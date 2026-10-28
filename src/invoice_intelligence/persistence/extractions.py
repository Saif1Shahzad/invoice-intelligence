"""Durable extraction jobs and immutable successful candidate runs."""
import hashlib
import json
import time
from uuid import uuid4

from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.extraction.providers import identity

SCHEMA = """
CREATE TABLE IF NOT EXISTS extraction_jobs (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 provider TEXT NOT NULL, extractor_version TEXT NOT NULL,
 source_key TEXT NOT NULL, source_digest TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT, lease_until REAL, last_error_code TEXT, last_error TEXT,
 created_at REAL NOT NULL, updated_at REAL NOT NULL,
 UNIQUE(document_id,provider,extractor_version,source_digest)
);
CREATE TABLE IF NOT EXISTS extraction_attempts (
 token TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES extraction_jobs(id),
 attempt INTEGER NOT NULL, status TEXT NOT NULL, started_at REAL NOT NULL,
 finished_at REAL, elapsed_seconds REAL, error_code TEXT
);
CREATE TABLE IF NOT EXISTS extraction_runs (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES extraction_jobs(id),
 document_id TEXT NOT NULL REFERENCES documents(id), result_key TEXT NOT NULL,
 created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS extraction_jobs_state ON extraction_jobs(status,lease_until);
PRAGMA user_version = 2;
"""


class ExtractionStore:
    def __init__(self, store):
        self.base = store
        self.settings = store.settings
        self.provider, self.version = identity(self.settings)

    def enqueue(self, document_id):
        if self.settings.extraction_provider == "disabled":
            raise DocumentError("extraction_disabled", "Enable EXTRACTION_PROVIDER=local or groq in both API and worker.", 409)
        document = self.base.document(document_id)
        if document["status"] not in {"text_ready", "needs_review"} or not document["result_key"]:
            raise DocumentError("text_not_ready", "Wait for the text/OCR stage to complete before extraction.", 409)
        path = self.base.artifact(document["result_key"])
        if not path.is_file():
            raise DocumentError("text_result_missing", "Stored text result is unavailable.", 409)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise DocumentError("text_result_unreadable", "Stored text result cannot be read.", 409) from None
        now = time.time()
        with self.base.transaction() as connection:
            row = connection.execute("""SELECT id FROM extraction_jobs WHERE document_id=? AND provider=?
                AND extractor_version=? AND source_digest=?""", (document_id, self.provider, self.version, digest)).fetchone()
            if row:
                return row["id"], True
            identifier = str(uuid4())
            connection.execute("""INSERT INTO extraction_jobs
                (id,document_id,provider,extractor_version,source_key,source_digest,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'queued',?,?)""", (identifier, document_id, self.provider, self.version, document["result_key"], digest, now, now))
        return identifier, False

    def discover(self):
        """Recover the text-finish/enqueue gap, and upgrade saved Day-3 text results."""
        if self.provider == "groq":
            return  # Groq jobs only arise from new uploads or an explicit Extract request.
        with self.base.connect() as connection:
            rows = connection.execute("""SELECT d.id FROM documents d WHERE d.result_key IS NOT NULL
                AND d.status IN ('text_ready','needs_review') AND NOT EXISTS
                (SELECT 1 FROM extraction_jobs e WHERE e.document_id=d.id AND e.source_key=d.result_key
                 AND e.provider=? AND e.extractor_version=?) LIMIT 10""", (self.provider, self.version)).fetchall()
        for row in rows:
            try:
                self.enqueue(row["id"])
            except DocumentError as error:
                # A damaged old artifact must not crash/starve the whole worker.
                document = self.base.document(row["id"])
                now = time.time()
                digest = "unavailable:"+hashlib.sha256(document["result_key"].encode()).hexdigest()
                with self.base.transaction() as connection:
                    connection.execute("""INSERT OR IGNORE INTO extraction_jobs
                        (id,document_id,provider,extractor_version,source_key,source_digest,status,last_error_code,last_error,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,'failed',?,?,?,?)""", (str(uuid4()),row["id"],self.provider,self.version,document["result_key"],digest,error.code,error.message,now,now))

    def claim(self,document_id=None):
        now = time.time()
        with self.base.transaction() as connection:
            if self.provider=='groq':
                last=connection.execute("SELECT MAX(a.started_at) FROM extraction_attempts a JOIN extraction_jobs j ON a.job_id=j.id WHERE j.provider='groq'").fetchone()[0]
                if last is not None and now-last<self.settings.groq_min_interval:return None
            rows = connection.execute("SELECT * FROM extraction_jobs WHERE provider=? AND extractor_version=? AND ((status='queued' AND retry_after<=?) OR (status='processing' AND lease_until<?)) AND (? IS NULL OR document_id=?) ORDER BY created_at", (self.provider,self.version,now,now,document_id,document_id)).fetchall()
            for row in rows:
                if row["status"] == "processing":
                    connection.execute("UPDATE extraction_attempts SET status='lease_expired',finished_at=? WHERE token=? AND status='processing'", (now,row["lease_token"]))
                if row["attempts"] >= self.settings.max_attempts:
                    connection.execute("UPDATE extraction_jobs SET status='failed',last_error_code='attempt_limit',last_error='Maximum attempts reached.',updated_at=?,lease_token=NULL,lease_until=NULL WHERE id=?", (now,row["id"]))
                    continue
                token = str(uuid4())
                connection.execute("""UPDATE extraction_jobs SET status='processing',attempts=?,lease_token=?,lease_until=?,
                    last_error_code=NULL,last_error=NULL,updated_at=? WHERE id=?""", (row["attempts"]+1,token,now+self.settings.process_timeout+60,now,row["id"]))
                connection.execute("INSERT INTO extraction_attempts(token,job_id,attempt,status,started_at) VALUES (?,?,?,'processing',?)", (token,row["id"],row["attempts"]+1,now))
                return dict(row) | {"lease_token":token,"attempts":row["attempts"]+1}
        return None

    def finish(self, job, *, result_key=None, error=None, elapsed=0):
        if not error and result_key:
            self.base.publish_tree(str(__import__("pathlib").Path(result_key).parent))
        now = time.time()
        with self.base.transaction() as connection:
            row = connection.execute("SELECT * FROM extraction_jobs WHERE id=? AND status='processing' AND lease_token=?", (job["id"],job["lease_token"])).fetchone()
            if row is None:
                return False
            retryable=error and error.code=='groq_rate_limit' and job['attempts']<self.settings.max_attempts
            status = "queued" if retryable else "failed" if error else "succeeded"
            connection.execute('UPDATE extraction_jobs SET retry_after=? WHERE id=?',(now+max(5,error.retry_after) if retryable else 0,job['id']))
            connection.execute("UPDATE extraction_jobs SET status=?,lease_token=NULL,lease_until=NULL,last_error_code=?,last_error=?,updated_at=? WHERE id=?",
                (status,error.code if error else None,error.message if error else None,now,job["id"]))
            connection.execute("UPDATE extraction_attempts SET status=?,finished_at=?,elapsed_seconds=?,error_code=? WHERE token=?",
                (status,now,elapsed,error.code if error else None,job["lease_token"]))
            if not error:
                connection.execute("INSERT INTO extraction_runs(id,job_id,document_id,result_key,created_at) VALUES (?,?,?,?,?)",
                    (job["lease_token"],job["id"],job["document_id"],result_key,now))
        return True

    def summary(self, document_id, include_result=True):
        with self.base.connect() as connection:
            row = connection.execute("SELECT * FROM extraction_jobs WHERE document_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (document_id,)).fetchone()
            if row is None:
                return {"status":"not_started","job":None,"fields":None,"validation":None}
            row = dict(row)
            attempts = [dict(a) for a in connection.execute("SELECT attempt,status,started_at,finished_at,elapsed_seconds,error_code FROM extraction_attempts WHERE job_id=? ORDER BY attempt", (row["id"],))]
            run = connection.execute("SELECT * FROM extraction_runs WHERE job_id=? ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
        output = {"status":row["status"],"job":{"id":row["id"],"status":row["status"],"attempts":row["attempts"],
            "provider":row["provider"],"extractor_version":row["extractor_version"],
            "retry_after":row.get("retry_after",0),"error_code":row["last_error_code"],"error":row["last_error"],"attempt_history":attempts},
            "run_id":run["id"] if run else None}
        if run:
            try:
                payload = json.loads(self.base.artifact(run["result_key"]).read_text())
            except (OSError,ValueError):
                output['status']='failed'
                output['job'].update(error_code='extraction_artifact_unavailable',error='Saved extraction is missing or unreadable. Restore the data folder from backup.')
                output.update(fields=None,validation=None)
                return output
            output["status"] = payload["validation"]["routing"]
            if include_result:
                output.update(fields=payload["extraction"],validation=payload["validation"],provenance=payload["provenance"],usage=payload["usage"])
        elif include_result:
            output.update(fields=None,validation=None)
        return output

    def history(self, document_id):
        self.base.document(document_id)
        with self.base.connect() as connection:
            runs = [dict(row) for row in connection.execute("SELECT r.*,e.provider,e.extractor_version,e.source_digest FROM extraction_runs r JOIN extraction_jobs e ON r.job_id=e.id WHERE r.document_id=? ORDER BY r.created_at", (document_id,))]
        return [{"run_id":run["id"],"created_at":run["created_at"],"provider":run["provider"],
                 "extractor_version":run["extractor_version"],"source_text_sha256":run["source_digest"]} for run in runs]

    def retry(self, document_id):
        self.base.document(document_id)
        with self.base.transaction() as connection:
            row = connection.execute("SELECT * FROM extraction_jobs WHERE document_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (document_id,)).fetchone()
            if row is None or row["status"] != "failed":
                raise DocumentError("extraction_retry_not_allowed", "Only a failed extraction job can be retried.", 409)
            if row["attempts"] >= self.settings.max_attempts:
                raise DocumentError("attempt_limit", "Maximum extraction attempts reached.", 409)
            connection.execute("UPDATE extraction_jobs SET status='queued',updated_at=? WHERE id=?", (time.time(),row["id"]))
