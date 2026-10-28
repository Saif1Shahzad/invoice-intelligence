"""Local review revisions. Source candidates never change when a reviewer edits."""
import json
import time
from decimal import DecimalException

from pydantic import ValidationError
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.domain.invoice_validation import validate_extraction
from invoice_intelligence.schemas.extraction import InvoiceExtraction, ExtractedLineItem, ExtractedTax

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_heads (
 document_id TEXT PRIMARY KEY REFERENCES documents(id), revision INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS review_revisions (
 document_id TEXT NOT NULL REFERENCES documents(id), revision INTEGER NOT NULL,
 source_run_id TEXT NOT NULL REFERENCES extraction_runs(id),
 status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
 fields_json TEXT NOT NULL, validation_json TEXT NOT NULL,
 actor TEXT NOT NULL, reason TEXT NOT NULL, action TEXT NOT NULL,
 changes_json TEXT NOT NULL, acknowledged_warnings INTEGER NOT NULL,
 created_at REAL NOT NULL, PRIMARY KEY(document_id,revision)
);
CREATE TRIGGER IF NOT EXISTS review_revision_no_update BEFORE UPDATE ON review_revisions
 BEGIN SELECT RAISE(ABORT,'Review revisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_revision_no_delete BEFORE DELETE ON review_revisions
 BEGIN SELECT RAISE(ABORT,'Review revisions are append-only'); END;
PRAGMA user_version = 3;
"""
HEADERS = tuple(name for name in InvoiceExtraction.model_fields if name not in {
    'schema_version', 'document_id', 'line_items', 'taxes', 'warnings'})
BLOCKING = {'required_field_unresolved','line_field_unresolved','missing_line_items',
            'header_equation_incomplete','optional_amount_unresolved','ambiguous_field','line_discount_ambiguous'}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def confirmation(validation):
    blockers = [issue for issue in validation['issues'] if issue['severity'] == 'error' or issue['code'] in BLOCKING]
    return {'allowed': not blockers, 'blockers': blockers,
            'warning_count': sum(issue['severity'] == 'warning' for issue in validation['issues'])}


class ReviewStore:
    def __init__(self, base):
        self.base = base

    def latest(self, connection, document_id):
        return connection.execute('''SELECT r.*,j.source_key FROM extraction_runs r
            JOIN extraction_jobs j ON r.job_id=j.id WHERE r.document_id=?
            ORDER BY r.created_at DESC,r.rowid DESC LIMIT 1''', (document_id,)).fetchone()

    def candidate(self, run):
        if run is None:
            raise DocumentError('review_not_ready', 'Wait for structured extraction to finish.', 409)
        try:
            payload = json.loads(self.base.artifact(run['result_key']).read_text())
            fields = InvoiceExtraction.model_validate(payload['extraction'])
        except (OSError, ValueError, KeyError):
            raise DocumentError('candidate_unavailable', 'The saved extraction candidate is unavailable.', 409) from None
        return fields, validate_extraction(fields)

    def current(self, connection, document_id):
        return connection.execute('''SELECT r.* FROM review_heads h JOIN review_revisions r
            ON h.document_id=r.document_id AND h.revision=r.revision WHERE h.document_id=?''', (document_id,)).fetchone()

    def append(self, connection, document_id, revision, run_id, fields, validation, *, status='pending',
               actor='system', reason='Imported extraction candidate', action='initialized', changes=(), acknowledged=False):
        connection.execute('''INSERT INTO review_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (document_id, revision, run_id, status, fields.model_dump_json(), dumps(validation), actor, reason,
             action, dumps(changes), int(acknowledged), time.time()))
        connection.execute('''INSERT INTO review_heads VALUES (?,?) ON CONFLICT(document_id)
            DO UPDATE SET revision=excluded.revision''', (document_id, revision))

    def ensure(self, connection, document_id):
        current = self.current(connection, document_id)
        if current is None:
            run = self.latest(connection, document_id)
            fields, validation = self.candidate(run)
            self.append(connection, document_id, 0, run['id'], fields, validation)
            current = self.current(connection, document_id)
        return current

    def get(self, document_id, revision=None):
        self.base.document(document_id)
        # Lazy initialization is transactional and safe for simultaneous first opens.
        with self.base.transaction() as connection:
            head = self.ensure(connection, document_id)
            row = head if revision is None else connection.execute(
                'SELECT * FROM review_revisions WHERE document_id=? AND revision=?', (document_id,revision)).fetchone()
            if row is None:
                raise DocumentError('review_revision_not_found', 'No such review revision exists.', 404)
            latest = self.latest(connection, document_id)
            run = connection.execute('''SELECT r.id,j.source_key FROM extraction_runs r
                JOIN extraction_jobs j ON r.job_id=j.id WHERE r.id=?''', (row['source_run_id'],)).fetchone()
            from invoice_intelligence.persistence.matching import MatchingStore
            matching = MatchingStore(self.base).findings(connection, document_id)
        try:
            source = json.loads(self.base.artifact(run['source_key']).read_text())
        except (OSError, ValueError):
            raise DocumentError('review_source_unavailable', 'Pinned review source is unavailable.', 409) from None
        fields, validation = json.loads(row['fields_json']), json.loads(row['validation_json'])
        saved_checks = next((change['after'] for change in json.loads(row['changes_json'])
                            if change['field'] == 'matching_checks'), None)
        return {'document_id':document_id, 'revision':row['revision'], 'current_revision':head['revision'],
            'status':row['status'], 'source_run_id':row['source_run_id'],
            'newer_candidate_available':latest['id'] != row['source_run_id'],
            'fields':fields, 'validation':validation, 'confirmation':confirmation(validation),
            'matching':matching, 'matching_is_live':True,
            'po_exception_accepted':bool(next((change['after'] for change in json.loads(row['changes_json'])
                                             if change['field']=='po_exception_accepted'),False)),
            'matching_changed_since_confirmation':row['status']=='approved' and (not saved_checks or saved_checks['token']!=matching['token']),
            'pages':[{'page':p['page'], 'method':p['method'], 'image_url':f"/v1/documents/{document_id}/review/source/{run['id']}/{p['page']}"} for p in source['pages']],
            'actor':row['actor'], 'reason':row['reason'], 'created_at':row['created_at'],
            'acknowledged_warnings':bool(row['acknowledged_warnings'])}

    def history(self, document_id):
        self.base.document(document_id)
        with self.base.connect() as connection:
            rows = connection.execute('''SELECT revision,source_run_id,status,actor,reason,action,
                changes_json,acknowledged_warnings,created_at FROM review_revisions WHERE document_id=?
                ORDER BY revision DESC''', (document_id,)).fetchall()
        return [{key:row[key] for key in row.keys() if key != 'changes_json'} |
                {'changes':json.loads(row['changes_json'])} for row in rows]

    def check(self, connection, document_id, action, *, require_latest=True):
        if not action.actor.strip() or not action.reason.strip():
            raise DocumentError('review_reason_required', 'Enter a reviewer name and a meaningful reason.', 422)
        row = self.ensure(connection, document_id)
        if row['revision'] != action.expected_revision:
            raise DocumentError('review_conflict', 'Another action changed this invoice. Reload it before continuing.', 409)
        if require_latest and self.latest(connection,document_id)['id'] != row['source_run_id']:
            raise DocumentError('new_candidate_available', 'A newer extraction exists. Use latest extraction before editing or confirming.', 409)
        return row

    def update(self, document_id, request):
        self.base.document(document_id)
        with self.base.transaction() as connection:
            row = self.check(connection,document_id,request)
            before = InvoiceExtraction.model_validate_json(row['fields_json'])
            data = before.model_dump(mode='json')
            verified=set(request.verified_fields)
            allowed=set(HEADERS) | {f'{collection}[{i}].{name}' for collection in ['line_items','taxes'] for i,item in enumerate(getattr(before,collection)) for name in type(item).model_fields}
            if verified-allowed:
                raise DocumentError('invalid_verification_field','Verification paths must refer to current invoice fields.',422)
            if set(request.fields) - set(HEADERS):
                raise DocumentError('unknown_review_field', 'Only editable invoice fields may be changed.', 422)

            def change(original, value):
                explicit_absence = isinstance(value,str) and not value.strip()
                value = value.strip() if isinstance(value,str) else value
                value = None if value == '' else value
                if value is None and original['value'] is None and not explicit_absence:
                    return original
                return original | {'value':value, 'status':'corrected' if value is not None else 'missing',
                                   'reason':request.reason.strip() if value is not None else 'cleared_by_reviewer'}

            for name, value in request.fields.items():
                data[name] = change(data[name], value)
            for collection, model in [('line_items',ExtractedLineItem),('taxes',ExtractedTax)]:
                incoming = getattr(request,collection)
                if incoming is None:
                    continue
                existing, updated, used = data[collection], [], set()
                for item in incoming:
                    index = item.source_index
                    if index is not None and (index >= len(existing) or index in used):
                        raise DocumentError('invalid_source_index', 'Row source indices must be unique and refer to the current revision.', 422)
                    used.add(index) if index is not None else None
                    original = existing[index] if index is not None else model().model_dump(mode='json')
                    updated.append({name:change(original[name],value) for name,value in item.model_dump(exclude={'source_index'}).items()})
                data[collection] = updated
            try:
                after = InvoiceExtraction.model_validate(data)
            except ValidationError as error:
                raise DocumentError('invalid_review_value', str(error), 422) from None
            # Normalize first: retyping an equivalent decimal/date must not mark it corrected.
            for name in HEADERS:
                explicit_absence = isinstance(request.fields.get(name),str) and not request.fields[name].strip()
                if getattr(after,name).value == getattr(before,name).value and not explicit_absence and not (getattr(before,name).status=='proposed' and name in verified):
                    setattr(after,name,getattr(before,name))
            for collection in ['line_items','taxes']:
                incoming = getattr(request,collection)
                if incoming is not None:
                    for item, new in zip(incoming,getattr(after,collection)):
                        if item.source_index is not None:
                            old = getattr(before,collection)[item.source_index]
                            for name in type(old).model_fields:
                                incoming_value=getattr(item,name)
                                explicit_absence=isinstance(incoming_value,str) and not incoming_value.strip()
                                if getattr(old,name).value == getattr(new,name).value and not explicit_absence and not (getattr(old,name).status=='proposed' and f'{collection}[{item.source_index}].{name}' in verified):
                                    setattr(new,name,getattr(old,name))
            changes = []
            def diff(old,new,path=''):
                if isinstance(old,dict) and isinstance(new,dict):
                    if 'status' in old and 'value' in old:
                        if old != new:
                            change={'field':path,'before':old['value'],'after':new['value']}
                            if old['value']==new['value']:
                                change.update(before_status=old['status'],after_status=new['status'],before_reason=old['reason'],after_reason=new['reason'])
                            changes.append(change)
                    else:
                        for key in new:
                            diff(old.get(key),new[key], f'{path}.{key}' if path else key)
                elif isinstance(old,list) and isinstance(new,list) and len(old)==len(new):
                    for i,(a,b) in enumerate(zip(old,new)):
                        diff(a,b,f'{path}[{i}]')
                elif old != new:
                    changes.append({'field':path,'before':old,'after':new})
            diff(before.model_dump(mode='json'),after.model_dump(mode='json'))
            if changes:
                try:
                    validation = validate_extraction(after)
                except DecimalException:
                    raise DocumentError('invalid_review_value', 'Numeric values exceed the supported arithmetic precision or range.', 422) from None
                self.append(connection,document_id,row['revision']+1,row['source_run_id'],after,
                    validation,actor=request.actor.strip(),reason=request.reason.strip(),
                    action='corrected',changes=changes)
        return self.get(document_id)

    def decide(self, document_id, request):
        self.base.document(document_id)
        with self.base.transaction() as connection:
            row = self.check(connection,document_id,request,require_latest=request.decision=='approved')
            if row['status'] != 'pending':
                raise DocumentError('review_already_decided', 'This revision has already been decided. Save a correction to reopen it.', 409)
            validation = json.loads(row['validation_json'])
            gate = confirmation(validation)
            matching_changes = []
            if request.decision == 'approved':
                if not gate['allowed']:
                    raise DocumentError('confirmation_blocked', 'Resolve required fields and arithmetic errors before confirming.', 409)
                if not request.acknowledge_warnings:
                    raise DocumentError('warnings_not_acknowledged', 'Explicitly acknowledge the warnings and arithmetic assumptions before confirming.', 409)
                from invoice_intelligence.persistence.matching import MatchingStore
                matching = MatchingStore(self.base).findings(connection, document_id)
                significant = bool(matching['duplicates'] or matching['purchase_order']['status']!='not_requested')
                if request.matching_token != matching['token'] and (significant or request.matching_token is not None):
                    raise DocumentError('matching_conflict','Reload the invoice and inspect its current duplicate/PO checks before confirming.',409)
                if not matching['allowed']:
                    raise DocumentError('duplicate_confirmation_blocked','Resolve possible duplicates. A record marked as a duplicate cannot be confirmed.',409)
                if matching['requires_po_exception'] and not request.acknowledge_po_exception:
                    raise DocumentError('po_exception_not_acknowledged','Resolve the PO discrepancies or explicitly accept this PO exception with a reason.',409)
                matching_changes=[{'field':'matching_checks','before':None,'after':matching},
                                  {'field':'po_exception_accepted','before':False,'after':request.acknowledge_po_exception}]
                # A missing source image must never permit blind confirmation.
                run = connection.execute('SELECT source_key FROM extraction_jobs WHERE id=(SELECT job_id FROM extraction_runs WHERE id=?)',(row['source_run_id'],)).fetchone()
                try:
                    source_path = self.base.artifact(run['source_key'])
                    source = json.loads(source_path.read_text())
                    if not source['pages'] or any(not (source_path.parent / f"page_{p['page']}.png").is_file() for p in source['pages']):
                        raise OSError()
                except (OSError,ValueError,KeyError):
                    raise DocumentError('review_source_unavailable','Source pages must be available before confirmation.',409) from None
            self.append(connection,document_id,row['revision']+1,row['source_run_id'],
                InvoiceExtraction.model_validate_json(row['fields_json']),validation,status=request.decision,
                actor=request.actor.strip(),reason=request.reason.strip(),action=request.decision,
                acknowledged=request.acknowledge_warnings,changes=matching_changes)
        return self.get(document_id)

    def rebase(self, document_id, request):
        self.base.document(document_id)
        with self.base.transaction() as connection:
            row = self.check(connection,document_id,request,require_latest=False)
            latest = self.latest(connection,document_id)
            if latest['id'] == row['source_run_id']:
                raise DocumentError('no_new_candidate','This review already uses the latest extraction.',409)
            fields,validation = self.candidate(latest)
            self.append(connection,document_id,row['revision']+1,latest['id'],fields,validation,
                actor=request.actor.strip(),reason=request.reason.strip(),action='rebased',
                changes=[{'field':'source_run_id','before':row['source_run_id'],'after':latest['id']}])
        return self.get(document_id)

    def reopen(self, document_id, request):
        self.base.document(document_id)
        with self.base.transaction() as connection:
            row=self.check(connection,document_id,request,require_latest=False)
            if row['status']=='pending':
                raise DocumentError('review_already_pending','This invoice is already pending review.',409)
            self.append(connection,document_id,row['revision']+1,row['source_run_id'],
                InvoiceExtraction.model_validate_json(row['fields_json']),json.loads(row['validation_json']),
                actor=request.actor.strip(),reason=request.reason.strip(),action='reopened',
                changes=[{'field':'status','before':row['status'],'after':'pending'}])
        return self.get(document_id)

    def image(self, document_id, run_id, page):
        self.base.document(document_id)
        with self.base.connect() as connection:
            row = connection.execute('''SELECT j.source_key FROM extraction_runs r JOIN extraction_jobs j
                ON r.job_id=j.id WHERE r.id=? AND r.document_id=?''',(run_id,document_id)).fetchone()
        if row is None or page < 1:
            raise DocumentError('page_not_found','No matching source page.',404)
        source_path = self.base.artifact(row['source_key'])
        try:
            source = json.loads(source_path.read_text())
        except (OSError,ValueError):
            raise DocumentError('page_not_found','Pinned source is unavailable.',404) from None
        path = self.base.artifact((__import__('pathlib').Path(row['source_key']).parent / f'page_{page}.png').as_posix())
        if page > len(source['pages']) or not path.is_file():
            raise DocumentError('page_not_found','No matching source page.',404)
        return path
