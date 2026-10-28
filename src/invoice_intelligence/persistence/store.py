"""Single-user SQLite document/job store with transactions and lease fencing.

No invoice/payable approval records are created at the Day-3 text stage.
"""
from contextlib import contextmanager
import json
import sqlite3
import time
from uuid import uuid4

from invoice_intelligence.domain.errors import DocumentError

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
 media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, page_count INTEGER NOT NULL,
 original_key TEXT NOT NULL, status TEXT NOT NULL, result_key TEXT,
 created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT, lease_until REAL, last_error_code TEXT, last_error TEXT,
 created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
 key TEXT PRIMARY KEY, sha256 TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS job_attempts (
 token TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), attempt INTEGER NOT NULL,
 started_at REAL NOT NULL, finished_at REAL, status TEXT NOT NULL,
 error_code TEXT, elapsed_seconds REAL
);
CREATE INDEX IF NOT EXISTS jobs_status_lease ON jobs(status,lease_until);
PRAGMA user_version = 1;
"""


class Store:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = settings.data_dir / "documents.sqlite3"

    def initialize(self):
        with self.connect() as connection:
            # The first API and worker may open a fresh database simultaneously.
            for attempt in range(40):
                try:
                    connection.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as error:
                    if 'locked' not in str(error).lower() or attempt==39:raise
                    time.sleep(.05)
            connection.executescript(SCHEMA)
            from invoice_intelligence.persistence.extractions import SCHEMA as EXTRACTION_SCHEMA
            connection.executescript(EXTRACTION_SCHEMA)
            from invoice_intelligence.persistence.reviews import SCHEMA as REVIEW_SCHEMA
            connection.executescript(REVIEW_SCHEMA)
            from invoice_intelligence.persistence.matching import SCHEMA as MATCHING_SCHEMA
            connection.executescript(MATCHING_SCHEMA)
            from invoice_intelligence.persistence.operations import SCHEMA as OPERATIONS_SCHEMA
            connection.executescript(OPERATIONS_SCHEMA)
            connection.execute('BEGIN IMMEDIATE')
            columns={r['name'] for r in connection.execute('PRAGMA table_info(extraction_jobs)')}
            if 'retry_after' not in columns:
                connection.execute('ALTER TABLE extraction_jobs ADD COLUMN retry_after REAL NOT NULL DEFAULT 0')
            connection.execute('PRAGMA user_version=6')
            connection.commit()
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def existing(self, digest, key=None):
        with self.connect() as connection:
            if key:
                row = connection.execute("SELECT * FROM idempotency_keys WHERE key=?", (key,)).fetchone()
                if row and row["sha256"] != digest:
                    raise DocumentError("idempotency_conflict", "This Idempotency-Key was used with different file bytes.", 409)
            row = connection.execute("SELECT id FROM documents WHERE sha256=?", (digest,)).fetchone()
            return row["id"] if row else None

    def register(self, *, digest, filename, media_type, size_bytes, page_count, original_key, key=None):
        now = time.time()
        with self.transaction() as connection:
            if key:
                previous = connection.execute("SELECT * FROM idempotency_keys WHERE key=?", (key,)).fetchone()
                if previous and previous["sha256"] != digest:
                    raise DocumentError("idempotency_conflict", "This Idempotency-Key was used with different file bytes.", 409)
            row = connection.execute("SELECT id FROM documents WHERE sha256=?", (digest,)).fetchone()
            duplicate = row is not None
            document_id = row["id"] if row else str(uuid4())
            if not duplicate:
                connection.execute("""INSERT INTO documents
                    (id,sha256,filename,media_type,size_bytes,page_count,original_key,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,'queued',?,?)""",
                    (document_id, digest, filename, media_type, size_bytes, page_count, original_key, now, now))
                connection.execute("""INSERT INTO jobs(id,document_id,status,created_at,updated_at)
                    VALUES (?,?,'queued',?,?)""", (str(uuid4()), document_id, now, now))
            if key:
                connection.execute("INSERT OR IGNORE INTO idempotency_keys VALUES (?,?,?)", (key, digest, document_id))
        return document_id, duplicate

    def document(self, document_id):
        with self.connect() as connection:
            row = connection.execute("""SELECT d.*,j.id AS job_id,j.status AS job_status,j.attempts,
                j.last_error_code,j.last_error FROM documents d JOIN jobs j ON d.id=j.document_id
                WHERE d.id=?""", (document_id,)).fetchone()
            if row is None:
                raise DocumentError("document_not_found", "No document exists with this ID.", 404)
            result = dict(row)
            result["attempt_history"] = [dict(r) for r in connection.execute("""SELECT attempt,started_at,
                finished_at,status,error_code,elapsed_seconds FROM job_attempts WHERE job_id=? ORDER BY attempt""", (row["job_id"],))]
            return result

    def list_documents(self, limit=25, offset=0):
        with self.connect() as connection:
            ids = [r["id"] for r in connection.execute("SELECT id FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))]
        return [self.document(identifier) for identifier in ids]

    def claim(self):
        now = time.time()
        with self.transaction() as connection:
            rows = connection.execute("SELECT * FROM jobs WHERE status='queued' OR (status='processing' AND lease_until<?) ORDER BY created_at", (now,)).fetchall()
            for row in rows:
                if row["status"] == "processing":
                    connection.execute("UPDATE job_attempts SET status='lease_expired',finished_at=? WHERE token=? AND status='processing'", (now, row["lease_token"]))
                if row["attempts"] >= self.settings.max_attempts:
                    connection.execute("UPDATE jobs SET status='failed',lease_token=NULL,lease_until=NULL,last_error_code='attempt_limit',last_error='Maximum attempts reached.',updated_at=? WHERE id=?", (now, row["id"]))
                    connection.execute("UPDATE documents SET status='failed',updated_at=? WHERE id=?", (now, row["document_id"]))
                    continue
                token = str(uuid4())
                attempt = row["attempts"] + 1
                connection.execute("""UPDATE jobs SET status='processing',attempts=?,lease_token=?,lease_until=?,
                    last_error_code=NULL,last_error=NULL,updated_at=? WHERE id=?""",
                    (attempt, token, now + self.settings.process_timeout + 60, now, row["id"]))
                connection.execute("UPDATE documents SET status='processing',updated_at=? WHERE id=?", (now, row["document_id"]))
                connection.execute("INSERT INTO job_attempts(token,job_id,attempt,started_at,status) VALUES (?,?,?,?,'processing')", (token, row["id"], attempt, now))
                return dict(row) | {"lease_token": token, "attempts": attempt}
        return None

    def finish(self, job, *, result_key=None, status="text_ready", error=None, elapsed=0):
        now = time.time()
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=? AND status='processing' AND lease_token=?", (job["id"], job["lease_token"])).fetchone()
            if row is None:
                return False  # Fenced-out worker cannot overwrite the newer attempt.
            job_status = "failed" if error else "succeeded"
            code, message = (error.code, error.message) if error else (None, None)
            connection.execute("UPDATE jobs SET status=?,lease_token=NULL,lease_until=NULL,last_error_code=?,last_error=?,updated_at=? WHERE id=?", (job_status, code, message, now, job["id"]))
            connection.execute("UPDATE documents SET status=?,result_key=?,updated_at=? WHERE id=?", ("failed" if error else status, result_key, now, row["document_id"]))
            connection.execute("UPDATE job_attempts SET status=?,finished_at=?,error_code=?,elapsed_seconds=? WHERE token=?", (job_status, now, code, elapsed, job["lease_token"]))
        return True

    def retry(self, document_id):
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE document_id=?", (document_id,)).fetchone()
            if row is None:
                raise DocumentError("document_not_found", "No document exists with this ID.", 404)
            if row["status"] != "failed":
                raise DocumentError("retry_not_allowed", "Only a failed job can be retried.", 409)
            if row["attempts"] >= self.settings.max_attempts:
                raise DocumentError("attempt_limit", "Maximum processing attempts reached.", 409)
            now = time.time()
            connection.execute("UPDATE jobs SET status='queued',updated_at=? WHERE id=?", (now, row["id"]))
            connection.execute("UPDATE documents SET status='queued',updated_at=? WHERE id=?", (now, document_id))

    def result(self, document):
        if not document["result_key"]:
            return None
        try:
            return json.loads((self.settings.data_dir / document["result_key"]).read_text())
        except (OSError,ValueError):
            raise DocumentError('text_artifact_unavailable','Saved page/text artifacts are missing or unreadable. Restore the data folder from backup.',409) from None
