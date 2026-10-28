"""PO versions, reversible pair decisions and live matching context for review."""
import hashlib
import json
import time
from uuid import uuid4

from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.matching.purchase_orders import parse_csv
from invoice_intelligence.matching.rules import VERSION, digest, duplicate_rule, match_po, normalize, value

SCHEMA='''
CREATE TABLE IF NOT EXISTS po_imports (
 id TEXT PRIMARY KEY, digest TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
 actor TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS po_versions (
 id TEXT PRIMARY KEY, po_key TEXT NOT NULL, po_number TEXT NOT NULL,
 supplier_name TEXT NOT NULL, currency TEXT NOT NULL, content_digest TEXT NOT NULL,
 lines_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES po_imports(id),
 created_at REAL NOT NULL, UNIQUE(po_key,content_digest)
);
CREATE TABLE IF NOT EXISTS po_heads (
 po_key TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES po_versions(id)
);
CREATE TABLE IF NOT EXISTS duplicate_decisions (
 id TEXT PRIMARY KEY, left_id TEXT NOT NULL REFERENCES documents(id),
 right_id TEXT NOT NULL REFERENCES documents(id), context_token TEXT NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('same_bill','different_bill','unresolved')),
 canonical_document_id TEXT REFERENCES documents(id), actor TEXT NOT NULL,
 reason TEXT NOT NULL, created_at REAL NOT NULL, CHECK(left_id<right_id)
);
CREATE INDEX IF NOT EXISTS duplicate_pair ON duplicate_decisions(left_id,right_id,created_at);
PRAGMA user_version=4;
'''
for table in ['po_imports','po_versions','duplicate_decisions']:
    for operation in ['UPDATE','DELETE']:
        SCHEMA+=f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Matching history is append-only'); END;\n"


class MatchingStore:
    def __init__(self,base):
        self.base=base

    def import_csv(self,raw,filename,actor,reason):
        if not actor.strip() or not reason.strip() or len(actor)>80 or len(reason)>1000:
            raise DocumentError('po_import_identity_required','Provide a reviewer name (1–80 characters) and reason (1–1000 characters).',422)
        orders=parse_csv(raw)
        checksum=hashlib.sha256(raw).hexdigest()
        with self.base.transaction() as c:
            old=c.execute('SELECT id FROM po_imports WHERE digest=?',(checksum,)).fetchone()
            if old:
                return {'import_id':old['id'],'reused':True,'new_versions':0,'orders':len(orders)}
            identifier=str(uuid4());now=time.time();created=0
            c.execute('INSERT INTO po_imports VALUES (?,?,?,?,?,?)',(identifier,checksum,filename[:240],actor.strip(),reason.strip(),now))
            for key,order in orders.items():
                old=c.execute('SELECT id FROM po_versions WHERE po_key=? AND content_digest=?',(key,order['content_digest'])).fetchone()
                # Replaying an old version cannot roll back a newer head.
                if old: continue
                version=str(uuid4());created+=1
                c.execute('INSERT INTO po_versions VALUES (?,?,?,?,?,?,?,?,?)',(
                    version,key,order['po_number'],order['supplier_name'],order['currency'],order['content_digest'],json.dumps(order['lines']),identifier,now))
                c.execute('INSERT INTO po_heads VALUES (?,?) ON CONFLICT(po_key) DO UPDATE SET version_id=excluded.version_id',(key,version))
        return {'import_id':identifier,'reused':False,'new_versions':created,'orders':len(orders)}

    def orders(self):
        with self.base.connect() as c:
            return [dict(row) for row in c.execute('''SELECT v.id,v.po_number,v.supplier_name,v.currency,v.created_at,
                i.actor,i.reason FROM po_heads h JOIN po_versions v ON h.version_id=v.id
                JOIN po_imports i ON v.import_id=i.id ORDER BY v.po_number''')]

    def po_history(self,reference):
        with self.base.connect() as c:
            return [dict(row)|{'lines':json.loads(row['lines_json'])} for row in c.execute('''SELECT v.*,i.actor,i.reason
                FROM po_versions v JOIN po_imports i ON v.import_id=i.id WHERE v.po_key=? ORDER BY v.created_at,v.rowid''',(normalize(reference),))]

    def profiles(self,c):
        rows=c.execute('''SELECT d.id,d.filename,r.id AS latest_run,r.result_key,
            v.source_run_id,v.fields_json,v.status AS review_status FROM documents d
            JOIN extraction_runs r ON r.id=(SELECT r2.id FROM extraction_runs r2 WHERE r2.document_id=d.id
                ORDER BY r2.created_at DESC,r2.rowid DESC LIMIT 1)
            LEFT JOIN review_heads h ON h.document_id=d.id
            LEFT JOIN review_revisions v ON v.document_id=h.document_id AND v.revision=h.revision
            ORDER BY d.id''').fetchall()
        profiles={};unavailable=[]
        for row in rows:
            try:
                fields=json.loads(row['fields_json']) if row['fields_json'] else json.loads((self.base.settings.data_dir/row['result_key']).read_text())['extraction']
                # Values only: decision status/reasons do not invalidate a pair, but edits/runs do.
                def plain(v):
                    if isinstance(v,dict):
                        return v.get('value') if 'status' in v and 'value' in v else {k:plain(x) for k,x in v.items()}
                    return [plain(x) for x in v] if isinstance(v,list) else v
                fingerprint=digest({'fields':plain(fields),'run':row['source_run_id'] or row['latest_run'],'latest':row['latest_run']})
                profiles[row['id']]={'id':row['id'],'filename':row['filename'],'fields':fields,'fingerprint':fingerprint,
                    'review_status':row['review_status'] or 'not_started'}
            except (OSError,ValueError,KeyError):
                unavailable.append(row['id'])
        # Pending/failed extraction is visible as incomplete duplicate coverage.
        unavailable+= [row['id'] for row in c.execute('''SELECT id FROM documents d WHERE NOT EXISTS
            (SELECT 1 FROM extraction_runs r WHERE r.document_id=d.id) ORDER BY id''')]
        return profiles,sorted(set(unavailable))

    def pair_context(self,a,b):
        return digest(sorted([(a['id'],a['fingerprint']),(b['id'],b['fingerprint'])]))

    def findings(self,c,document_id,profile_snapshot=None):
        profiles,unavailable=profile_snapshot if profile_snapshot is not None else self.profiles(c)
        if document_id not in profiles:
            raise DocumentError('matching_not_ready','A readable extraction is required for matching.',409)
        current=profiles[document_id];fields=current['fields'];duplicates=[]
        for other in profiles.values():
            if other['id']==document_id: continue
            rule=duplicate_rule(fields,other['fields'])
            if not rule: continue
            left,right=sorted([document_id,other['id']]);context=self.pair_context(current,other)
            event=c.execute('''SELECT * FROM duplicate_decisions WHERE left_id=? AND right_id=?
                ORDER BY created_at DESC,rowid DESC LIMIT 1''',(left,right)).fetchone()
            valid=event is not None and event['context_token']==context
            decision=event['decision'] if valid else 'unresolved'
            duplicates.append({'document_id':other['id'],'filename':other['filename'],
                'supplier':value(other['fields'],'supplier_name'),'invoice_number':value(other['fields'],'invoice_number'),
                'total':value(other['fields'],'total'),'currency':value(other['fields'],'currency'),
                **rule,'decision':decision,'decision_id':event['id'] if valid else None,
                'canonical_document_id':event['canonical_document_id'] if valid else None,
                'decision_actor':event['actor'] if event else None,'decision_reason':event['reason'] if event else None,
                'decision_time':event['created_at'] if event else None,
                'decision_stale':bool(event and not valid),'other_fingerprint':other['fingerprint']})
        po=c.execute('''SELECT v.* FROM po_heads h JOIN po_versions v ON h.version_id=v.id
            WHERE h.po_key=?''',(normalize(value(fields,'po_number')),)).fetchone()
        order=dict(po)|{'lines':json.loads(po['lines_json'])} if po else None
        purchase_order=match_po(fields,order)
        blocked=[{'code':'duplicate_unresolved','document_id':d['document_id'],'message':'Resolve this possible duplicate before confirmation.'} for d in duplicates if d['decision']=='unresolved']
        blocked += [{'code':'marked_as_duplicate','document_id':d['document_id'],'message':'This invoice is marked as a duplicate of another record.'}
                    for d in duplicates if d['decision']=='same_bill' and d['canonical_document_id']!=document_id]
        token=digest({'version':VERSION,'current':current['fingerprint'],'duplicates':duplicates,
                      'purchase_order':purchase_order,'unavailable_documents':unavailable})
        return {'version':VERSION,'token':token,'duplicates':duplicates,'purchase_order':purchase_order,
            'blockers':blocked,'allowed':not blocked,'requires_po_exception':bool(purchase_order['issues']),
            'unavailable_document_ids':unavailable,'coverage_notice':f'{len(profiles)} readable invoices compared; {len(unavailable)} documents cannot yet be compared.',
            'scope':'Heuristic duplicate candidates require human decisions. No automatic merge, payment or calibrated probability.'}

    def get(self,document_id):
        self.base.document(document_id)
        with self.base.connect() as c:
            return self.findings(c,document_id)

    def summaries(self,document_ids):
        """Load the corpus once for a queue page, rather than once per card."""
        from invoice_intelligence.persistence.reviews import ReviewStore
        result={}
        with self.base.connect() as c:
            snapshot=self.profiles(c)
            for identifier in document_ids:
                if identifier not in snapshot[0]:
                    result[identifier]={'status':'not_ready'}
                    continue
                findings=self.findings(c,identifier,snapshot)
                row=ReviewStore(self.base).current(c,identifier)
                saved=next((change['after'] for change in json.loads(row['changes_json']) if change['field']=='matching_checks'),None) if row else None
                result[identifier]={'status':'checked','duplicate_candidates':len(findings['duplicates']),
                    'duplicate_blockers':len(findings['blockers']),
                    'marked_duplicate':any(b['code']=='marked_as_duplicate' for b in findings['blockers']),
                    'po_status':findings['purchase_order']['status'],'po_discrepancies':len(findings['purchase_order']['issues']),
                    'needs_recheck':bool(row and row['status']=='approved' and (not saved or saved['token']!=findings['token']))}
        return result

    def decide_duplicate(self,document_id,request):
        from invoice_intelligence.persistence.reviews import ReviewStore
        self.base.document(document_id)
        with self.base.transaction() as c:
            reviews=ReviewStore(self.base);row=reviews.check(c,document_id,request)
            findings=self.findings(c,document_id)
            if findings['token']!=request.matching_token:
                raise DocumentError('matching_conflict','Matching inputs changed. Reload and inspect the current checks.',409)
            candidate=next((d for d in findings['duplicates'] if d['document_id']==request.other_document_id),None)
            if candidate is None:
                raise DocumentError('duplicate_candidate_not_found','This pair is not a current duplicate candidate.',409)
            pair=sorted([document_id,request.other_document_id]);canonical=request.canonical_document_id
            if (request.decision=='same_bill' and canonical not in pair) or (request.decision!='same_bill' and canonical is not None):
                raise DocumentError('invalid_duplicate_decision','Choose one member of the pair as canonical only for same_bill.',422)
            if request.decision=='same_bill':
                canonical_findings=self.findings(c,canonical)
                if any(d['decision']=='same_bill' and d['canonical_document_id']!=canonical for d in canonical_findings['duplicates']):
                    raise DocumentError('duplicate_chain','Choose a canonical invoice that is not itself a duplicate. Reopen the prior decision first.',409)
                duplicate_id=next(x for x in pair if x!=canonical)
                prior=self.findings(c,duplicate_id)
                if any(d['decision']=='same_bill' and d['canonical_document_id'] not in {canonical,None} for d in prior['duplicates']):
                    raise DocumentError('duplicate_chain','This invoice already has another canonical record. Reopen that decision first.',409)
            event_id=str(uuid4())
            profiles,_=self.profiles(c)
            c.execute('INSERT INTO duplicate_decisions VALUES (?,?,?,?,?,?,?,?,?)',(
                event_id,*pair,self.pair_context(profiles[pair[0]],profiles[pair[1]]),request.decision,canonical,
                request.actor.strip(),request.reason.strip(),time.time()))
            from invoice_intelligence.schemas.extraction import InvoiceExtraction
            reviews.append(c,document_id,row['revision']+1,row['source_run_id'],
                InvoiceExtraction.model_validate_json(row['fields_json']),json.loads(row['validation_json']),
                actor=request.actor.strip(),reason=request.reason.strip(),action='duplicate_reviewed',
                changes=[{'field':'duplicate_decision','before':candidate['decision'],
                          'after':{'decision':request.decision,'canonical_document_id':canonical,'other_document_id':request.other_document_id,'event_id':event_id}}])
        return reviews.get(document_id)

    def duplicate_history(self,document_id):
        self.base.document(document_id)
        with self.base.connect() as c:
            return [dict(row) for row in c.execute('SELECT * FROM duplicate_decisions WHERE left_id=? OR right_id=? ORDER BY created_at DESC,rowid DESC',(document_id,document_id))]
