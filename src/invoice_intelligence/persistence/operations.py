"""Worker diagnostics and replay-safe, explicitly started review-time sessions."""
import time
from invoice_intelligence.domain.errors import DocumentError

SCHEMA='''
CREATE TABLE IF NOT EXISTS worker_heartbeats (
 id TEXT PRIMARY KEY, started_at REAL NOT NULL, last_seen REAL NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_sessions (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), actor TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('human','automated_demo')), start_revision INTEGER NOT NULL,
 started_at REAL NOT NULL, last_received_at REAL NOT NULL, last_sequence INTEGER NOT NULL DEFAULT 0,
 active_ms INTEGER NOT NULL DEFAULT 0, closed_at REAL, end_revision INTEGER, end_status TEXT
);
CREATE TABLE IF NOT EXISTS review_time_events (
 session_id TEXT NOT NULL REFERENCES review_sessions(id), sequence INTEGER NOT NULL,
 active_ms INTEGER NOT NULL, ended INTEGER NOT NULL, created_at REAL NOT NULL,
 PRIMARY KEY(session_id,sequence)
);
CREATE TRIGGER IF NOT EXISTS review_time_no_update BEFORE UPDATE ON review_time_events
 BEGIN SELECT RAISE(ABORT,'Review time events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_time_no_delete BEFORE DELETE ON review_time_events
 BEGIN SELECT RAISE(ABORT,'Review time events are append-only'); END;
PRAGMA user_version=5;
'''

class OperationsStore:
    def __init__(self,base): self.base=base

    def worker_tick(self,identifier,state='running',now=None):
        now=time.time() if now is None else now
        with self.base.connect() as c:
            c.execute('''INSERT INTO worker_heartbeats VALUES (?,?,?,?) ON CONFLICT(id)
                DO UPDATE SET last_seen=excluded.last_seen,state=excluded.state''',(identifier,now,now,state))

    def health(self,now=None):
        now=time.time() if now is None else now
        with self.base.connect() as c:
            workers=[dict(r) for r in c.execute("SELECT * FROM worker_heartbeats WHERE state='running' AND last_seen>=?",(now-20,))]
            text={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) AS n FROM jobs GROUP BY status')}
            extraction={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) AS n FROM extraction_jobs GROUP BY status')}
        return {'worker_active':bool(workers),'workers':len(workers),'heartbeat_timeout_seconds':20,
                'text_jobs':text,'extraction_jobs':extraction}

    def start(self,document_id,request,now=None):
        from invoice_intelligence.persistence.reviews import ReviewStore
        self.base.document(document_id);now=time.time() if now is None else now
        if not request.actor.strip(): raise DocumentError('reviewer_required','Enter your reviewer name before starting the timer.',422)
        with self.base.transaction() as c:
            row=ReviewStore(self.base).ensure(c,document_id)
            old=c.execute('SELECT * FROM review_sessions WHERE id=?',(str(request.session_id),)).fetchone()
            if old:
                if old['document_id']!=document_id or old['actor']!=request.actor.strip() or old['kind']!=request.kind:
                    raise DocumentError('session_conflict','Session ID already belongs to different inputs.',409)
            else:
                if row['status']!='pending':
                    raise DocumentError('review_not_pending','Reopen the invoice before starting a review timer.',409)
                c.execute('''INSERT INTO review_sessions(id,document_id,actor,kind,start_revision,started_at,last_received_at)
                    VALUES (?,?,?,?,?,?,?)''',(str(request.session_id),document_id,request.actor.strip(),request.kind,row['revision'],now,now))
        return self.session(document_id,str(request.session_id))

    def session(self,document_id,identifier):
        with self.base.connect() as c:
            row=c.execute('SELECT * FROM review_sessions WHERE id=? AND document_id=?',(identifier,document_id)).fetchone()
        if row is None: raise DocumentError('session_not_found','No matching review-time session.',404)
        return dict(row)

    def record(self,document_id,identifier,request,now=None):
        now=time.time() if now is None else now
        with self.base.transaction() as c:
            row=c.execute('SELECT * FROM review_sessions WHERE id=? AND document_id=?',(identifier,document_id)).fetchone()
            if row is None: raise DocumentError('session_not_found','No matching review-time session.',404)
            old=c.execute('SELECT * FROM review_time_events WHERE session_id=? AND sequence=?',(identifier,request.sequence)).fetchone()
            if old:
                if old['active_ms']!=request.active_ms or old['ended']!=request.ended:
                    raise DocumentError('session_conflict','This timing sequence was already used with different values.',409)
            else:
                if row['closed_at'] is not None: raise DocumentError('session_closed','Start a new timer; this session is closed.',409)
                if request.sequence!=row['last_sequence']+1:
                    raise DocumentError('session_sequence_conflict','Reload session state before sending more timing events.',409)
                if request.active_ms<row['active_ms'] or request.active_ms>max(0,now-row['started_at'])*1000+1000:
                    raise DocumentError('invalid_review_time','Active time must be cumulative, nondecreasing, and within elapsed wall time.',422)
                c.execute('INSERT INTO review_time_events VALUES (?,?,?,?,?)',(identifier,request.sequence,request.active_ms,int(request.ended),now))
                from invoice_intelligence.persistence.reviews import ReviewStore
                head=ReviewStore(self.base).current(c,document_id)
                c.execute('''UPDATE review_sessions SET last_sequence=?,active_ms=?,last_received_at=?,closed_at=?,end_revision=?,end_status=? WHERE id=?''',
                          (request.sequence,request.active_ms,now,now if request.ended else None,
                           head['revision'] if request.ended else None,head['status'] if request.ended else None,identifier))
        return self.session(document_id,identifier)

    def sessions(self,document_id=None):
        with self.base.connect() as c:
            query='SELECT * FROM review_sessions';args=()
            if document_id is not None: query+=' WHERE document_id=?';args=(document_id,)
            return [dict(r) for r in c.execute(query+' ORDER BY started_at',args)]
