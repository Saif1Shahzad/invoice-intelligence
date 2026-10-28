"""Development-only integration/evaluation; runtime never receives answer keys.

Runs the 20 Day-2 development examples plus two OCR cases in a fresh isolated
SQLite runtime. Labels are loaded only AFTER each extraction completes.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import statistics
import sys
import time
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.workers.runner import run_once


def normalized(value):
    text=unicodedata.normalize('NFKC',str(value))
    return ' '.join(text.split())


def same(predicted, expected, field):
    if predicted is None:
        return False
    if field in {'subtotal','document_discount','shipping','tax_amount','tax_rate','total',
                 'conditional_discount_rate','quantity','unit_price','amount','discount_amount'}:
        try:return Decimal(str(predicted))==Decimal(str(expected))
        except InvalidOperation:return False
    return normalized(predicted)==normalized(expected)


def main():
    manifest=json.loads((ROOT/'data/splits/invoicebenchmark/inspection_sample.json').read_text())
    report=ROOT/'reports/day4'
    report.mkdir(parents=True,exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    settings=Settings(data_dir=ROOT/'data/runtime/day4_demo'/run_id)
    metrics=defaultdict(lambda:{'correct':0,'total':0})
    line_cells=defaultdict(lambda:{'correct':0,'total':0})
    absence={'correctly_empty':0,'total':0,'false_populated':0}
    line_counts={'true_rows':0,'predicted_rows':0,'missing_rows':0,'extra_rows':0,'exact_rows_on_available_labels':0}
    cases=[]
    def run_case(client,path,mime):
        started=time.monotonic()
        uploaded=client.post('/v1/documents',files={'file':(path.name,path.read_bytes(),mime)})
        assert uploaded.status_code in {200,202},uploaded.text
        identifier=uploaded.json()['id']
        for _ in range(5):
            record=client.get('/v1/documents/'+identifier).json()
            if record['extraction']['status'] in {'ready_for_confirmation','needs_review','failed'}:
                break
            if run_once(settings,client.app.state.store) is None:
                break
        record=client.get('/v1/documents/'+identifier).json()
        (report/(path.stem+'.'+('ocr' if mime=='image/png' else 'pdf')+'.result.json')).write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
        return record,time.monotonic()-started
    with TestClient(create_app(settings)) as client:
        for identifier in manifest['document_ids']:
            record,elapsed=run_case(client,ROOT/f'data/raw/invoicebenchmark/output/pdf/{identifier}.pdf','application/pdf')
            stage=record['extraction']
            # Ground truth enters evaluation here, never upload or extraction input.
            labels=json.loads((ROOT/f'data/labels/invoicebenchmark/development/{identifier}.json').read_text())
            fields=stage.get('fields') or {}
            for name,target in labels['fields'].items():
                predicted=fields.get(name,{})
                if target['score_extraction']:
                    metrics[name]['total']+=1
                    metrics[name]['correct']+=int(predicted.get('status')=='observed' and same(predicted.get('value'),target['value'],name))
                if target.get('score_absence'):
                    absence['total']+=1
                    empty=predicted.get('value') is None
                    absence['correctly_empty']+=int(empty)
                    absence['false_populated']+=int(not empty)
            predicted_rows=fields.get('line_items',[])
            targets=labels['line_items']
            line_counts['true_rows']+=len(targets)
            line_counts['predicted_rows']+=len(predicted_rows)
            line_counts['missing_rows']+=max(0,len(targets)-len(predicted_rows))
            line_counts['extra_rows']+=max(0,len(predicted_rows)-len(targets))
            for index,target_row in enumerate(targets):
                predicted=predicted_rows[index] if index<len(predicted_rows) else {}
                exact=True
                for name,target in target_row.items():
                    if target['score_extraction']:
                        cell=predicted.get(name,{})
                        correct=cell.get('status')=='observed' and same(cell.get('value'),target['value'],name)
                        line_cells[name]['total']+=1
                        line_cells[name]['correct']+=int(correct)
                        exact=exact and correct
                line_counts['exact_rows_on_available_labels']+=int(exact)
            issues=stage.get('validation',{}).get('issues',[])
            cases.append({'invoice_id':identifier,'document_id':record['id'],'status':stage['status'],
                'issue_codes':sorted({i['code'] for i in issues}),'observed_total':fields.get('total',{}).get('value'),
                'line_items':len(predicted_rows),'elapsed_seconds':round(elapsed,4)})
            print(identifier,stage['status'],len(predicted_rows),'rows',flush=True)
        ocr=[]
        for path in [ROOT/'data/raw/invoicebenchmark/output/png/INV-2026-0002.png',ROOT/'data/generated/day3/rotated_scan.png']:
            if path.exists():
                record,elapsed=run_case(client,path,'image/png')
                stage=record['extraction']
                ocr.append({'file':path.name,'status':stage['status'],'observed_total':stage.get('fields',{}).get('total',{}).get('value'),
                    'line_items':len(stage.get('fields',{}).get('line_items',[])),
                    'issue_codes':sorted({i['code'] for i in stage.get('validation',{}).get('issues',[])}),
                    'elapsed_seconds':round(elapsed,4)})
    header_correct=sum(item['correct'] for item in metrics.values())
    header_total=sum(item['total'] for item in metrics.values())
    cell_correct=sum(item['correct'] for item in line_cells.values())
    cell_total=sum(item['total'] for item in line_cells.values())
    summary={'run_id':run_id,'scope':'20 deliberately selected development PDFs, not held-out accuracy or calibrated confidence.',
        'runtime_dir':str(settings.data_dir),'header_values':{'correct':header_correct,'total':header_total,'accuracy':header_correct/header_total},
        'per_header_field':dict(metrics),'line_cells':{'correct':cell_correct,'total':cell_total,'accuracy':cell_correct/cell_total},
        'per_line_field':dict(line_cells),'line_rows':line_counts,'known_absent_header_fields':absence,
        'review_rate':sum(case['status']=='needs_review' for case in cases)/len(cases),
        'failed_documents':sum(case['status']=='failed' for case in cases),
        'median_demo_document_seconds':statistics.median(case['elapsed_seconds'] for case in cases),
        'provider_cost_usd':'0.00','cost_scope':'Local rules; no external requests. Compute and labor are not priced.',
        'cases':cases,'ocr_checks':ocr,
        'limitations':['Development sample used for debugging; not a generalization claim.',
            'Candidate labels are partial; unprinted/derived/unmapped/disputed values are excluded from positive value scoring.',
            'Line rows aligned by source order; exact rows are scored on available labeled cells, not all possible row attributes.',
            'No confidence calibration, reviewer timing, PO or business-duplicate metrics were measured here.']}
    (report/'development_metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({key:summary[key] for key in ['header_values','line_cells','line_rows','known_absent_header_fields','review_rate','failed_documents','ocr_checks']},indent=2))


if __name__=='__main__':main()
