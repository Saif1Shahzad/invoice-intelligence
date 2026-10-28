"""Provider evidence, human verification, receipt arithmetic and access boundaries."""
from dataclasses import replace
import base64,json,os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.security import password_hash
from invoice_intelligence.extraction.groq import decode,HEADERS,ROWS,numbers,supported,call
from invoice_intelligence.extraction.source import Word
from invoice_intelligence.schemas.extraction import InvoiceExtraction
from invoice_intelligence.domain.invoice_validation import validate_extraction
from invoice_intelligence.extraction.providers import identity
from invoice_intelligence.domain.errors import DocumentError

class GroqTests(unittest.TestCase):
    def raw(self):return {'fields':{n:{'value':None,'span_ids':[]} for n in HEADERS},'line_items':[],'taxes':[],'warnings':[]}
    def test_missing_or_invented_spans_never_create_observed_fields(self):
        raw=self.raw();raw['fields']['total']={'value':'100','span_ids':['invented']}
        f=decode(raw,{},[]);self.assertEqual(f['total']['status'],'missing')
    def test_vision_disagreement_is_a_proposal_and_blocks_approval(self):
        raw=self.raw();raw['fields']['total']={'value':'100','span_ids':['p1:w1']};w=Word(1,1,'p1:w1','l00',(0,0,.1,.1),'ocr')
        f=decode(raw,{w.span_id:w},[]);self.assertEqual(f['total']['status'],'proposed')
        invoice=InvoiceExtraction.model_validate({'document_id':'test',**f})
        issues=validate_extraction(invoice)['issues'];self.assertIn('provider_value_unverified',[i['code'] for i in issues])
    def test_model_cannot_supply_extra_fields_or_corrected_status(self):
        raw=self.raw();raw['fields']['total']={'value':'100','span_ids':[],'status':'corrected'}
        with self.assertRaises(DocumentError):decode(raw,{},[])
    def test_payment_requires_its_own_label(self):
        words=[Word(1,1,'1','Total 100',(0,0,.1,.1),'ocr')]
        self.assertFalse(supported('amount_paid','100',words));self.assertTrue(supported('total','100',words))
    def test_indian_and_european_numeric_groups(self):
        self.assertIn(108000,numbers('INR 1,08,000.00'));self.assertIn(310,numbers('310,00 EURO'))
    def test_model_identity_is_separate_from_local_jobs(self):
        a=Settings();b=replace(a,extraction_provider='groq');c=replace(b,groq_model='different/model')
        self.assertNotEqual(identity(a),identity(b));self.assertNotEqual(identity(b),identity(c))
    def test_receipt_charges_reconcile_without_invented_quantities(self):
        def f(v):return {'value':v,'status':'corrected','reason':'Checked by reviewer','evidence':[]}
        record={'document_id':'receipt','document_type':f('receipt'),'supplier_name':f('Shop'),'issue_date':f('2026-10-28'),'currency':f('USD'),'tax_mode':f('exclusive'),'subtotal':f('48.68'),'tax_amount':f('4.80'),'shipping':f('1.50'),'service_fee':f('2.00'),'tip':f('4.50'),'total':f('61.48'),'line_items':[{'description':f('Purchased items'),'amount':f('48.68')}]}
        v=validate_extraction(InvoiceExtraction.model_validate(record));self.assertFalse(any(i['severity']=='error' for i in v['issues']));self.assertNotIn('line_field_unresolved',[i['code'] for i in v['issues']])
        record['total']=f('62');self.assertIn('total_mismatch',[i['code'] for i in validate_extraction(InvoiceExtraction.model_validate(record))['issues']])

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name);salt='12'*16
        self.users={n:{'role':role,'salt':salt,'hash':password_hash('test-password',salt)} for n,role in [('reader','viewer'),('reviewer','reviewer'),('owner','admin')]}
        self.file=self.root/'accounts.json';self.file.write_text(json.dumps(self.users));self.settings=Settings(data_dir=self.root/'data',auth_file=str(self.file))
        self.client=TestClient(create_app(self.settings));self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None);self.temp.cleanup()
    def test_documents_exports_and_static_assets_require_auth(self):
        for p in ['/','/v1/documents','/v1/exports/confirmed.json','/static/app.js','/health']:
            self.assertEqual(self.client.get(p).status_code,401,p)
        self.assertEqual(self.client.get('/livez').status_code,200)
    def test_viewer_reads_but_cannot_write(self):
        self.assertEqual(self.client.get('/v1/documents',auth=('reader','test-password')).status_code,200)
        self.assertEqual(self.client.post('/v1/documents',auth=('reader','test-password')).status_code,403)
    def test_only_admin_can_import_purchase_orders(self):
        self.assertEqual(self.client.post('/v1/purchase-orders/import',auth=('reviewer','test-password')).status_code,403)
    def test_cross_site_writes_are_blocked_even_when_authenticated(self):
        self.assertEqual(self.client.post('/v1/documents',auth=('owner','test-password'),headers={'Origin':'https://attacker.invalid'}).status_code,403)
    def test_disallowed_host_is_rejected(self):
        self.assertEqual(self.client.get('/livez',headers={'Host':'attacker.invalid'}).status_code,400)
    def test_failed_auth_is_rate_limited(self):
        for _ in range(10):self.assertEqual(self.client.get('/health',auth=('owner','wrong')).status_code,401)
        self.assertEqual(self.client.get('/health',auth=('owner','wrong')).status_code,429)
    def test_production_fails_without_auth_and_https(self):
        with self.assertRaises(ValueError):Settings(deployment='production')

if __name__=='__main__':unittest.main()

class ProposalWorkflowTests(unittest.TestCase):
    def test_same_value_proposal_needs_explicit_verification_and_records_actor(self):
        from test_day7_release import ReleaseTests
        from invoice_intelligence.persistence.reviews import ReviewStore
        from invoice_intelligence.schemas.extraction import InvoiceExtraction
        ReleaseTests.setUpClass()
        try:
            with TestClient(create_app(Settings(data_dir=Path(ReleaseTests.fixture.name)))) as client:
                id=ReleaseTests.id;path=f'/v1/documents/{id}/review';r=client.get(path).json()
                fields=r['fields'];fields['total']['status']='proposed';fields['total']['reason']='vision_value_not_corroborated_by_ocr'
                inv=InvoiceExtraction.model_validate(fields)
                with client.app.state.store.transaction() as conn:
                    ReviewStore(client.app.state.store).append(conn,id,r['revision']+1,r['source_run_id'],inv,validate_extraction(inv),actor='Fixture',reason='Proposed vision value',action='initialized')
                r=client.get(path).json();self.assertFalse(r['confirmation']['allowed'])
                body={'actor':'Tester','reason':'Read the amount on the source page','expected_revision':r['revision'],'fields':{'total':r['fields']['total']['value']}}
                unchanged=client.patch(path,json=body);self.assertEqual(unchanged.json()['fields']['total']['status'],'proposed')
                body['verified_fields']=['total'];verified=client.patch(path,json=body);self.assertEqual(verified.status_code,200,verified.text);self.assertEqual(verified.json()['fields']['total']['status'],'corrected');self.assertTrue(verified.json()['confirmation']['allowed'])
                self.assertEqual(client.get(path+'/history').json()['revisions'][0]['actor'],'Tester')
        finally:ReleaseTests.tearDownClass()

class BackupTests(unittest.TestCase):
    def test_backup_restore_and_tamper_detection(self):
        from invoice_intelligence.backup import backup,restore
        import sqlite3
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();db=source/'documents.sqlite3'
            with sqlite3.connect(db) as c:c.execute('CREATE TABLE example(value)');c.execute('INSERT INTO example VALUES (42)')
            (source/'document.png').write_bytes(b'source evidence')
            backup(source,root/'backup');restore(root/'backup',root/'restored')
            self.assertEqual((root/'restored/document.png').read_bytes(),b'source evidence')
            with sqlite3.connect(root/'restored/documents.sqlite3') as c:self.assertEqual(c.execute('SELECT value FROM example').fetchone()[0],42)
            (root/'backup/document.png').write_bytes(b'changed')
            with self.assertRaises(ValueError):restore(root/'backup',root/'bad-restore')
    def test_backup_never_overwrites_runtime(self):
        from invoice_intelligence.backup import backup
        with TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):backup(root,root/'nested')

class GroqQueueTests(unittest.TestCase):
    def test_quota_retry_is_delayed_and_other_provider_jobs_are_not_claimed(self):
        from invoice_intelligence.persistence.store import Store
        from invoice_intelligence.persistence.extractions import ExtractionStore
        from test_day3_pipeline import text_pdf
        from invoice_intelligence.workers.runner import run_once
        with TemporaryDirectory() as d:
            settings=Settings(data_dir=Path(d));store=Store(settings);store.initialize()
            with TestClient(create_app(settings)) as c:
                id=c.post('/v1/documents',files={'file':('invoice.pdf',text_pdf(),'application/pdf')}).json()['id'];run_once(settings,c.app.state.store);run_once(settings,c.app.state.store)
            groq=replace(settings,extraction_provider='groq',groq_min_interval=0);store=Store(groq);store.initialize();jobs=ExtractionStore(store)
            jobs.discover()
            with store.connect() as conn:self.assertEqual(conn.execute("SELECT COUNT(*) FROM extraction_jobs WHERE provider='groq'").fetchone()[0],0)
            jobs.enqueue(id);job=jobs.claim();self.assertIsNotNone(job)
            jobs.finish(job,error=DocumentError('groq_rate_limit','Wait for quota',retry_after=60))
            self.assertIsNone(jobs.claim())
            with store.connect() as conn:
                row=conn.execute('SELECT * FROM extraction_jobs WHERE id=?',(job['id'],)).fetchone();self.assertEqual(row['status'],'queued');self.assertGreater(row['retry_after'],0)
            with patch('invoice_intelligence.persistence.extractions.time.time',return_value=row['retry_after']+1):self.assertIsNotNone(jobs.claim())

class ProviderFailureTests(unittest.TestCase):
    def fixture(self,root):
        from PIL import Image
        image=root/'page_1.png';Image.new('RGB',(50,50),'white').save(image)
        return {'pages':[{'page':1,'text':'Total 100','method':'ocr','words':[{'span_id':'p1:w1','text':'Total','bbox':[0,.1,.4,.2]},{'span_id':'p1:w2','text':'100','bbox':[.5,.1,.8,.2]}]}]}
    def test_truncated_response_never_publishes_a_candidate_or_secret(self):
        from invoice_intelligence.extraction.groq import extract
        with TemporaryDirectory() as d:
            root=Path(d);source=self.fixture(root);output=root/'output'
            response={'id':'response','usage':{'prompt_tokens':10,'completion_tokens':10},'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}
            with patch.dict(os.environ,{'GROQ_API_KEY':'test-key-never-store'}),patch('invoice_intelligence.extraction.groq.call',return_value=response):
                with self.assertRaises(DocumentError) as error:extract('test',source,root/'result.json',Settings().child_options(),output)
            self.assertEqual(error.exception.code,'groq_incomplete');self.assertFalse((output/'extraction.json').exists())
            self.assertNotIn('test-key-never-store',''.join(p.read_text() for p in output.glob('*.json')))
    def test_budget_failure_makes_no_remote_call(self):
        from invoice_intelligence.extraction.groq import extract
        with TemporaryDirectory() as d:
            root=Path(d);source=self.fixture(root);options=Settings().child_options();options['groq_document_budget']='0.00000001'
            with patch.dict(os.environ,{'GROQ_API_KEY':'test-only'}),patch('invoice_intelligence.extraction.groq.call') as call_:
                with self.assertRaises(DocumentError):extract('test',source,root/'result.json',options,root/'out')
                call_.assert_not_called()
    def test_compact_wire_unknown_references_remain_unverified(self):
        from invoice_intelligence.extraction.groq import expand
        raw={'fields':{n:None for n in HEADERS},'line_items':[],'taxes':[],'warnings':[]};raw['fields']['total']={'v':'100','s':[999]}
        output=decode(expand(raw,{1:'p1:w1'}),{},[]);self.assertEqual(output['total']['status'],'missing')
    def test_duplicate_proposals_raise_holds_without_changing_source_status(self):
        from invoice_intelligence.matching.rules import duplicate_rule
        a={k:{'value':v,'status':'proposed'} for k,v in {'supplier_name':'Shop','invoice_number':'R-123','currency':'USD','total':'10'}.items()}
        result=duplicate_rule(a,a);self.assertTrue(result['unverified_candidate']);self.assertEqual(a['total']['status'],'proposed')

class ConfigurationTests(unittest.TestCase):
    def test_dotenv_is_not_shell_code_and_preserves_existing_environment(self):
        from invoice_intelligence.environment import load_environment
        with TemporaryDirectory() as d:
            p=Path(d)/'.env';p.write_text('TEST_INVOICE_SETTING="$(echo should-not-run)"\nGROQ_API_KEY=configure_locally\n')
            with patch.dict(os.environ,{'TEST_INVOICE_SETTING':'existing'},clear=True):
                load_environment(p);self.assertEqual(os.environ['TEST_INVOICE_SETTING'],'existing');self.assertNotIn('GROQ_API_KEY',os.environ)
            with patch.dict(os.environ,{},clear=True):
                load_environment(p);self.assertEqual(os.environ['TEST_INVOICE_SETTING'],'$(echo should-not-run)')
    def test_vercel_config_has_only_https_backend_routing_and_no_secrets(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('vercel_prepare',Path(__file__).parents[1]/'scripts/prepare_vercel.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with TemporaryDirectory() as d:
            config=mod.prepare('https://api.example.com',Path(d));self.assertEqual(config['rewrites'][0]['destination'],'https://api.example.com/:path*');self.assertNotIn('GROQ_API_KEY',json.dumps(config))
            for origin in ['http://api.example.com','https://user:password@api.example.com','https://localhost','https://api.example.com/path']:
                with self.assertRaises(ValueError):mod.prepare(origin,Path(d))

class BoundIdentityTests(unittest.TestCase):
    setUp=SecurityTests.setUp
    tearDown=SecurityTests.tearDown
    def test_actor_is_bound_to_login_and_other_reviewers_cannot_change_timer(self):
        from test_day3_pipeline import text_pdf
        from invoice_intelligence.workers.runner import run_once
        from uuid import uuid4
        auth=('owner','test-password');id=self.client.post('/v1/documents',auth=auth,files={'file':('invoice.pdf',text_pdf(),'application/pdf')}).json()['id']
        run_once(self.settings,self.client.app.state.store);run_once(self.settings,self.client.app.state.store)
        path=f'/v1/documents/{id}';r=self.client.get(path+'/review',auth=auth).json()
        change=self.client.patch(path+'/review',auth=auth,json={'actor':'Forged name','reason':'Checked source','expected_revision':r['revision'],'fields':{'invoice_number':'TEST-LOGIN'}})
        self.assertEqual(change.status_code,200,change.text)
        history=self.client.get(path+'/review/history',auth=auth).json();self.assertEqual(history['revisions'][0]['actor'],'owner')
        sid=str(uuid4());started=self.client.post(path+'/review-sessions',auth=auth,json={'session_id':sid,'actor':'Forged name','kind':'automated_demo'})
        self.assertEqual(started.status_code,200,started.text);self.assertEqual(started.json()['actor'],'owner')
        denied=self.client.post(path+'/review-sessions/'+sid+'/events',auth=('reviewer','test-password'),json={'sequence':1,'active_ms':0});self.assertEqual(denied.status_code,403)
        session=self.client.get('/v1/session',auth=auth).json();self.assertEqual(session,{'authenticated':True,'user':'owner','role':'admin'})

class ParserIsolationTests(unittest.TestCase):
    def test_native_parsers_do_not_inherit_api_credentials(self):
        from invoice_intelligence.ingestion.isolated import run_isolated
        with patch.dict(os.environ,{'GROQ_API_KEY':'dummy-key','OTHER_PASSWORD':'dummy-password'},clear=True),patch('invoice_intelligence.ingestion.isolated.subprocess.Popen') as popen:
            process=popen.return_value;process.communicate.return_value=(json.dumps({'ok':True,'result':{}}),'');process.returncode=0
            run_isolated(Path('source.pdf'),Settings())
            self.assertNotIn('GROQ_API_KEY',popen.call_args.kwargs['env']);self.assertNotIn('OTHER_PASSWORD',popen.call_args.kwargs['env'])
            run_isolated(Path('source.json'),Settings(extraction_provider='groq'),mode='extract')
            self.assertEqual(popen.call_args.kwargs['env']['GROQ_API_KEY'],'dummy-key');self.assertNotIn('OTHER_PASSWORD',popen.call_args.kwargs['env'])

class MigrationTests(unittest.TestCase):
    def test_parallel_startup_applies_retry_migration_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from invoice_intelligence.persistence.store import Store
        with TemporaryDirectory() as d:
            settings=Settings(data_dir=Path(d))
            with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:Store(settings).initialize(),range(2)))
            with Store(settings).connect() as conn:
                names=[r['name'] for r in conn.execute('PRAGMA table_info(extraction_jobs)')]
                self.assertEqual(names.count('retry_after'),1);self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],6)
