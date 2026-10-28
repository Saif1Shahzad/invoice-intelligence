from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from invoice_intelligence.config import Settings
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.domain.reconciliation import reconcile
from invoice_intelligence.ingestion.service import ingest, UploadLimitMiddleware
from invoice_intelligence.persistence.store import Store
from invoice_intelligence.persistence.extractions import ExtractionStore
from invoice_intelligence.persistence.reviews import ReviewStore
from invoice_intelligence.persistence.matching import MatchingStore
from invoice_intelligence.matching.purchase_orders import MAX_CSV_BYTES, TEMPLATE
from invoice_intelligence.schemas.matching import DuplicateDecision
from invoice_intelligence.schemas.review import ReviewAction, ReviewUpdate, ReviewDecision
from invoice_intelligence.schemas.invoice import Invoice
from invoice_intelligence import __version__
from invoice_intelligence.persistence.operations import OperationsStore
from invoice_intelligence.persistence.exports import ExportStore
from invoice_intelligence.schemas.timing import SessionStart, TimeEvent


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def public_document(store, document, *, include_result=True):
    identifier = document['id']
    payload = {key: document[key] for key in ['id', 'sha256', 'filename', 'media_type', 'size_bytes', 'page_count', 'status']}
    payload['created_at'] = iso(document['created_at'])
    payload['updated_at'] = iso(document['updated_at'])
    payload['source_url'] = f'/v1/documents/{identifier}/file'
    payload['job'] = {'id': document['job_id'], 'status': document['job_status'],
        'attempts': document['attempts'], 'error_code': document['last_error_code'], 'error': document['last_error'],
        'attempt_history': document['attempt_history']}
    payload['extraction'] = ExtractionStore(store).summary(identifier, include_result=include_result)
    with store.connect() as connection:
        review = ReviewStore(store).current(connection, identifier)
    payload['review'] = {'status':review['status'], 'revision':review['revision']} if review else {'status':'not_started','revision':None}
    if include_result:
        result = store.result(document)
        if result:
            for page in result['pages']:
                page.pop('image_file', None)
                page['image_url'] = f"/v1/documents/{identifier}/pages/{page['page']}/image"
        payload['result'] = result
    return payload


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application):
        store = Store(settings)
        store.initialize()
        application.state.store = store
        if __import__("os").getenv("INVOICE_PUBLIC_ACCOUNTS")=="true":
            from invoice_intelligence.cloud.accounts import initialize
            initialize(store)
        try:
            yield
        finally:
            store.close()

    application = FastAPI(title='Invoice Intelligence', version=__version__, lifespan=lifespan,
        description='Human-reviewed invoice/receipt extraction. Groq is opt-in; authenticated deployment requires HTTPS.')
    from invoice_intelligence.security import install_security, audit_identity
    install_security(application,settings)
    application.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_upload_bytes)
    web = Path(__file__).resolve().parents[1] / 'web'
    application.mount('/static', StaticFiles(directory=web), name='static')

    @application.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @application.get('/', include_in_schema=False)
    @application.get('/review', include_in_schema=False)
    def review_screen():
        return FileResponse(web / 'index.html')

    @application.exception_handler(DocumentError)
    async def document_error(request, error):
        return JSONResponse({'error': {'code': error.code, 'message': error.message}}, status_code=error.status_code)

    @application.get('/health')
    def health(request: Request):
        return {'status': 'ok', 'version':__version__, 'stage': 'groq_reviewed_pilot', 'database': 'postgresql_cloud' if __import__('os').getenv('INVOICE_CLOUD')=='vercel' else 'sqlite_local_single_user',
            'processing_mode':'request_driven' if __import__('os').getenv('INVOICE_CLOUD')=='vercel' else 'background_worker',
            'max_pages':settings.max_pages,'max_upload_bytes':settings.max_upload_bytes,
            'extraction_provider': settings.extraction_provider,
            'ocr_available': shutil.which(settings.tesseract_cmd) is not None,
            'authentication_enabled':bool(settings.auth_file),'deployment':settings.deployment,
            'provider_model':settings.groq_model if settings.extraction_provider=='groq' else None,
            'operations':OperationsStore(request.app.state.store).health()}

    @application.get('/v1/session')
    def current_session(request: Request):
        principal=getattr(request.state,'principal',None)
        return {'authenticated':bool(principal),'user':principal['name'] if principal else None,
                'role':principal['role'] if principal else 'admin'}

    @application.get('/v1/release-report')
    def release_report():
        import json
        path=web/'release-report.json'
        return json.loads(path.read_text()) if path.exists() else {'status':'not_run','version':__version__}

    @application.get('/v1/improvement-report')
    def improvement_report():
        import json
        path=web/'improvement-report.json'
        return json.loads(path.read_text()) if path.exists() else {'status':'evaluation_running'}

    @application.get('/improvement',include_in_schema=False)
    def improvement_screen():
        return FileResponse(web/'improvement.html')

    @application.get('/evaluation', include_in_schema=False)
    def evaluation_screen():
        return FileResponse(web/'evaluation.html')

    @application.get('/v1/exports/confirmed.csv')
    def confirmed_csv(request: Request):
        content,count,excluded=ExportStore(request.app.state.store).csv()
        return Response(content,media_type='text/csv',headers={
            'Content-Disposition':'attachment; filename="confirmed_invoices.csv"',
            'X-Exported-Invoices':str(count),'X-Excluded-Stale-Confirmations':str(excluded)})

    @application.get('/v1/exports/confirmed.xlsx')
    def confirmed_excel(request: Request):
        from invoice_intelligence.persistence.xlsx import confirmed_workbook
        return Response(confirmed_workbook(request.app.state.store),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="confirmed_invoices.xlsx"'})

    @application.get('/v1/exports/confirmed.json')
    def confirmed_json(request: Request):
        return JSONResponse(ExportStore(request.app.state.store).approved(),headers={
            'Content-Disposition':'attachment; filename="confirmed_invoices.json"'})

    @application.post('/v1/validate')
    def validate_invoice(invoice: Invoice):
        issues = reconcile(line_nets=[item.net_amount for item in invoice.line_items],
            subtotal=invoice.subtotal, discount=invoice.document_discount,
            shipping=invoice.shipping, tax=invoice.tax, total=invoice.total,
            tolerance=invoice.rounding_tolerance)
        return {'arithmetic_issues': issues,
            'status': 'needs_review' if issues else 'requires_human_confirmation',
            'scope': 'Header arithmetic only; not connected to uploaded text or structured extraction yet.'}

    @application.post('/v1/documents', status_code=202)
    def upload_document(request: Request, response: Response, file: Annotated[UploadFile, File()],
                        idempotency_key: Annotated[str | None, Header()] = None):
        store = request.app.state.store
        try:
            identifier, duplicate = ingest(file, idempotency_key, settings, store)
        finally:
            file.file.close()
        response.status_code = 200 if duplicate else 202
        response.headers['Location'] = f'/v1/documents/{identifier}'
        return public_document(store, store.document(identifier), include_result=False) | {'duplicate': duplicate}

    @application.get('/v1/documents')
    def list_documents(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                       offset: Annotated[int, Query(ge=0)] = 0):
        store = request.app.state.store
        documents=store.list_documents(limit,offset)
        matching=MatchingStore(store).summaries([d['id'] for d in documents])
        return {'documents': [public_document(store, d, include_result=False) |
                              {'matching_summary':matching[d['id']]} for d in documents]}

    @application.get('/v1/documents/{document_id}')
    def get_document(document_id: str, request: Request):
        store = request.app.state.store
        return public_document(store, store.document(document_id))

    @application.get('/v1/documents/{document_id}/file')
    def get_original(document_id: str, request: Request):
        document = request.app.state.store.document(document_id)
        path = request.app.state.store.artifact(document['original_key'])
        if not path.is_file():
            raise DocumentError('original_missing', 'Stored source file is unavailable.', 404)
        return FileResponse(path, media_type=document['media_type'], filename=document['filename'])

    @application.get('/v1/documents/{document_id}/pages/{page_number}/image')
    def get_page(document_id: str, page_number: int, request: Request):
        store = request.app.state.store
        document = store.document(document_id)
        result = store.result(document)
        if not result or not 1 <= page_number <= len(result['pages']):
            raise DocumentError('page_not_found', 'No processed page exists with this number.', 404)
        path = store.artifact((Path(document['result_key']).parent / f'page_{page_number}.png').as_posix())
        if not path.is_file():
            raise DocumentError('page_not_found', 'Processed page image is unavailable.', 404)
        return FileResponse(path, media_type='image/png')

    @application.post('/v1/documents/{document_id}/retry', status_code=202)
    def retry_document(document_id: str, request: Request):
        store = request.app.state.store
        store.retry(document_id)
        return public_document(store, store.document(document_id), include_result=False)

    @application.post('/v1/documents/{document_id}/extract', status_code=202)
    def extract_document(document_id: str, request: Request, response: Response):
        extraction_store = ExtractionStore(request.app.state.store)
        identifier, reused = extraction_store.enqueue(document_id)
        response.status_code = 200 if reused else 202
        return extraction_store.summary(document_id) | {'reused': reused, 'requested_job_id': identifier}

    @application.get('/v1/documents/{document_id}/extractions')
    def extraction_history(document_id: str, request: Request):
        return {'runs': ExtractionStore(request.app.state.store).history(document_id)}

    @application.post('/v1/documents/{document_id}/extract/retry', status_code=202)
    def retry_extraction(document_id: str, request: Request):
        extraction_store = ExtractionStore(request.app.state.store)
        job=extraction_store.summary(document_id,include_result=False).get('job')
        if job and (job['provider'],job['extractor_version'])!=(extraction_store.provider,extraction_store.version):
            raise DocumentError('extractor_configuration_changed','The provider/model configuration changed. Use Extract with configured provider to create a new candidate.',409)
        extraction_store.retry(document_id)
        return extraction_store.summary(document_id)

    @application.get('/v1/documents/{document_id}/review')
    def get_review(document_id: str, request: Request, revision: Annotated[int | None, Query(ge=0)] = None):
        return ReviewStore(request.app.state.store).get(document_id, revision)

    @application.patch('/v1/documents/{document_id}/review')
    def update_review(document_id: str, change: ReviewUpdate, request: Request):
        return ReviewStore(request.app.state.store).update(document_id, audit_identity(request,change))

    @application.post('/v1/documents/{document_id}/review/decision')
    def decide_review(document_id: str, decision: ReviewDecision, request: Request):
        return ReviewStore(request.app.state.store).decide(document_id, audit_identity(request,decision))

    @application.post('/v1/documents/{document_id}/review/rebase')
    def rebase_review(document_id: str, change: ReviewAction, request: Request):
        return ReviewStore(request.app.state.store).rebase(document_id, audit_identity(request,change))

    @application.post('/v1/documents/{document_id}/review/reopen')
    def reopen_review(document_id: str, change: ReviewAction, request: Request):
        return ReviewStore(request.app.state.store).reopen(document_id, audit_identity(request,change))

    @application.get('/v1/documents/{document_id}/review/history')
    def review_history(document_id: str, request: Request):
        return {'revisions':ReviewStore(request.app.state.store).history(document_id)}

    @application.get('/v1/documents/{document_id}/export')
    def export_document(document_id: str, request: Request):
        request.app.state.store.document(document_id)
        return JSONResponse(ExportStore(request.app.state.store).approved(document_id),headers={
            'Content-Disposition':'attachment; filename="reviewed_invoice.json"'})

    @application.post('/v1/documents/{document_id}/review-sessions')
    def start_session(document_id: str, session: SessionStart, request: Request):
        return OperationsStore(request.app.state.store).start(document_id,audit_identity(request,session))

    @application.get('/v1/documents/{document_id}/review-sessions')
    def list_sessions(document_id: str, request: Request):
        request.app.state.store.document(document_id)
        return {'sessions':OperationsStore(request.app.state.store).sessions(document_id),
                'notice':'Browser-reported active time. Parallel tabs may overlap; human and automated sessions are separate.'}

    @application.post('/v1/documents/{document_id}/review-sessions/{session_id}/events')
    def timing_event(document_id: str, session_id: str, event: TimeEvent, request: Request):
        ops=OperationsStore(request.app.state.store)
        principal=getattr(request.state,'principal',None)
        if principal and principal['role']!='admin' and ops.session(document_id,session_id)['actor']!=principal['name']:
            raise DocumentError('session_owner_required','Only the timer owner or an administrator may update it.',403)
        return ops.record(document_id,session_id,event)

    @application.get('/v1/review-time-report')
    def timing_report(request: Request):
        import statistics
        sessions=OperationsStore(request.app.state.store).sessions()
        result={}
        for kind in ['human','automated_demo']:
            closed=[s for s in sessions if s['kind']==kind and s['closed_at'] is not None]
            group=[s for s in closed if s['end_status'] in {'approved','rejected'}]
            result[kind]={'completed_sessions':len(group),
                'closed_without_decision':len(closed)-len(group),
                'median_active_seconds':statistics.median([s['active_ms']/1000 for s in group]) if group else None}
        return result | {'sessions':sessions,'notice':'Self-reported reviewer identity and browser activity; overlapping sessions are not a paired manual-entry experiment.'}

    @application.get('/v1/documents/{document_id}/review/source/{run_id}/{page_number}')
    def review_source(document_id: str, run_id: str, page_number: int, request: Request):
        return FileResponse(ReviewStore(request.app.state.store).image(document_id,run_id,page_number), media_type='image/png')

    @application.get('/v1/documents/{document_id}/matching')
    def matching_findings(document_id: str, request: Request):
        return MatchingStore(request.app.state.store).get(document_id)

    @application.post('/v1/documents/{document_id}/duplicates/decision')
    def duplicate_decision(document_id: str, decision: DuplicateDecision, request: Request):
        return MatchingStore(request.app.state.store).decide_duplicate(document_id, audit_identity(request,decision))

    @application.get('/v1/documents/{document_id}/duplicates/history')
    def duplicate_history(document_id: str, request: Request):
        return {'decisions':MatchingStore(request.app.state.store).duplicate_history(document_id)}

    @application.get('/v1/purchase-orders/template')
    def po_template():
        return Response(TEMPLATE,media_type='text/csv',headers={'Content-Disposition':'attachment; filename="purchase_orders_template.csv"'})

    @application.post('/v1/purchase-orders/import')
    def import_purchase_orders(request: Request, file: Annotated[UploadFile, File()],
                              actor: Annotated[str, Form(min_length=1,max_length=80)],
                              reason: Annotated[str, Form(min_length=1,max_length=1000)]):
        try:
            raw=file.file.read(MAX_CSV_BYTES+1)
        finally:
            file.file.close()
        principal=getattr(request.state,'principal',None)
        return MatchingStore(request.app.state.store).import_csv(raw,file.filename or 'orders.csv',principal['name'] if principal else actor,reason)

    @application.get('/v1/purchase-orders')
    def list_purchase_orders(request: Request):
        return {'purchase_orders':MatchingStore(request.app.state.store).orders()}

    @application.get('/v1/purchase-orders/{reference}/history')
    def po_history(reference: str, request: Request):
        return {'versions':MatchingStore(request.app.state.store).po_history(reference)}

    return application


app = create_app()
