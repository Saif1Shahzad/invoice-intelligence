from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.extraction.source import verify_evidence
from invoice_intelligence.persistence.extractions import ExtractionStore
from invoice_intelligence.schemas.extraction import InvoiceExtraction
from invoice_intelligence.workers.runner import run_once
from test_day3_pipeline import text_pdf


class ExtractionJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.settings=Settings(data_dir=Path(self.temp.name))
        self.app=create_app(self.settings)
        self.client=TestClient(self.app)
        self.client.__enter__()
        self.store=self.app.state.store
        self.extractions=ExtractionStore(self.store)
        self.pdf=text_pdf()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def upload(self):
        response=self.client.post('/v1/documents',files={'file':('fixture.pdf',self.pdf,'application/pdf')})
        self.assertEqual(response.status_code,202,response.text)
        return response.json()['id']

    def text_ready(self):
        identifier=self.upload()
        self.assertEqual(run_once(self.settings,self.store)['stage'],'text')
        return identifier

    def complete(self):
        identifier=self.text_ready()
        self.assertEqual(run_once(self.settings,self.store)['stage'],'extraction')
        return identifier

    def test_upload_to_source_grounded_fields_and_validation(self):
        identifier=self.complete()
        document=self.client.get('/v1/documents/'+identifier).json()
        self.assertEqual(document['status'],'text_ready')
        stage=document['extraction']
        self.assertIn(stage['status'],['needs_review','ready_for_confirmation'])
        self.assertEqual(stage['fields']['total']['value'],'120.00')
        self.assertTrue(stage['validation']['human_confirmation_required'])
        self.assertEqual(stage['usage']['external_requests'],0)
        self.assertEqual(stage['usage']['provider_cost_usd'],'0.00')
        verify_evidence(InvoiceExtraction.model_validate(stage['fields']),document['result'])
        self.assertEqual(self.client.get('/v1/documents/'+identifier+'/extractions').json()['runs'][0]['run_id'],stage['run_id'])
        self.assertIsNone(run_once(self.settings,self.store))

    def test_repeated_and_concurrent_extract_requests_reuse_job_and_run(self):
        identifier=self.text_ready()
        def request(_):
            response=self.client.post('/v1/documents/'+identifier+'/extract')
            self.assertEqual(response.status_code,200,response.text)
            return response.json()['requested_job_id']
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs=list(pool.map(request,range(4)))
        self.assertEqual(len(set(jobs)),1)
        run_once(self.settings,self.store)
        again=self.client.post('/v1/documents/'+identifier+'/extract')
        self.assertEqual(again.status_code,200)
        self.assertTrue(again.json()['reused'])
        with self.store.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM extraction_jobs').fetchone()[0],1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM extraction_runs').fetchone()[0],1)
        self.assertIsNone(run_once(self.settings,self.store))

    def test_extract_requires_saved_text(self):
        identifier=self.upload()
        response=self.client.post('/v1/documents/'+identifier+'/extract')
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['error']['code'],'text_not_ready')
        self.assertEqual(self.client.get('/v1/documents/'+identifier).json()['extraction']['status'],'not_started')

    def test_saved_extraction_survives_api_restart(self):
        identifier=self.complete()
        before=self.client.get('/v1/documents/'+identifier).json()['extraction']
        with TestClient(create_app(self.settings)) as restarted:
            self.assertEqual(restarted.get('/v1/documents/'+identifier).json()['extraction'],before)

    def test_text_integrity_failure_and_retry_preserve_saved_text_job(self):
        identifier=self.text_ready()
        path=self.settings.data_dir/self.store.document(identifier)['result_key']
        original=path.read_bytes()
        path.write_bytes(original+b' ')
        result=run_once(self.settings,self.store)
        self.assertEqual(result['status'],'failed')
        stage=self.client.get('/v1/documents/'+identifier).json()['extraction']
        self.assertEqual(stage['job']['error_code'],'text_integrity_error')
        self.assertIsNone(stage['fields'])
        self.assertEqual(self.store.document(identifier)['status'],'text_ready')
        path.write_bytes(original)
        self.assertEqual(self.client.post('/v1/documents/'+identifier+'/extract/retry').status_code,202)
        run_once(self.settings,self.store)
        stage=self.client.get('/v1/documents/'+identifier).json()['extraction']
        self.assertEqual(stage['job']['attempts'],2)
        self.assertEqual(len(self.extractions.history(identifier)),1)

    def test_extraction_timeout_does_not_publish_partial_candidate(self):
        identifier=self.text_ready()
        run_once(replace(self.settings,process_timeout=.001),self.store)
        stage=self.extractions.summary(identifier)
        self.assertEqual(stage['status'],'failed')
        self.assertEqual(stage['job']['error_code'],'processing_timeout')
        self.assertIsNone(stage['fields'])
        self.assertEqual(self.extractions.history(identifier),[])
        self.assertEqual(self.store.document(identifier)['status'],'text_ready')

    def test_expired_extraction_worker_is_fenced_and_attempts_are_bounded(self):
        identifier=self.text_ready()
        first=self.extractions.claim()
        with self.store.connect() as connection:
            connection.execute('UPDATE extraction_jobs SET lease_until=0 WHERE id=?',(first['id'],))
        second=self.extractions.claim()
        self.assertEqual(second['attempts'],2)
        self.assertFalse(self.extractions.finish(first,result_key='stale/extraction.json'))
        self.extractions.finish(second,error=DocumentError('fixture_error','Intentional test failure.'))
        self.extractions.retry(identifier)
        third=self.extractions.claim()
        self.extractions.finish(third,error=DocumentError('fixture_error','Intentional test failure.'))
        self.assertEqual(self.client.post('/v1/documents/'+identifier+'/extract/retry').status_code,409)
        self.assertEqual(self.extractions.history(identifier),[])

    def test_two_extraction_workers_cannot_claim_same_active_job(self):
        self.text_ready()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=list(pool.map(lambda _:self.extractions.claim(),range(2)))
        self.assertEqual(sum(job is not None for job in jobs),1)

    def test_existing_day3_results_are_discovered_without_reupload(self):
        with TemporaryDirectory() as other:
            disabled=Settings(data_dir=Path(other),extraction_provider='disabled')
            with TestClient(create_app(disabled)) as old:
                response=old.post('/v1/documents',files={'file':('old.pdf',self.pdf,'application/pdf')})
                identifier=response.json()['id']
                run_once(disabled,old.app.state.store)
                self.assertEqual(old.get('/v1/documents/'+identifier).json()['extraction']['status'],'not_started')
            enabled=replace(disabled,extraction_provider='local')
            with TestClient(create_app(enabled)) as upgraded:
                self.assertEqual(run_once(enabled,upgraded.app.state.store)['stage'],'extraction')
                record=upgraded.get('/v1/documents/'+identifier).json()
                self.assertEqual(record['id'],identifier)
                self.assertEqual(record['extraction']['fields']['total']['value'],'120.00')
                with upgraded.app.state.store.connect() as connection:
                    self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],6)
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM documents').fetchone()[0],1)

    def test_disabled_provider_and_invalid_retry_return_clear_errors(self):
        with TestClient(create_app(replace(self.settings,extraction_provider='disabled'))) as client:
            identifier=self.upload()
            run_once(self.settings,self.store)
            response=client.post('/v1/documents/'+identifier+'/extract')
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['error']['code'],'extraction_disabled')
        self.assertEqual(self.client.post('/v1/documents/'+identifier+'/extract/retry').status_code,409)

    def test_discovery_of_missing_legacy_text_does_not_crash_worker(self):
        identifier=self.text_ready()
        with self.store.connect() as connection:
            connection.execute('DELETE FROM extraction_jobs WHERE document_id=?',(identifier,))
        path=self.settings.data_dir/self.store.document(identifier)['result_key']
        path.unlink()
        self.assertIsNone(run_once(self.settings,self.store))
        stage=self.extractions.summary(identifier)
        self.assertEqual(stage['status'],'failed')
        self.assertEqual(stage['job']['error_code'],'text_result_missing')
