"""Human review lifecycle, revision fencing, source provenance and API boundaries."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.extraction.source import verify_evidence
from invoice_intelligence.schemas.extraction import InvoiceExtraction
from invoice_intelligence.workers.runner import run_once
from test_day3_pipeline import text_pdf

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise the actual pipeline once; every test then receives an isolated copy.
        cls.fixture=TemporaryDirectory()
        settings=Settings(data_dir=Path(cls.fixture.name))
        with TestClient(create_app(settings)) as client:
            identifier=client.post('/v1/documents',files={'file':('review.pdf',text_pdf(),'application/pdf')}).json()['id']
            run_once(settings,client.app.state.store)
            run_once(settings,client.app.state.store)
            cls.fixture_id=identifier
    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()
    def setUp(self):
        import shutil
        self.temp=TemporaryDirectory()
        shutil.copytree(self.fixture.name,self.temp.name,dirs_exist_ok=True)
        self.settings=Settings(data_dir=Path(self.temp.name))
        self.client=TestClient(create_app(self.settings));self.client.__enter__()
        self.store=self.client.app.state.store;self.id=self.fixture_id
        self.path=f'/v1/documents/{self.id}/review'
    def tearDown(self):
        self.client.__exit__(None,None,None);self.temp.cleanup()
    def review(self):
        response=self.client.get(self.path)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()
    def action(self,revision=None,**extra):
        return {'expected_revision':self.review()['revision'] if revision is None else revision,
                'actor':'Saif','reason':'Checked against the source invoice',**extra}
    def patch(self,**extra):
        return self.client.patch(self.path,json=self.action(**extra))
    def decide(self,decision='approved',**extra):
        return self.client.post(self.path+'/decision',json=self.action(decision=decision,acknowledge_warnings=True,**extra))
    def make_complete(self):
        # Fixture header may omit tax basis; the reviewer explicitly establishes it.
        r=self.patch(fields={'tax_mode':'exclusive','issue_date':'2026-10-23'},line_items=[{
            'description':'Paper cartons','quantity':'2','unit_price':'50.00','amount':'100.00'}])
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['confirmation']['allowed'],r.json()['validation'])
        return r.json()
    def test_real_pipeline_review_source_and_static_ui(self):
        r=self.review()
        self.assertEqual(r['revision'],0)
        self.assertEqual(r['fields']['total']['value'],'120.00')
        self.assertEqual(self.client.get(r['pages'][0]['image_url']).headers['content-type'],'image/png')
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertIn('Review workspace',self.client.get('/').text)
        self.assertIn('nosniff',self.client.get('/static/app.js').headers['x-content-type-options'])
        self.assertIn("script-src 'self'",self.client.get('/').headers['content-security-policy'])
    def test_correction_revalidation_candidate_preservation_and_restart(self):
        self.make_complete()
        candidate=self.client.get(f'/v1/documents/{self.id}').json()['extraction']['fields']
        original=self.review()['fields']['total']
        r=self.patch(fields={'total':'999.99'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['revision'],2)
        self.assertEqual(r.json()['fields']['total']['status'],'corrected')
        self.assertEqual(r.json()['fields']['total']['evidence'],original['evidence'])
        self.assertIn('total_mismatch',[i['code'] for i in r.json()['validation']['issues']])
        self.assertEqual(self.client.get(f'/v1/documents/{self.id}').json()['extraction']['fields'],candidate)
        with TestClient(create_app(self.settings)) as restarted:
            self.assertEqual(restarted.get(self.path).json(),self.review())
        hist=self.client.get(self.path+'/history').json()['revisions']
        self.assertEqual(hist[0]['changes'],[{'field':'total','before':'120.00','after':'999.99'}])
        self.assertEqual(hist[0]['actor'],'Saif')
        self.assertEqual(self.client.get(self.path+'?revision=0').json()['fields']['total'],original)
    def test_bad_arithmetic_cannot_be_confirmed_even_if_acknowledged(self):
        self.make_complete();self.patch(fields={'total':'999.99'})
        r=self.decide();self.assertEqual(r.status_code,409)
        self.assertEqual(r.json()['error']['code'],'confirmation_blocked')
        self.assertEqual(self.review()['status'],'pending')
    def test_confirmation_persistence_replay_and_reopen_on_edit(self):
        r=self.make_complete();revision=r['revision']
        body=self.action(revision,decision='approved',acknowledge_warnings=True)
        approved=self.client.post(self.path+'/decision',json=body)
        self.assertEqual(approved.status_code,200,approved.text)
        self.assertEqual(approved.json()['status'],'approved')
        self.assertEqual(self.client.post(self.path+'/decision',json=body).status_code,409)
        self.assertEqual(self.review()['revision'],revision+1)
        self.assertEqual(self.client.get('/v1/documents').json()['documents'][0]['review']['status'],'approved')
        changed=self.patch(fields={'supplier_name':'Verified supplier'})
        self.assertEqual(changed.json()['status'],'pending')
        self.assertEqual(self.client.get(self.path+'?revision='+str(revision+1)).json()['status'],'approved')
    def test_rejection_is_possible_for_unresolved_invoice(self):
        r=self.decide('rejected');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['status'],'rejected')
        self.assertEqual(self.decide('rejected').status_code,409)
    def test_stale_tabs_and_concurrent_edits_cannot_overwrite(self):
        self.review()
        def save(value):
            return self.client.patch(self.path,json=self.action(0,fields={'invoice_number':value}))
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(save,['A-001','B-002']))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409])
        self.assertEqual(self.review()['revision'],1)
        self.assertEqual(len(self.client.get(self.path+'/history').json()['revisions']),2)
    def test_initial_open_is_safe_for_concurrent_readers(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.client.get(self.path),range(4)))
        self.assertTrue(all(r.status_code==200 for r in results))
        self.assertEqual(len(self.client.get(self.path+'/history').json()['revisions']),1)
    def test_equivalent_decimal_is_noop_and_preserves_observation(self):
        r=self.patch(fields={'total':'120.0'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['revision'],0)
        self.assertEqual(r.json()['fields']['total']['status'],'observed')
    def test_invalid_values_are_atomic(self):
        for fields in [{'total':'NaN'},{'total':'hello'},{'issue_date':'2026-99-99'}, {'currency':'EURO'},{'tax_mode':'unknown'}, {'document_id':'injected'}]:
            with self.subTest(fields=fields):
                response=self.patch(fields=fields)
                self.assertEqual(response.status_code,422,response.text)
                self.assertEqual(self.review()['revision'],0)
    def test_unknown_fields_boxes_and_blank_actor_are_rejected(self):
        for extra in [{'evidence':[]},{'actor':'  '},{'reason':' '},{'fields':{'total':{'value':'1','evidence':[]}}}]:
            body=self.action(**extra)
            r=self.client.patch(self.path,json=body)
            self.assertEqual(r.status_code,422,r.text)
    def test_remove_add_and_move_rows_preserve_context_by_source_index(self):
        self.make_complete()
        original=self.review()['fields']['line_items'][0]
        row={name:f['value'] for name,f in original.items()}
        added={'source_index':None,'description':'Manual shipping item','quantity':'1','unit_price':'5','amount':'5'}
        r=self.patch(line_items=[added,{'source_index':0,**row}])
        self.assertEqual(r.status_code,200,r.text)
        items=r.json()['fields']['line_items']
        self.assertEqual(items[1],original)
        self.assertEqual(items[0]['description']['status'],'corrected')
        self.assertEqual(items[0]['description']['evidence'],[])
        r=self.patch(line_items=[{'source_index':1,**row}])
        self.assertEqual(r.json()['fields']['line_items'],[original])
    def test_invalid_or_repeated_source_indices_rejected(self):
        for rows in [[{'source_index':9}],[{'source_index':0},{'source_index':0}]]:
            self.assertEqual(self.patch(line_items=rows).status_code,422)
            self.assertEqual(self.review()['revision'],0)
    def test_clear_required_field_blocks_confirmation(self):
        self.make_complete()
        r=self.patch(fields={'invoice_number':None})
        self.assertEqual(r.json()['fields']['invoice_number']['status'],'missing')
        self.assertFalse(r.json()['confirmation']['allowed'])
        self.assertEqual(self.decide().status_code,409)
    def test_warning_acknowledgement_required(self):
        self.make_complete()
        self.patch(fields={'document_type':'credit_note'})
        r=self.client.post(self.path+'/decision',json=self.action(decision='approved',acknowledge_warnings=False))
        self.assertEqual(r.status_code,409)
        self.assertEqual(r.json()['error']['code'],'warnings_not_acknowledged')
        self.assertEqual(self.decide().status_code,200)
    def test_assumptions_require_acknowledgement_even_without_warnings(self):
        self.make_complete()
        self.assertFalse(self.review()['validation']['issues'])
        r=self.client.post(self.path+'/decision',json=self.action(decision='approved'))
        self.assertEqual(r.status_code,409)
        self.assertEqual(r.json()['error']['code'],'warnings_not_acknowledged')
    def test_extreme_numeric_values_return_actionable_error_without_revision(self):
        self.make_complete()
        before=self.review()['revision']
        r=self.patch(fields={'subtotal':'1e999999'})
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(self.review()['revision'],before)
    def test_history_cannot_be_updated_or_deleted(self):
        self.review()
        with self.store.connect() as connection:
            for query in ['UPDATE review_revisions SET actor="changed"','DELETE FROM review_revisions']:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(query)
    def newer_candidate(self):
        # Simulate a new successful extractor version with the same pinned source.
        with self.store.transaction() as c:
            job=dict(c.execute('SELECT * FROM extraction_jobs').fetchone())
            run=dict(c.execute('SELECT * FROM extraction_runs').fetchone())
            c.execute('''INSERT INTO extraction_jobs(id,document_id,provider,extractor_version,source_key,source_digest,status,created_at,updated_at)
                VALUES ('new-job',?,'local','future-version',?,?,'succeeded',9999999999,9999999999)''',(self.id,job['source_key'],job['source_digest']))
            c.execute('INSERT INTO extraction_runs VALUES (?,?,?,?,?)',('new-run','new-job',self.id,run['result_key'],9999999999))
    def test_new_extraction_cannot_silently_replace_saved_corrections(self):
        self.make_complete();self.patch(fields={'supplier_name':'Manual supplier'})
        revision=self.review()['revision'];self.newer_candidate()
        self.assertTrue(self.review()['newer_candidate_available'])
        self.assertEqual(self.review()['fields']['supplier_name']['value'],'Manual supplier')
        self.assertEqual(self.patch(fields={'invoice_number':'CHANGED'}).status_code,409)
        self.assertEqual(self.decide().status_code,409)
        r=self.client.post(self.path+'/rebase',json=self.action())
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['source_run_id'],'new-run')
        self.assertEqual(r.json()['status'],'pending')
        self.assertEqual(self.client.get(self.path+f'?revision={revision}').json()['fields']['supplier_name']['value'],'Manual supplier')
    def test_missing_source_blocks_confirmation(self):
        self.make_complete()
        document=self.store.document(self.id)
        (self.settings.data_dir/Path(document['result_key']).parent/'page_1.png').unlink()
        self.assertEqual(self.decide().json()['error']['code'],'review_source_unavailable')
    def test_source_cannot_be_read_under_another_document_id(self):
        run=self.review()['source_run_id']
        other,_=self.store.register(digest='other',filename='other.pdf',media_type='application/pdf',size_bytes=1,page_count=1,original_key='none')
        r=self.client.get(f'/v1/documents/{other}/review/source/{run}/1')
        self.assertEqual(r.status_code,404)
        self.assertEqual(self.client.get(self.path+'/source/'+run+'/0').status_code,404)
    def test_no_review_before_extraction_or_for_unknown_document(self):
        other,_=self.store.register(digest='queued',filename='queued.pdf',media_type='application/pdf',size_bytes=1,page_count=1,original_key='none')
        self.assertEqual(self.client.get(f'/v1/documents/{other}/review').status_code,409)
        self.assertEqual(self.client.get('/v1/documents/missing/review').status_code,404)
        self.assertEqual(self.client.get(self.path+'?revision=50').status_code,404)
    def test_provider_cannot_claim_human_corrections(self):
        extraction=InvoiceExtraction.model_validate(self.review()['fields'])
        extraction.total.status='corrected';extraction.total.reason='provider pretending human reviewed'
        source=self.store.result(self.store.document(self.id))
        with self.assertRaises(ValueError):
            verify_evidence(extraction,source)

if __name__=='__main__':
    unittest.main()
