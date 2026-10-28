"""PostgreSQL persistence for the existing reviewed-invoice domain.

Domain mutations take a database advisory transaction lock, preserving the
single-writer semantics relied upon by matching, revision checks and job claims.
Remote inference never runs inside that transaction.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import tempfile

from invoice_intelligence.persistence.store import Store
from invoice_intelligence.domain.errors import DocumentError

LOCK = 714_092_613

class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)

class Cursor:
    def __init__(self, cursor): self.cursor=cursor
    @property
    def rowcount(self): return self.cursor.rowcount
    def fetchone(self):
        row=self.cursor.fetchone()
        return Row(row) if row is not None else None
    def fetchall(self): return [Row(row) for row in self.cursor.fetchall()]
    def __iter__(self):
        for row in self.cursor: yield Row(row)


def translate(sql):
    sql=sql.replace('? IS NULL','CAST(? AS TEXT) IS NULL')
    if '?' in sql:
        # All domain statements use ? only as bind markers, never within values.
        sql=sql.replace('%','%%').replace('?','%s')
    sql=re.sub(r'\browid\b','id',sql,flags=re.I)
    if re.search(r'INSERT\s+OR\s+IGNORE',sql,re.I):
        sql=re.sub(r'INSERT\s+OR\s+IGNORE','INSERT',sql,flags=re.I).rstrip().rstrip(';')+' ON CONFLICT DO NOTHING'
    return sql

class Connection:
    def __init__(self,raw): self.raw=raw
    def execute(self,sql,params=()): return Cursor(self.raw.execute(translate(sql),params))
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()


def schema_sql():
    from invoice_intelligence.persistence.store import SCHEMA
    from invoice_intelligence.persistence.extractions import SCHEMA as EXTRACTIONS
    from invoice_intelligence.persistence.reviews import SCHEMA as REVIEWS
    from invoice_intelligence.persistence.matching import SCHEMA as MATCHING
    from invoice_intelligence.persistence.operations import SCHEMA as OPERATIONS
    sql='\n'.join([SCHEMA,EXTRACTIONS,REVIEWS,MATCHING,OPERATIONS])
    sql=re.sub(r'CREATE TRIGGER.*?END;','',sql,flags=re.S)
    sql=re.sub(r'PRAGMA[^;]*;','',sql)
    sql=re.sub(r'\bREAL\b','DOUBLE PRECISION',sql)
    return sql

class PostgresStore(Store):
    def __init__(self,settings):
        self.settings=settings
        settings.data_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=None
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row
        self.pool=ConnectionPool(os.environ['DATABASE_URL'],min_size=0,max_size=5,max_idle=30,timeout=20,
            kwargs={'autocommit':True,'row_factory':dict_row,'connect_timeout':10},open=True)

    def close(self):
        self.pool.close()


    @contextmanager
    def connect(self):
        with self.pool.connection() as raw:
            schema=os.getenv('INVOICE_DB_SCHEMA')
            if schema:
                from psycopg import sql
                with raw.transaction():
                    raw.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
                    yield Connection(raw)
            else:
                yield Connection(raw)

    @contextmanager
    def transaction(self):
        with self.connect() as c:
            with c.raw.transaction():
                c.raw.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
                yield c

    def initialize(self):
        with self.transaction() as c:
            c.raw.execute('CREATE TABLE IF NOT EXISTS invoice_cloud_migrations (version INTEGER PRIMARY KEY)')
            if c.raw.execute('SELECT version FROM invoice_cloud_migrations WHERE version=1').fetchone(): return
            c.raw.execute(schema_sql(),prepare=False)
            c.raw.execute('ALTER TABLE extraction_jobs ADD COLUMN IF NOT EXISTS retry_after DOUBLE PRECISION NOT NULL DEFAULT 0')
            c.raw.execute('CREATE TABLE IF NOT EXISTS invoice_artifacts (key TEXT PRIMARY KEY, sha256 TEXT NOT NULL, size_bytes BIGINT NOT NULL)')
            c.raw.execute("""CREATE OR REPLACE FUNCTION invoice_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Invoice audit history is append-only'; END $$""")
            for table in ['review_revisions','po_imports','po_versions','duplicate_decisions','review_time_events']:
                c.raw.execute(f'CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION invoice_append_only()')
            c.raw.execute('INSERT INTO invoice_cloud_migrations VALUES (1)')

    def _key(self,key):
        key=str(key)
        if not key or key.startswith('/') or any(p in {'','..','.'} for p in key.split('/')) or '\\' in key:
            raise DocumentError('invalid_artifact_key','Invalid source artifact location.',500)
        path=(self.settings.data_dir/key).resolve()
        if not path.is_relative_to(self.settings.data_dir):raise DocumentError('invalid_artifact_key','Invalid source artifact location.',500)
        return key,path

    def artifact(self,key):
        from vercel.blob import sync as blob
        key,path=self._key(key)
        with self.connect() as c: row=c.execute('SELECT sha256,size_bytes FROM invoice_artifacts WHERE key=?',(key,)).fetchone()
        if row is None: raise DocumentError('artifact_unavailable','The private source artifact is not available.',409)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']:return path
        if row['size_bytes']>80*1024*1024:raise DocumentError('artifact_limit','Source artifact exceeds its limit.',409)
        body=blob.get_blob(key,access='private').body
        if len(body)!=row['size_bytes'] or hashlib.sha256(body).hexdigest()!=row['sha256']:
            raise DocumentError('artifact_integrity_error','Private source artifact failed its integrity check.',409)
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
            temp=Path(f.name);f.write(body)
        temp.chmod(0o600);os.replace(temp,path)
        return path

    def publish(self,key):
        from vercel.blob import sync as blob
        key,path=self._key(key);body=path.read_bytes();digest=hashlib.sha256(body).hexdigest()
        with self.connect() as c:old=c.execute('SELECT sha256 FROM invoice_artifacts WHERE key=?',(key,)).fetchone()
        if old:
            if old['sha256']!=digest:raise DocumentError('immutable_artifact_conflict','A source artifact cannot be overwritten.',409)
            return
        # Content-addressed originals and per-attempt output keys are immutable.
        # Equivalent uploads may race; the database digest still checks identity.
        try:blob.put_blob(key,body,access='private',add_random_suffix=False,allow_overwrite=False)
        except Exception as error:
            if getattr(error,'status_code',None) not in {409,400}:raise
            existing=blob.get_blob(key,access='private').body
            if hashlib.sha256(existing).hexdigest()!=digest:raise DocumentError('immutable_artifact_conflict','Private source differs from expected bytes.',409) from None
        with self.transaction() as c:
            c.execute('INSERT INTO invoice_artifacts(key,sha256,size_bytes) VALUES (?,?,?) ON CONFLICT DO NOTHING',(key,digest,len(body)))
            saved=c.execute('SELECT sha256 FROM invoice_artifacts WHERE key=?',(key,)).fetchone()
            if saved['sha256']!=digest:raise DocumentError('immutable_artifact_conflict','A source artifact cannot be overwritten.',409)

    def publish_tree(self,key):
        _,root=self._key(key)
        for path in sorted(root.rglob('*')):
            if path.is_file():self.publish(path.relative_to(self.settings.data_dir).as_posix())

    def hydrate_source(self,key):
        import json
        source=self.artifact(key)
        payload=json.loads(source.read_text())
        for page in payload['pages']:
            self.artifact((Path(key).parent/f"page_{page['page']}.png").as_posix())
        return source
