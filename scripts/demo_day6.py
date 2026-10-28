"""Small reproducible DEVELOPMENT benchmark and isolated Day-6 browser demo.

Labels enter scoring after extraction. PDF/PNG variants share a business label;
POs and human PO assignments below are explicitly synthetic workflow fixtures.
"""
from collections import defaultdict
import csv
from datetime import datetime,timezone
from decimal import Decimal
import io
from itertools import combinations
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.matching.purchase_orders import COLUMNS
from invoice_intelligence.matching.rules import VERSION,duplicate_rule,normalize
from invoice_intelligence.workers.runner import run_once
from demo_day4 import same


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    settings=Settings(data_dir=ROOT/'data/runtime/day6_demo'/stamp)
    report=ROOT/'reports/day6';report.mkdir(parents=True,exist_ok=True)
    cases=[];errors=[];totals=defaultdict(int);per_field=defaultdict(lambda:{'correct':0,'total':0})
    sample=json.loads((ROOT/'data/splits/invoicebenchmark/inspection_sample.json').read_text())['document_ids']
    specifications=[('INV-2026-0001','pdf'),('INV-2026-0025','pdf'),('INV-2026-0005','pdf'),('INV-2026-0001','png'),('INV-2026-0005','png')]
    with TestClient(create_app(settings)) as client:
        for invoice,kind in specifications:
            assert invoice in sample,'Only frozen development examples may enter this demo.'
            path=ROOT/f'data/raw/invoicebenchmark/output/{kind}/{invoice}.{kind}'
            filename=path.name if kind=='pdf' else invoice+'-image-copy.png'
            start=time.monotonic()
            upload=client.post('/v1/documents',files={'file':(filename,path.read_bytes(),'application/pdf' if kind=='pdf' else 'image/png')})
            assert upload.status_code==202,upload.text
            identifier=upload.json()['id']
            for _ in range(4):
                record=client.get('/v1/documents/'+identifier).json()
                if record['extraction'].get('run_id') or record['extraction']['status']=='failed':break
                run_once(settings,client.app.state.store)
            record=client.get('/v1/documents/'+identifier).json();elapsed=time.monotonic()-start
            candidate=record['extraction'].get('fields')
            cases.append({'business_id':invoice,'kind':kind,'document_id':identifier,'filename':filename,
                'extraction':record['extraction'],'elapsed_seconds':elapsed})
            # Labeled values are read only after the runtime has completed its extraction.
            labels=json.loads((ROOT/f'data/labels/invoicebenchmark/development/{invoice}.json').read_text())
            for name,target in labels['fields'].items():
                if target['score_extraction']:
                    observed=(candidate or {}).get(name,{})
                    correct=bool(observed.get('status')=='observed' and same(observed.get('value'),target['value'],name))
                    totals['header_correct']+=correct;totals['header_total']+=1
                    per_field[name]['correct']+=correct;per_field[name]['total']+=1
                    if not correct:errors.append({'file':filename,'field':name,'expected':target['value'],'observed':observed.get('value')})
                if target.get('score_absence'):
                    totals['absence_total']+=1
                    totals['absence_correct']+=((candidate or {}).get(name,{}).get('value') is None)
            predicted=(candidate or {}).get('line_items',[])
            totals['expected_rows']+=len(labels['line_items']);totals['predicted_rows']+=len(predicted)
            for index,target_row in enumerate(labels['line_items']):
                exact=True;scored=False
                for name,target in target_row.items():
                    if target['score_extraction']:
                        scored=True
                        observed=predicted[index].get(name,{}) if index<len(predicted) else {}
                        totals['line_cell_total']+=1
                        correct=bool(observed.get('status')=='observed' and same(observed.get('value'),target['value'],name))
                        totals['line_cell_correct']+=correct;exact=exact and correct
                        if not correct:errors.append({'file':filename,'field':f'line_items[{index}].{name}','expected':target['value'],'observed':observed.get('value')})
                totals['exact_rows_on_scored_cells']+=bool(exact and scored)
            print(filename,record['extraction']['status'],f'{elapsed:.3f}s',flush=True)
        pairs=[];counts={'tp':0,'fp':0,'tn':0,'fn':0};hard_negatives=0
        for a,b in combinations(cases,2):
            expected=a['business_id']==b['business_id']
            fields_a=a['extraction'].get('fields') or {};fields_b=b['extraction'].get('fields') or {}
            rule=duplicate_rule(fields_a,fields_b)
            predicted=rule is not None
            counts['tp' if expected and predicted else 'fn' if expected else 'fp' if predicted else 'tn']+=1
            same_supplier=normalize(fields_a.get('supplier_name',{}).get('value'))==normalize(fields_b.get('supplier_name',{}).get('value'))
            hard_negatives+=int(not expected and same_supplier)
            pairs.append({'a':a['filename'],'b':b['filename'],'expected_duplicate':expected,'flagged':predicted,'rule':rule})
        # Import synthetic POs based on the COMPUTER'S observed item values, not hidden labels.
        # These are fixtures for checking the matcher, not an independent PO accuracy dataset.
        out=io.StringIO();writer=csv.writer(out);writer.writerow(COLUMNS);po_cases=[]
        for invoice,reference,discrepancy in [('INV-2026-0001','PO-DEMO-MATCH',False),('INV-2026-0005','PO-DEMO-DIFFERENCE',True)]:
            case=next(c for c in cases if c['business_id']==invoice and c['kind']=='pdf')
            fields=case['extraction']['fields'];assert fields,'Demo extraction failed; cannot build a PO fixture.'
            for index,row in enumerate(fields['line_items']):
                quantity=row['quantity']['value'];price=row['unit_price']['value']
                assert quantity is not None and price is not None
                if discrepancy and index==0:quantity=str(Decimal(quantity)+1);price=str(Decimal(price)+1)
                writer.writerow([reference,fields['supplier_name']['value'],fields['currency']['value'],index+1,
                    row['sku']['value'] or '',row['description']['value'],quantity,price])
            # An explicit manual PO assignment is a review revision, never extraction evidence.
            review=client.get(f"/v1/documents/{case['document_id']}/review").json()
            edited=client.patch(f"/v1/documents/{case['document_id']}/review",json={
                'expected_revision':review['revision'],'actor':'Demo setup','reason':'Synthetic workflow fixture: manually assign a demo PO; no claim this reference was printed.',
                'fields':{'po_number':reference}})
            assert edited.status_code==200,edited.text
            po_cases.append({'document_id':case['document_id'],'filename':case['filename'],'expected':'discrepancy' if discrepancy else 'matched'})
        po_csv=out.getvalue().encode();(report/'purchase_orders.csv').write_bytes(po_csv)
        imported=client.post('/v1/purchase-orders/import',files={'file':('demo_orders.csv',po_csv,'text/csv')},data={'actor':'Demo setup','reason':'Synthetic PO fixtures, one matched and one with deliberate quantity/price differences.'})
        assert imported.status_code==200,imported.text
        assert client.post('/v1/purchase-orders/import',files={'file':('renamed.csv',po_csv,'text/csv')},data={'actor':'Demo setup','reason':'Replay check'}).json()['reused']
        for case in po_cases:
            result=client.get(f"/v1/documents/{case['document_id']}/matching").json()['purchase_order']
            case.update(observed=result['status'],issue_codes=sorted({i['code'] for i in result['issues']}))
            assert case['observed']==case['expected'],case
        # Exact bytes are reused even after review/PO changes.
        path=ROOT/'data/raw/invoicebenchmark/output/pdf/INV-2026-0001.pdf'
        replay=client.post('/v1/documents',files={'file':('renamed-again.pdf',path.read_bytes(),'application/pdf')})
        assert replay.status_code==200 and replay.json()['duplicate']
        combined_review=0;matching_review=0
        for case in cases:
            findings=client.get(f"/v1/documents/{case['document_id']}/matching").json()
            matching_review+=bool(findings['blockers'] or findings['requires_po_exception'])
            combined_review+=bool(findings['blockers'] or findings['requires_po_exception'] or case['extraction']['status']=='needs_review')
    cost=sum(Decimal(c['extraction'].get('usage',{}).get('provider_cost_usd','0')) for c in cases)
    metrics={'created_at':datetime.now(timezone.utc).isoformat(),'rule_version':VERSION,'runtime':str(settings.data_dir),
        'scope':'Five frozen development PDF/image variants; same template families. Not held-out evaluation or calibrated thresholds.',
        'documents':len(cases),'processing_failures':sum(not c['extraction'].get('fields') for c in cases),
        'accuracy_counts':dict(totals),'header_by_field':dict(per_field),
        'header_accuracy':totals['header_correct']/totals['header_total'] if totals['header_total'] else None,
        'line_cell_accuracy':totals['line_cell_correct']/totals['line_cell_total'] if totals['line_cell_total'] else None,
        'duplicates':counts|{'precision':counts['tp']/(counts['tp']+counts['fp']) if counts['tp']+counts['fp'] else None,
            'recall':counts['tp']/(counts['tp']+counts['fn']) if counts['tp']+counts['fn'] else None,
            'pairs':len(pairs),'same_supplier_negative_pairs':hard_negatives},
        'extraction_exception_review_rate':sum(c['extraction']['status']=='needs_review' for c in cases)/len(cases),
        'matching_exception_review_rate':matching_review/len(cases),'combined_exception_review_rate':combined_review/len(cases),
        'human_confirmation_rate':1.0,'median_pipeline_seconds':statistics.median(c['elapsed_seconds'] for c in cases),
        'provider_cost_usd':str(cost),'cost_notice':'Observed external-provider cost only; local compute/electricity/reviewer time excluded.',
        'measured_review_time_seconds':None,'review_time_notice':'Not measured in this automated benchmark; human timing remains Day 7.',
        'po_cases':po_cases,'po_fixture_notice':'Synthetic POs derived from observed values with known differences, not independent business records.',
        'cases':cases,'errors':errors,'labeled_pairs':pairs,'exact_upload_replay_reused':True}
    (report/'development_metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False)+'\n')
    (report/'demo_setup.json').write_text(json.dumps({'runtime':str(settings.data_dir),'cases':[{k:c[k] for k in ['document_id','filename','business_id','kind']} for c in cases]},indent=2)+'\n')
    print('Duplicate results:',metrics['duplicates'])
    print('Accuracy counts:',dict(totals))
    print('PO checks:',po_cases)
    print(f"INVOICE_DATA_DIR='{settings.data_dir}' .venv/bin/uvicorn invoice_intelligence.api.main:app --host 127.0.0.1 --port 8003")
    print('Open http://127.0.0.1:8003/. Possible duplicates are deliberately unresolved for your review.')

if __name__=='__main__':main()
