"""Vercel container entry point: persistent Postgres/Blob, bounded HTTP work."""
import json
import os
from pathlib import Path
import tempfile
import time
from fastapi import Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from invoice_intelligence.config import Settings
from invoice_intelligence.domain.errors import DocumentError

os.environ['INVOICE_CLOUD']='vercel'
os.environ.setdefault('INVOICE_PUBLIC_ACCOUNTS','true')
# All durable bytes live in private Blob. This directory is only a verified cache.
os.environ.setdefault('INVOICE_DATA_DIR','/tmp/invoice-cache')
os.environ.setdefault('INVOICE_PROCESS_TIMEOUT','90')
os.environ.setdefault('INVOICE_MAX_UPLOAD_BYTES',str(3_500_000))
os.environ.setdefault('INVOICE_MAX_PAGES','3')
os.environ.setdefault('INVOICE_DEPLOYMENT','production')
os.environ.setdefault('INVOICE_PUBLIC_ORIGIN','https://invoice-intelligence-theta.vercel.app')
os.environ.setdefault('INVOICE_ALLOWED_HOSTS','invoice-intelligence-theta.vercel.app,localhost,127.0.0.1')

accounts=os.environ.get('INVOICE_ACCOUNTS_JSON','')
if not accounts or not os.environ.get('DATABASE_URL') or not os.environ.get('BLOB_READ_WRITE_TOKEN'):
    raise RuntimeError('Configure database, private storage and reviewer accounts before starting the live app.')
account_path=Path('/tmp/invoice-accounts.json')
account_path.write_text(accounts);account_path.chmod(0o600)
os.environ['INVOICE_AUTH_FILE']=str(account_path)

from invoice_intelligence.api.main import create_app,public_document
settings=Settings.from_env()
app=create_app(settings)


def process_document(store,identifier):
    """Complete at most two bounded stages while the invocation stays active.

    Durable lease fencing makes concurrent process calls harmless. If an
    invocation stops, saved queued work can be resumed explicitly from the UI.
    No thread is left running after an HTTP response.
    """
    from invoice_intelligence.workers.runner import run_once
    store.document(identifier)
    results=[]
    for _ in range(2):
        result=run_once(settings,store,document_id=identifier)
        if result is None:break
        results.append(result)
        if result['status'] in {'failed','queued','superseded'}:break
    return {'stages':results,'document':public_document(store,store.document(identifier),include_result=False)}

@app.post('/v1/documents/{document_id}/process')
def process_saved(document_id:str,request:Request):
    return process_document(request.app.state.store,document_id)

# Uploads are persisted first. The browser then requests processing and polls
# durable job state; closing the browser cannot erase an invoice or its history.
# The existing /review UI remains available for PO/duplicate/reopen controls.
static_root=Path(os.getenv('INVOICE_FRONTEND_DIR','/app/frontend-dist')).resolve()
@app.get('/assets/{asset_path:path}',include_in_schema=False)
def assets(asset_path:str):
    path=(static_root/'assets'/asset_path).resolve()
    if not path.is_relative_to(static_root/'assets') or not path.is_file():
        raise DocumentError('asset_not_found','Frontend asset not found.',404)
    return FileResponse(path)

# Replace only the root screen. Preserve every existing backend route, including
# /review (legacy administrative controls), /v1 and authenticated source files.
for route in list(app.router.routes):
    if getattr(route,'path',None) in {'/','/review'}:
        app.router.routes.remove(route)

@app.get('/legacy-review',include_in_schema=False)
def legacy_review():
    return FileResponse(Path(__file__).resolve().parents[1]/'web'/'index.html')

@app.middleware('http')
async def cloud_headers(request,call_next):
    response=await call_next(request)
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
    return response

@app.get('/{frontend_path:path}',include_in_schema=False)
def frontend(frontend_path:str):
    if frontend_path.startswith(('v1/','assets/','static/')) or frontend_path=='health':
        raise DocumentError('not_found','No matching route.',404)
    if frontend_path=='favicon.svg':return FileResponse(static_root/'favicon.svg',media_type='image/svg+xml')
    return FileResponse(static_root/'index.html')
