"""Prepare three DEVELOPMENT invoices for a manual browser review in an isolated store.

No review decisions are fabricated. Safe to rerun: a new timestamped runtime is used.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.workers.runner import run_once


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    runtime=ROOT/'data/runtime/day5_demo'/stamp
    settings=Settings(data_dir=runtime)
    cases=[]
    # These are already part of the frozen Day-2 development inspection sample.
    sample=json.loads((ROOT/'data/splits/invoicebenchmark/inspection_sample.json').read_text())['document_ids']
    with TestClient(create_app(settings)) as client:
        for suffix in ['0001','0002','0005']:
            invoice='INV-2026-'+suffix
            assert invoice in sample
            path=ROOT/f'data/raw/invoicebenchmark/output/pdf/{invoice}.pdf'
            response=client.post('/v1/documents',files={'file':(path.name,path.read_bytes(),'application/pdf')})
            assert response.status_code==202,response.text
            identifier=response.json()['id']
            run_once(settings,client.app.state.store)
            run_once(settings,client.app.state.store)
            record=client.get('/v1/documents/'+identifier).json()
            assert record['extraction']['run_id'],record
            cases.append({'filename':path.name,'document_id':identifier,'routing':record['extraction']['status']})
    report=ROOT/'reports/day5';report.mkdir(parents=True,exist_ok=True)
    (report/'demo_setup.json').write_text(json.dumps({'runtime':str(runtime),'cases':cases},indent=2)+'\n')
    print('Prepared a separate demo runtime. Your normal runtime was not edited.')
    print(f"INVOICE_DATA_DIR='{runtime}' .venv/bin/uvicorn invoice_intelligence.api.main:app --host 127.0.0.1 --port 8002")
    print('Open http://127.0.0.1:8002/ and select an invoice.')
    print('0002 contains a printed total mismatch; correct only after checking its source and calculations.')

if __name__=='__main__':
    main()
