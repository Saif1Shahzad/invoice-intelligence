"""Release timing, export gates, diagnostics, scoring and artifact failure handling."""
import csv
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.persistence.operations import OperationsStore
from invoice_intelligence.schemas.timing import SessionStart,TimeEvent
from invoice_intelligence.evaluation.scoring import score,readiness
from invoice_intelligence.workers.heartbeat import heartbeat
from invoice_intelligence.workers.runner import run_once
from test_day3_pipeline import text_pdf

class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=TemporaryDirectory();settings=Settings(data_dir=Path(cls.fixture.name))
        with TestClient(create_app(settings)) as client:
            cls.id=client.post('/v1/documents',files={'file':('invoice.pdf',text_pdf(),'application/pdf')}).json()['id']
            run_once(settings,client.app.state.store);run_once(settings,client.app.state.store)
            initial=client.get('/v1/documents/'+cls.id+'/review').json()
            r=client.patch('/v1/documents/'+cls.id+'/review',json={'expected_revision':initial['revision'],'actor':'Tester','reason':'Complete synthetic fixture','fields':{'tax_mode':'exclusive','issue_date':'2026-10-24'},'line_items':[{'description':'Paper cartons','quantity':'2','unit_price':'50','amount':'100'}]})
            assert r.status_code==200,r.text
    @classmethod
    def tearDownClass(cls):cls.fixture.cleanup()
    def setUp(self):
        self.temp=TemporaryDirectory();shutil.copytree(self.fixture.name,self.temp.name,dirs_exist_ok=True)
        self.settings=Settings(data_dir=Path(self.temp.name));self.client=TestClient(create_app(self.settings));self.client.__enter__();self.store=self.client.app.state.store;self.ops=OperationsStore(self.store)
        self.path='/v1/documents/'+self.id
    def tearDown(self):self.client.__exit__(None,None,None);self.temp.cleanup()
    def review(self):return self.client.get(self.path+'/review').json()
    def approve(self):
        r=self.review();response=self.client.post(self.path+'/review/decision',json={'expected_revision':r['revision'],'actor':'Tester','reason':'Checked synthetic record','decision':'approved','acknowledge_warnings':True,'matching_token':r['matching']['token']});self.assertEqual(response.status_code,200,response.text)
    def start(self,kind='human',now=100):
        return self.ops.start(self.id,SessionStart(session_id=uuid4(),actor='Tester',kind=kind),now=now)
    def test_timing_events_are_replay_safe_and_do_not_add_duplicate_time(self):
        s=self.start();e=TimeEvent(sequence=1,active_ms=3000)
        first=self.ops.record(self.id,s['id'],e,now=105)
        self.assertEqual(first['active_ms'],3000)
        self.assertEqual(self.ops.record(self.id,s['id'],e,now=106)['active_ms'],3000)
        ended=self.ops.record(self.id,s['id'],TimeEvent(sequence=2,active_ms=5000,ended=True),now=110)
        self.assertEqual(ended['active_ms'],5000);self.assertIsNotNone(ended['closed_at'])
        self.assertEqual(ended['end_status'],'pending')
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM review_time_events').fetchone()[0],2)
    def test_timing_rejects_conflicts_regressions_impossible_duration_and_closed_sessions(self):
        from invoice_intelligence.domain.errors import DocumentError
        s=self.start();self.ops.record(self.id,s['id'],TimeEvent(sequence=1,active_ms=1000),now=105)
        for e in [TimeEvent(sequence=1,active_ms=1001),TimeEvent(sequence=3,active_ms=2000),TimeEvent(sequence=2,active_ms=500),TimeEvent(sequence=2,active_ms=500000)]:
            with self.assertRaises(DocumentError):self.ops.record(self.id,s['id'],e,now=106)
        self.ops.record(self.id,s['id'],TimeEvent(sequence=2,active_ms=2000,ended=True),now=110)
        with self.assertRaises(DocumentError):self.ops.record(self.id,s['id'],TimeEvent(sequence=3,active_ms=2000),now=111)
    def test_session_start_replay_and_identity_conflict(self):
        request=SessionStart(session_id=uuid4(),actor='Tester')
        self.ops.start(self.id,request,now=100);self.ops.start(self.id,request,now=105)
        self.assertEqual(len(self.ops.sessions()),1)
        response=self.client.post(self.path+'/review-sessions',json={'session_id':str(request.session_id),'actor':'Someone else','kind':'human'})
        self.assertEqual(response.status_code,409)
    def test_timing_report_separates_automation_and_excludes_undecided_sessions(self):
        s=self.start();self.ops.record(self.id,s['id'],TimeEvent(sequence=1,active_ms=1000,ended=True),now=105)
        auto=self.start(kind='automated_demo',now=110);self.approve()
        self.ops.record(self.id,auto['id'],TimeEvent(sequence=1,active_ms=2000,ended=True),now=115)
        report=self.client.get('/v1/review-time-report').json()
        self.assertEqual(report['human']['completed_sessions'],0);self.assertIsNone(report['human']['median_active_seconds'])
        self.assertEqual(report['automated_demo']['median_active_seconds'],2)
    def test_session_api_rejects_wrong_document_and_invalid_payload(self):
        response=self.client.post(self.path+'/review-sessions',json={'session_id':str(uuid4()),'actor':' ','kind':'human'})
        self.assertEqual(response.status_code,422)
        response=self.client.post(self.path+'/review-sessions',json={'session_id':'invalid','actor':'Tester'})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.client.post(self.path+'/review-sessions/missing/events',json={'sequence':1,'active_ms':0}).status_code,404)
    def test_worker_liveness_expires_and_context_stops_heartbeat(self):
        self.ops.worker_tick('test-worker',now=100)
        self.assertTrue(self.ops.health(now=110)['worker_active']);self.assertFalse(self.ops.health(now=121)['worker_active'])
        with heartbeat(self.store):self.assertTrue(self.client.get('/health').json()['operations']['worker_active'])
        self.assertFalse(self.client.get('/health').json()['operations']['worker_active'])
    def test_exports_exclude_pending_and_reopened_invoices(self):
        self.assertEqual(self.client.get(self.path+'/export').status_code,409)
        self.approve();export=self.client.get(self.path+'/export');self.assertEqual(export.status_code,200)
        self.assertEqual(export.json()['records'][0]['fields']['total']['value'],'120.00')
        r=self.review();self.client.post(self.path+'/review/reopen',json={'expected_revision':r['revision'],'actor':'Tester','reason':'Check again'})
        self.assertEqual(self.client.get('/v1/exports/confirmed.json').json()['records'],[])
    def test_csv_exports_item_rows_and_neutralizes_formula_text(self):
        r=self.review();self.client.patch(self.path+'/review',json={'expected_revision':r['revision'],'actor':'Tester','reason':'Synthetic formula fixture','fields':{'invoice_number':'=HYPERLINK("bad")'}})
        self.approve();response=self.client.get('/v1/exports/confirmed.csv')
        rows=list(csv.DictReader(io.StringIO(response.text)))
        self.assertEqual(len(rows),1);self.assertTrue(rows[0]['invoice_number'].startswith("'="))
        self.assertEqual(rows[0]['line_amount'],'100')
    def test_stale_confirmation_is_excluded_from_exports(self):
        self.approve()
        # An unprocessed upload changes the documented coverage context.
        self.store.register(digest='pending',filename='pending.pdf',media_type='application/pdf',size_bytes=1,page_count=1,original_key='none')
        export=self.client.get('/v1/exports/confirmed.json').json()
        self.assertEqual(export['records'],[]);self.assertEqual(export['excluded_stale_confirmations'],[self.id])
    def test_missing_extraction_artifact_is_reported_in_queue_without_server_error(self):
        with self.store.connect() as c:key=c.execute('SELECT result_key FROM extraction_runs').fetchone()[0]
        (self.settings.data_dir/key).unlink()
        response=self.client.get('/v1/documents');self.assertEqual(response.status_code,200,response.text)
        stage=response.json()['documents'][0]['extraction'];self.assertEqual(stage['job']['error_code'],'extraction_artifact_unavailable')
    def test_missing_text_artifact_returns_actionable_error(self):
        document=self.store.document(self.id);(self.settings.data_dir/document['result_key']).unlink()
        response=self.client.get(self.path);self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['error']['code'],'text_artifact_unavailable')
    def test_explicit_absence_resolves_optional_ambiguity_without_silently_clearing_it(self):
        from invoice_intelligence.persistence.reviews import ReviewStore
        from invoice_intelligence.schemas.extraction import InvoiceExtraction
        from invoice_intelligence.domain.invoice_validation import validate_extraction
        r=self.review();fields=r['fields'];fields['po_number'].update(status='ambiguous',value=None,reason='conflicting_values')
        invoice=InvoiceExtraction.model_validate(fields)
        with self.store.transaction() as c:
            ReviewStore(self.store).append(c,self.id,r['revision']+1,r['source_run_id'],invoice,validate_extraction(invoice),actor='Fixture',reason='Synthetic ambiguous source',action='corrected')
        revision=self.review()['revision']
        def patch(value):return self.client.patch(self.path+'/review',json={'expected_revision':self.review()['revision'],'actor':'Tester','reason':'Checked source: no PO applies','fields':{'po_number':value}})
        untouched=patch(None);self.assertEqual(untouched.json()['revision'],revision)
        cleared=patch('');self.assertEqual(cleared.status_code,200,cleared.text)
        self.assertEqual(cleared.json()['fields']['po_number']['status'],'missing')
        self.assertTrue(cleared.json()['confirmation']['allowed'])
        history=self.client.get(self.path+'/review/history').json()['revisions']
        self.assertEqual(history[0]['changes'][0]['before_status'],'ambiguous')

    def test_release_pages_and_version_are_available(self):
        from invoice_intelligence import __version__
        self.assertEqual(self.client.get('/health').json()['version'],__version__)
        self.assertEqual(self.client.get('/evaluation').status_code,200)
        self.assertEqual(self.client.get('/static/timing.js').status_code,200)
        self.assertIn('multiple',self.client.get('/').text)

class ScoringTests(unittest.TestCase):
    def labels(self):
        return {'fields':{'total':{'value':'100','score_extraction':True,'score_absence':False}},'line_items':[{'description':{'value':'Paper','score_extraction':True},'amount':{'value':'100','score_extraction':True}}]}
    def fields(self):return {'total':{'status':'observed','value':'100.00'},'line_items':[{'description':{'status':'observed','value':'Paper'},'amount':{'status':'observed','value':'100'}}]}
    def test_failures_and_extra_rows_are_counted(self):
        failed=score(None,self.labels())['counts'];self.assertEqual(failed['header_total'],1);self.assertEqual(failed['header_correct'],0);self.assertEqual(failed['cell_total'],2)
        f=self.fields();f['line_items'].append(f['line_items'][0]);counts=score(f,self.labels())['counts']
        self.assertEqual(counts['cell_total'],6);self.assertEqual(counts['extra_rows'],1);self.assertEqual(counts['fully_scored_record_correct'],0)
    def test_decimal_normalization_and_absence_are_explicit(self):
        self.assertEqual(score(self.fields(),self.labels())['counts']['header_correct'],1)
        labels=self.labels();labels['fields']['shipping']={'value':None,'score_extraction':False,'score_absence':True}
        self.assertEqual(score(self.fields(),labels)['counts']['absence_correct'],1)
    def test_readiness_is_not_a_confidence_probability(self):
        from invoice_intelligence.evaluation.scoring import CRITICAL
        record={'extraction':{'fields':{n:{'status':'observed','value':'x','evidence':[{}]} for n in CRITICAL},'validation':{'routing':'ready_for_confirmation'}},'result':{'pages':[{'method':'ocr','mean_ocr_score':85}]}}
        self.assertTrue(readiness(record,80));self.assertFalse(readiness(record,90))
        record['extraction']['validation']['routing']='needs_review';self.assertFalse(readiness(record,0))

if __name__=='__main__':unittest.main()
