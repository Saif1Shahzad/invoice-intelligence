"""Prepare an isolated mixed release demo. Does not change normal runtime data."""
import argparse
import csv
from datetime import datetime,timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.matching.purchase_orders import COLUMNS
from invoice_intelligence.workers.runner import run_once


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    settings=Settings(data_dir=ROOT/'data/runtime/release_demo'/stamp)
    report=ROOT/'reports/day7';report.mkdir(parents=True,exist_ok=True);cases=[]
    specifications=[('Clean PDF','data/raw/invoicebenchmark/output/pdf/INV-2026-0001.pdf'),
        ('Printed total mismatch','data/raw/invoicebenchmark/output/pdf/INV-2026-0002.pdf'),
        ('OCR copy of clean PDF','data/raw/invoicebenchmark/output/png/INV-2026-0001.png'),
        ('PO discrepancy fixture','data/raw/invoicebenchmark/output/pdf/INV-2026-0005.pdf'),
        ('Rotated scan','data/generated/day3/rotated_scan.png'),
        ('Multipage fixture','data/generated/day3/two_page_fixture.pdf'),
        ('Reserved unfamiliar layout','output/pdf/reserved-layout.pdf'),
        ('Blank image','data/generated/day3/blank.png'),
        ('Malformed PDF rejection','data/generated/day3/malformed.pdf')]
    missing=[path for _,path in specifications if not (ROOT/path).exists()]
    if missing:parser.error('Missing local demo sources: '+', '.join(missing)+'. The application itself does not require the benchmark dataset.')
    with TestClient(create_app(settings)) as client:
        for purpose,relative in specifications:
            path=ROOT/relative;mime='image/png' if path.suffix=='.png' else 'application/pdf'
            name=path.stem+('-ocr-copy' if mime=='image/png' and path.stem.startswith('INV-') else '')+path.suffix
            uploaded=client.post('/v1/documents',files={'file':(name,path.read_bytes(),mime)})
            if uploaded.status_code not in {200,202}:
                cases.append({'purpose':purpose,'filename':name,'accepted':False,'error':uploaded.json()});continue
            identifier=uploaded.json()['id']
            for _ in range(4):
                record=client.get('/v1/documents/'+identifier).json()
                if record['extraction'].get('fields') or record['extraction']['status']=='failed' or record['job']['status']=='failed':break
                run_once(settings,client.app.state.store)
            record=client.get('/v1/documents/'+identifier).json()
            cases.append({'purpose':purpose,'filename':name,'accepted':True,'document_id':identifier,'routing':record['extraction']['status']})
            print(purpose,record['extraction']['status'],flush=True)
        out=io.StringIO();writer=csv.writer(out);writer.writerow(COLUMNS)
        for case in [c for c in cases if c['purpose'] in {'Clean PDF','PO discrepancy fixture'}]:
            identifier=case['document_id'];review=client.get(f'/v1/documents/{identifier}/review').json();fields=review['fields'];different=case['purpose']=='PO discrepancy fixture'
            reference='PO-DEMO-DIFFERENCE' if different else 'PO-DEMO-MATCH'
            for i,row in enumerate(fields['line_items'],1):
                quantity=row['quantity']['value'];price=row['unit_price']['value']
                if different and i==1:quantity=str(Decimal(quantity)+1);price=str(Decimal(price)+1)
                writer.writerow([reference,fields['supplier_name']['value'],fields['currency']['value'],i,row['sku']['value'] or '',row['description']['value'],quantity,price])
            edited=client.patch(f'/v1/documents/{identifier}/review',json={'expected_revision':review['revision'],'actor':'Demo setup','reason':'Synthetic workflow fixture: manual PO assignment, not a printed extracted value.','fields':{'po_number':reference}})
            assert edited.status_code==200,edited.text
        raw=out.getvalue().encode();(report/'purchase_orders.csv').write_bytes(raw)
        response=client.post('/v1/purchase-orders/import',files={'file':('demo.csv',raw,'text/csv')},data={'actor':'Demo setup','reason':'Synthetic full-order matching and discrepancy examples.'});assert response.status_code==200,response.text
        # Replay every accepted source and prove document/job/run counts stay fixed.
        with client.app.state.store.connect() as c:
            before={name:c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ['documents','jobs','extraction_jobs','extraction_runs']}
        for (_,relative),case in zip(specifications,cases):
            if not case['accepted']:continue
            path=ROOT/relative;r=client.post('/v1/documents',files={'file':(case['filename'],path.read_bytes(),'image/png' if path.suffix=='.png' else 'application/pdf')});assert r.status_code==200 and r.json()['duplicate']
        with client.app.state.store.connect() as c:
            after={name:c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in before}
        assert before==after
    setup={'runtime':str(settings.data_dir),'cases':cases,'replay':{'before':before,'after':after,'unchanged':True}}
    (report/'demo_setup.json').write_text(json.dumps(setup,indent=2)+'\n')
    print('Fresh isolated demo ready. No review decisions or human timings were fabricated.')
    print(f'.venv/bin/python -m invoice_intelligence serve --port {args.port} --data-dir "{settings.data_dir}"')
    print(f'Open http://127.0.0.1:{args.port}/')

if __name__=='__main__':main()
