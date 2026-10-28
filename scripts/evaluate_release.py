"""Freeze predictions before opening calibration/test labels. No tuning on test."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.evaluation.scoring import score,readiness
from invoice_intelligence.domain.benchmark_mapping import map_benchmark_label
from invoice_intelligence.matching.rules import duplicate_rule,normalize
from invoice_intelligence.workers.runner import run_once


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_hashes():
    dirs=['extraction','ocr','ingestion','domain','matching','schemas']
    return {str(p.relative_to(ROOT)):sha(p) for name in dirs for p in sorted((ROOT/'src/invoice_intelligence'/name).rglob('*.py'))}
def ratio(a,b):return a/b if b else None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'reports/day7/evaluation');args=parser.parse_args()
    # Never overwrite the frozen predictions of a prior run.
    run=args.output/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');run.mkdir(parents=True)
    manifests={name:json.loads((ROOT/f'data/splits/invoicebenchmark/{name}.json').read_text()) for name in ['calibration','test']}
    expected=json.loads((ROOT/'docs/day2/split_summary.json').read_text())['manifests']
    for split in manifests:
        assert sha(ROOT/f'data/splits/invoicebenchmark/{split}.json')==expected[split],'Frozen split changed.'
    frozen=source_hashes();(run/'frozen-code.json').write_text(json.dumps(frozen,indent=2)+'\n')
    predictions={};runtimes={};replay={}
    for split,manifest in manifests.items():
        settings=Settings(data_dir=ROOT/'data/runtime/release_evaluation'/run.name/split);runtimes[split]=str(settings.data_dir)
        records=[]
        with TestClient(create_app(settings)) as client:
            for entry in manifest['documents']:
                for kind,mime in [('pdf','application/pdf'),('png','image/png')]:
                    path=ROOT/entry['paths'][kind]
                    assert sha(path)==entry['sha256'][kind],'Source bytes changed.'
                    start=time.monotonic();upload=client.post('/v1/documents',files={'file':(path.name,path.read_bytes(),mime)})
                    identifier=upload.json().get('id')
                    if upload.status_code not in {200,202}:
                        record={'extraction':{'status':'failed','fields':None},'upload_error':upload.json()}
                    else:
                        for _ in range(4):
                            record=client.get('/v1/documents/'+identifier).json()
                            stage=record.get('extraction',{})
                            if stage.get('fields') or stage.get('status')=='failed' or record['job']['status']=='failed':break
                            run_once(settings,client.app.state.store)
                        record=client.get('/v1/documents/'+identifier).json()
                    case={'business_id':entry['document_id'],'supplier':entry['supplier_group'],'layout':entry['layout'],'kind':kind,
                          'record':record,'elapsed_seconds':time.monotonic()-start,'source_sha256':entry['sha256'][kind]}
                    records.append(case)
                    print(split,entry['document_id'],kind,record.get('extraction',{}).get('status'),flush=True)
            before={table:None for table in ['documents','jobs','extraction_jobs','extraction_runs']}
            with client.app.state.store.connect() as c:
                before={table:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in before}
            for entry in manifest['documents']:
                path=ROOT/entry['paths']['pdf'];again=client.post('/v1/documents',files={'file':('renamed.pdf',path.read_bytes(),'application/pdf')})
                assert again.status_code==200 and again.json()['duplicate']
            with client.app.state.store.connect() as c:
                after={table:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in before}
            assert before==after;replay[split]={'before':before,'after':after,'unchanged':True}
        path=run/(split+'-predictions.json');path.write_text(json.dumps(records,ensure_ascii=False)+'\n');predictions[split]=records
    assert source_hashes()==frozen,'Extraction/rule code changed during prediction generation.'
    # Both sets of predictions are frozen on disk before either set of labels is opened.
    (run/'prediction-lock.json').write_text(json.dumps({split:sha(run/(split+'-predictions.json')) for split in predictions},indent=2)+'\n')
    splits={};scored={}
    for split,cases in predictions.items():
        totals=defaultdict(int);by_field=defaultdict(lambda:{'correct':0,'total':0});errors=[];layout_slices=defaultdict(lambda:defaultdict(int));scored[split]=[]
        for case in cases:
            entry=next(e for e in manifests[split]['documents'] if e['document_id']==case['business_id'])
            label_path=ROOT/entry['paths']['label'];assert sha(label_path)==entry['sha256']['label']
            labels=map_benchmark_label(json.loads(label_path.read_text()))
            scoring=score(case['record'].get('extraction',{}).get('fields'),labels);scored[split].append((case,scoring))
            for key,v in scoring['counts'].items():totals[key]+=v;layout_slices[case['layout']+' / '+case['kind']][key]+=v
            for name,counts in scoring['fields'].items():
                for key,v in counts.items():by_field[name][key]+=v
            if scoring['errors']:errors.append({'business_id':case['business_id'],'kind':case['kind'],'errors':scoring['errors']})
        counts={'tp':0,'fp':0,'tn':0,'fn':0};pairs=[];hard=0
        for a,b in combinations(cases,2):
            expected_dup=a['business_id']==b['business_id'];rule=duplicate_rule(a['record'].get('extraction',{}).get('fields') or {},b['record'].get('extraction',{}).get('fields') or {})
            flagged=rule is not None;counts['tp' if expected_dup and flagged else 'fn' if expected_dup else 'fp' if flagged else 'tn']+=1
            hard+=int(not expected_dup and a['supplier']==b['supplier'])
            if expected_dup or flagged:pairs.append({'a':a['business_id']+'/'+a['kind'],'b':b['business_id']+'/'+b['kind'],'expected':expected_dup,'flagged':flagged,'rule':rule})
        latencies=sorted(c['elapsed_seconds'] for c in cases)
        failures=sum(not c['record'].get('extraction',{}).get('fields') for c in cases)
        review_count=sum(c['record'].get('extraction',{}).get('status')=='needs_review' for c in cases)
        splits[split]={'documents':len(cases),'independent_business_invoices':len(manifests[split]['documents']),
            'failures':failures,'counts':dict(totals),'field_accuracy':dict(by_field),'slices':{k:dict(v) for k,v in layout_slices.items()},
            'row_precision':ratio(totals['exact_rows'],totals['predicted_rows']),'row_recall':ratio(totals['exact_rows'],totals['expected_rows']),
            'exception_review_rate':ratio(review_count,len(cases)-failures),'human_confirmation_required':True,
            'latency_p50_seconds':statistics.median(latencies),'latency_p95_seconds':latencies[max(0,math.ceil(.95*len(latencies))-1)],
            'provider_cost_usd':str(sum(Decimal(c['record'].get('extraction',{}).get('usage',{}).get('provider_cost_usd','0')) for c in cases)),
            'duplicates':counts|{'precision':ratio(counts['tp'],counts['tp']+counts['fp']),'recall':ratio(counts['tp'],counts['tp']+counts['fn']),
                                 'pair_count':len(cases)*(len(cases)-1)//2,'same_supplier_negative_pairs':hard},
            'errors':errors,'replay':replay[split],'labeled_duplicate_pairs_and_false_positives':pairs}
    sweep=[]
    for threshold in [0,60,80,90,95,98,100]:
        ready=[sc for case,sc in scored['calibration'] if readiness(case['record'],threshold)]
        sweep.append({'minimum_mean_ocr_score':threshold,'ready_documents':len(ready),'coverage':len(ready)/len(predictions['calibration']),
            'incorrect_on_scored_values':sum(not s['counts']['fully_scored_record_correct'] for s in ready),
            'critical_assessable':sum(s['counts']['critical_assessable'] for s in ready),
            'critical_errors':sum(s['counts']['critical_assessable'] and not s['counts']['critical_record_correct'] for s in ready)})
    eligible=[row for row in sweep if row['incorrect_on_scored_values']==0 and row['ready_documents']>0]
    chosen=max(eligible,key=lambda row:(row['coverage'],row['minimum_mean_ocr_score'])) if eligible else None
    test_ready=[sc for case,sc in scored['test'] if chosen and readiness(case['record'],chosen['minimum_mean_ocr_score'])]
    report={'status':'measured','version':'1.0.0','created_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Frozen supplier-held-out InvoiceBenchmark evaluation; layouts are shared, NOT unseen template families. PDF/image variants are correlated.',
        'splits':splits,'calibration_sweep':sweep,'selected_exploratory_policy':chosen,
        'selected_policy_test':{'ready_documents':len(test_ready),'incorrect_on_scored_values':sum(not s['counts']['fully_scored_record_correct'] for s in test_ready)},
        'policy_notice':'OCR score is a heuristic, not a probability. Sweep affects exploratory readiness only; all invoices require human confirmation. It does not change extraction code or auto-approve invoices.',
        'human_review_time':None,'source_code_hashes':frozen,'prediction_hashes':json.loads((run/'prediction-lock.json').read_text()),
        'manifest_hashes':{name:sha(ROOT/f'data/splits/invoicebenchmark/{name}.json') for name in manifests},
        'hardware':{'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version()},
        'tesseract_version':subprocess.run(['tesseract','--version'],capture_output=True,text=True).stdout.splitlines()[0],
        'limitations':['No unfamiliar-layout accuracy claim: supplier identities are held out but template families are shared.',
            'Scores cover labeled targets; implicit/unscored fields are not treated as independently verified. Extra rows are penalized.',
            'Duplicate positives are provided PDF/raster counterparts, not diverse physical rescans. Pairs are correlated.',
            'External-provider cost excludes local compute, electricity and reviewer labor.',
            'Human review timing is instrumented but a human/manual-entry comparison has not yet been collected.',
            'Calibration thresholds are exploratory; sample size does not establish a rare-error guarantee.'],
        'normalization':'Unicode NFKC + whitespace; exact Decimal value comparison; rows aligned by fixed source order, never by amounts.',
        'run_directory':str(run),'runtime_directories':runtimes}
    (run/'metrics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    (ROOT/'reports/day7/latest-evaluation.json').write_text(json.dumps({'report':str(run/'metrics.json')},indent=2)+'\n')
    public={k:v for k,v in report.items() if k not in {'source_code_hashes','run_directory','runtime_directories'}}
    for summary in public['splits'].values():summary.pop('errors',None);summary.pop('labeled_duplicate_pairs_and_false_positives',None)
    (ROOT/'src/invoice_intelligence/web/release-report.json').write_text(json.dumps(public,indent=2)+'\n')
    print('Measured report:',run/'metrics.json',flush=True)

if __name__=='__main__':main()
