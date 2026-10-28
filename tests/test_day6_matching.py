"""Rule behavior plus durable, concurrent duplicate/PO review integration."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from pypdf import PdfReader,PdfWriter
from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.matching.purchase_orders import COLUMNS,parse_csv
from invoice_intelligence.matching.rules import duplicate_rule,match_po
from invoice_intelligence.workers.runner import run_once
from test_day3_pipeline import text_pdf


def wrapped(**values):
    return {k:{'value':v,'status':'corrected' if v is not None else 'missing'} for k,v in values.items()}


def example(**changes):
    fields=wrapped(document_type='invoice',supplier_name='Acme Limited',invoice_number='INV-2026-0001',
        issue_date='2026-10-23',currency='EUR',total='120.00',po_number='PO-1')
    fields['line_items']=[wrapped(description='Paper cartons',sku=None,quantity='2',unit_price='50.00',amount='100')]
    fields.update(wrapped(**changes))
    return fields


def csv_bytes(*,supplier='Synthetic Supplier Limited',price='50',quantity='2',reference='PO-1',currency='EUR',description='Paper cartons'):
    out=io.StringIO();writer=csv.writer(out);writer.writerow(COLUMNS)
    writer.writerow([reference,supplier,currency,'1','',description,quantity,price])
    return out.getvalue().encode()


class MatchingRuleTests(unittest.TestCase):
    def test_same_bill_ignores_filename_punctuation_and_amount_disagreement(self):
        a=example();b=example(supplier_name='ACME LIMITED',invoice_number='inv 2026 0001',total='121')
        self.assertEqual(duplicate_rule(a,b)['rule'],'supplier_and_reference')
    def test_ocr_like_reference_and_supplier_variants_need_other_anchors(self):
        a=example();b=example(invoice_number='INV-2O26-0001')
        self.assertEqual(duplicate_rule(a,b)['rule'],'ocr_like_identity')
        self.assertIsNone(duplicate_rule(a,example(invoice_number='INV-2O26-0001',issue_date='2026-10-24')))
        self.assertEqual(duplicate_rule(a,example(supplier_name='Acme Limlted'))['rule'],'ocr_like_identity')
    def test_hard_negatives_sequential_refs_supplier_currency_and_credit_note(self):
        for b in [example(invoice_number='INV-2026-0002'),example(supplier_name='Other Limited'),
                  example(invoice_number=None,currency='USD'),example(document_type='credit_note')]:
            self.assertIsNone(duplicate_rule(example(),b),b)
    def test_missing_reference_needs_item_support_and_does_not_match_empty_items(self):
        a=example();b=example(invoice_number=None)
        self.assertEqual(duplicate_rule(a,b)['rule'],'missing_reference_with_items')
        b['line_items']=[];self.assertIsNone(duplicate_rule(a,b))
    def test_po_exact_description_or_sku_matching_and_split_quantity(self):
        po={'id':'v1','supplier_name':'Acme Limited','currency':'EUR','lines':[
            {'line_number':'1','sku':'ABC','description':'Paper cartons','quantity':'2','unit_price':'50'}]}
        a=example();self.assertEqual(match_po(a,po)['status'],'matched')
        a['line_items']=[wrapped(sku='ABC',description='Different description',quantity='1',unit_price='50')]*2
        r=match_po(a,po);self.assertEqual(r['status'],'matched');self.assertEqual(len(r['matches']),2)
    def test_po_never_guesses_ambiguous_or_unknown_sku(self):
        line={'line_number':'1','sku':'A','description':'Paper cartons','quantity':'2','unit_price':'50'}
        po={'id':'v','supplier_name':'Acme Limited','currency':'EUR','lines':[line,line|{'line_number':'2'}]}
        self.assertIn('po_item_ambiguous',[i['code'] for i in match_po(example(),po)['issues']])
        a=example();a['line_items'][0]['sku']={'status':'corrected','value':'NOT-FOUND'}
        self.assertIn('po_item_not_found',[i['code'] for i in match_po(a,po)['issues']])
    def test_po_reports_supplier_currency_price_quantity_missing_and_extra_items(self):
        po={'id':'v','supplier_name':'Different','currency':'USD','lines':[
            {'line_number':'1','sku':'','description':'Paper cartons','quantity':'3','unit_price':'51'},
            {'line_number':'2','sku':'','description':'Ink','quantity':'1','unit_price':'10'}]}
        a=example();a['line_items'].append(wrapped(description='Not ordered',sku=None,quantity='1',unit_price='4'))
        codes={i['code'] for i in match_po(a,po)['issues']}
        self.assertTrue({'po_supplier_mismatch','po_currency_mismatch','po_price_mismatch','po_quantity_mismatch','po_line_missing','po_item_not_found'}<=codes)
    def test_no_po_reference_is_not_a_match_and_unknown_reference_is_discrepancy(self):
        self.assertEqual(match_po(example(po_number=None),None)['status'],'not_requested')
        self.assertEqual(match_po(example(),None)['issues'][0]['code'],'po_not_found')
    def test_csv_is_strict_bounded_and_validates_whole_batch(self):
        for content in [b'',b'wrong,header\na,b',csv_bytes(price='NaN'),csv_bytes(quantity='0'),
                        csv_bytes(currency='EURO'),csv_bytes(price='1,000'),csv_bytes(price='1e3'),
                        csv_bytes(price='1000000000001'),csv_bytes(supplier='---'),b'\xff',b'a'*(1024*1024+1)]:
            with self.subTest(content=content[:30]):
                with self.assertRaises(DocumentError):parse_csv(content)
        raw=csv_bytes();self.assertEqual(len(parse_csv(b'\xef\xbb\xbf'+raw)),1)
        with self.assertRaises(DocumentError):parse_csv(raw+raw.splitlines(keepends=True)[1])


class MatchingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=TemporaryDirectory();settings=Settings(data_dir=Path(cls.fixture.name))
        with TestClient(create_app(settings)) as client:
            cls.id=client.post('/v1/documents',files={'file':('invoice.pdf',text_pdf(),'application/pdf')}).json()['id']
            run_once(settings,client.app.state.store);run_once(settings,client.app.state.store)
    @classmethod
    def tearDownClass(cls):cls.fixture.cleanup()
    def setUp(self):
        self.temp=TemporaryDirectory();shutil.copytree(self.fixture.name,self.temp.name,dirs_exist_ok=True)
        self.settings=Settings(data_dir=Path(self.temp.name));self.client=TestClient(create_app(self.settings));self.client.__enter__();self.store=self.client.app.state.store
        self.complete(self.id)
    def tearDown(self):self.client.__exit__(None,None,None);self.temp.cleanup()
    def path(self,identifier,suffix='/review'):return f'/v1/documents/{identifier}{suffix}'
    def review(self,identifier=None):return self.client.get(self.path(identifier or self.id)).json()
    def action(self,identifier=None,**extra):return {'expected_revision':self.review(identifier)['revision'],'actor':'Tester','reason':'Checked synthetic matching fixture',**extra}
    def edit(self,identifier=None,**extra):
        identifier=identifier or self.id
        r=self.client.patch(self.path(identifier),json=self.action(identifier,**extra));self.assertEqual(r.status_code,200,r.text);return r.json()
    def complete(self,identifier):
        return self.edit(identifier,fields={'issue_date':'2026-10-23','tax_mode':'exclusive'},line_items=[{'description':'Paper cartons','quantity':'2','unit_price':'50','amount':'100'}])
    def other(self,reference=None):
        writer=PdfWriter();writer.append(PdfReader(io.BytesIO(text_pdf())));writer.add_metadata({'/Title':str(self.store.path)+str(reference)})
        output=io.BytesIO();writer.write(output)
        r=self.client.post('/v1/documents',files={'file':('other.pdf',output.getvalue(),'application/pdf')});self.assertEqual(r.status_code,202,r.text)
        identifier=r.json()['id'];run_once(self.settings,self.store);run_once(self.settings,self.store);self.complete(identifier)
        if reference:self.edit(identifier,fields={'invoice_number':reference})
        return identifier
    def classify(self,other,decision='same_bill',canonical=None):
        body=self.action(other_document_id=other,decision=decision,canonical_document_id=canonical,
            matching_token=self.review()['matching']['token'])
        return self.client.post(self.path(self.id,'/duplicates/decision'),json=body)
    def approve(self,identifier=None,**extra):
        identifier=identifier or self.id;r=self.review(identifier)
        body=self.action(identifier,decision='approved',acknowledge_warnings=True,matching_token=r['matching']['token'],**extra)
        return self.client.post(self.path(identifier,'/review/decision'),json=body)
    def import_csv(self,raw=None):
        return self.client.post('/v1/purchase-orders/import',files={'file':('orders.csv',raw or csv_bytes(),'text/csv')},data={'actor':'Tester','reason':'Synthetic PO import'})
    def test_real_pipeline_duplicate_blocks_then_resolves_and_survives_restart(self):
        other=self.other()
        self.assertEqual(len(self.review()['matching']['duplicates']),1)
        self.assertEqual(self.approve().json()['error']['code'],'duplicate_confirmation_blocked')
        r=self.classify(other,canonical=self.id);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.approve().status_code,200)
        self.assertEqual(self.approve(other).json()['error']['code'],'duplicate_confirmation_blocked')
        before=self.review()
        with TestClient(create_app(self.settings)) as restarted:self.assertEqual(restarted.get(self.path(self.id)).json(),before)
        events=self.client.get(self.path(other,'/duplicates/history')).json()['decisions'];self.assertEqual(events[0]['canonical_document_id'],self.id)
        cards=self.client.get('/v1/documents').json()['documents']
        self.assertTrue(next(d for d in cards if d['id']==other)['matching_summary']['marked_duplicate'])
        self.assertEqual(self.review(other)['matching']['duplicates'][0]['decision_actor'],'Tester')
    def test_pair_decisions_are_reversible_and_stale_request_cannot_append_twice(self):
        other=self.other();r=self.classify(other,'different_bill');self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(self.review()['matching']['allowed'])
        body=self.action(decision='unresolved',other_document_id=other,matching_token=self.review()['matching']['token'])
        r=self.client.post(self.path(self.id,'/duplicates/decision'),json=body);self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(self.review()['matching']['allowed'])
        self.assertEqual(self.client.post(self.path(self.id,'/duplicates/decision'),json=body).status_code,409)
        self.assertEqual(len(self.client.get(self.path(self.id,'/duplicates/history')).json()['decisions']),2)
    def test_changed_other_invoice_invalidates_pair_decision_and_matching_token(self):
        other=self.other();self.classify(other,'different_bill')
        token=self.review()['matching']['token'];revision=self.review()['revision']
        self.edit(other,fields={'supplier_address':'New reviewed address'})
        r=self.review();self.assertTrue(r['matching']['duplicates'][0]['decision_stale'])
        self.assertNotEqual(token,r['matching']['token'])
        response=self.client.post(self.path(self.id,'/review/decision'),json={'expected_revision':revision,'actor':'T','reason':'Old context','decision':'approved','acknowledge_warnings':True,'matching_token':token})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['error']['code'],'matching_conflict')
    def test_canonical_cannot_be_a_duplicate_or_form_a_cycle(self):
        other=self.other();self.classify(other,canonical=other)
        r=self.classify(other,canonical=self.id)
        self.assertEqual(r.status_code,409)
        self.assertEqual(r.json()['error']['code'],'duplicate_chain')
    def test_invalid_pair_and_canonical_are_atomic(self):
        other=self.other()
        self.assertEqual(self.classify(other,canonical='unknown').status_code,422)
        self.assertEqual(self.classify(other,'different_bill',canonical=other).status_code,422)
        self.assertEqual(self.classify(self.id,'different_bill').status_code,409)
        self.assertEqual(self.client.get(self.path(self.id,'/duplicates/history')).json()['decisions'],[])
    def test_two_simultaneous_decisions_accept_one(self):
        other=self.other();body=self.action(decision='different_bill',other_document_id=other,matching_token=self.review()['matching']['token'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.client.post(self.path(self.id,'/duplicates/decision'),json=body),range(2)))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
    def test_po_import_matching_and_correction_rerun(self):
        self.assertEqual(self.import_csv().status_code,200)
        r=self.edit(fields={'po_number':'PO-1'})
        self.assertEqual(r['matching']['purchase_order']['status'],'matched')
        self.assertEqual(self.approve().status_code,200)
        self.edit(line_items=[{'source_index':0,'description':'Paper cartons','quantity':'1','unit_price':'100','amount':'100'}])
        issues=self.review()['matching']['purchase_order']['issues']
        self.assertEqual({i['code'] for i in issues},{'po_quantity_mismatch','po_price_mismatch'})
        self.assertEqual(self.approve().json()['error']['code'],'po_exception_not_acknowledged')
        confirmed=self.approve(acknowledge_po_exception=True)
        self.assertEqual(confirmed.status_code,200)
        self.assertTrue(confirmed.json()['po_exception_accepted'])
        history=self.client.get(self.path(self.id,'/review/history')).json()['revisions']
        self.assertTrue(any(c['field']=='matching_checks' for c in history[0]['changes']))
    def test_unknown_po_needs_exception_and_no_reference_is_not_matched(self):
        self.assertEqual(self.review()['matching']['purchase_order']['status'],'not_requested')
        self.edit(fields={'po_number':'UNKNOWN'})
        self.assertEqual(self.approve().status_code,409)
        self.assertEqual(self.approve(acknowledge_po_exception=True).status_code,200)
    def test_po_versions_are_atomic_idempotent_and_replay_does_not_roll_back(self):
        first=self.import_csv().json();self.assertEqual(first['new_versions'],1)
        again=self.import_csv().json();self.assertTrue(again['reused'])
        self.import_csv(csv_bytes(price='51'))
        self.import_csv()
        versions=self.client.get('/v1/purchase-orders/PO-1/history').json()['versions']
        self.assertEqual(len(versions),2)
        current=self.client.get('/v1/purchase-orders').json()['purchase_orders'][0]
        self.assertEqual(current['id'],versions[-1]['id'])
        count=len(versions)
        invalid=csv_bytes()+b'PO-OTHER,Other,EUR,1,,Thing,2,NaN\n'
        self.assertEqual(self.import_csv(invalid).status_code,422)
        self.assertEqual(len(self.client.get('/v1/purchase-orders').json()['purchase_orders']),1)
    def test_concurrent_po_import_creates_one_version(self):
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.import_csv(),range(2)))
        self.assertTrue(all(r.status_code==200 for r in results))
        self.assertEqual(sum(r.json()['new_versions'] for r in results),1)
    def test_po_change_after_display_requires_reload_before_confirmation(self):
        self.import_csv();self.edit(fields={'po_number':'PO-1'});old=self.review()
        self.import_csv(csv_bytes(price='51'))
        body=self.action(decision='approved',acknowledge_warnings=True,acknowledge_po_exception=True,matching_token=old['matching']['token'])
        r=self.client.post(self.path(self.id,'/review/decision'),json=body)
        self.assertEqual(r.status_code,409);self.assertEqual(r.json()['error']['code'],'matching_conflict')
    def test_new_findings_flag_old_confirmation_and_reopen_is_audited(self):
        self.assertEqual(self.approve().status_code,200)
        self.assertFalse(self.review()['matching_changed_since_confirmation'])
        self.other()
        self.assertTrue(self.review()['matching_changed_since_confirmation'])
        cards=self.client.get('/v1/documents').json()['documents']
        self.assertTrue(next(d for d in cards if d['id']==self.id)['matching_summary']['needs_recheck'])
        r=self.client.post(self.path(self.id,'/review/reopen'),json=self.action())
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'pending')
        self.assertEqual(self.client.get(self.path(self.id,'/review/history')).json()['revisions'][0]['action'],'reopened')
    def test_exact_upload_is_reused_and_unprocessed_coverage_is_visible(self):
        r=self.client.post('/v1/documents',files={'file':('renamed.pdf',text_pdf(),'application/pdf')})
        self.assertEqual(r.status_code,200);self.assertTrue(r.json()['duplicate']);self.assertEqual(r.json()['id'],self.id)
        self.store.register(digest='pending',filename='pending.pdf',media_type='application/pdf',size_bytes=1,page_count=1,original_key='none')
        self.assertEqual(len(self.review()['matching']['unavailable_document_ids']),1)
        self.assertIn('not_ready',[d['matching_summary']['status'] for d in self.client.get('/v1/documents').json()['documents']])
    def test_history_tables_cannot_be_mutated(self):
        other=self.other();self.classify(other,'different_bill');self.import_csv()
        with self.store.connect() as c:
            for query in ['DELETE FROM duplicate_decisions','UPDATE po_versions SET currency="USD"','DELETE FROM po_imports']:
                with self.assertRaises(sqlite3.IntegrityError):c.execute(query)
    def test_invalid_po_identity_and_template(self):
        r=self.client.post('/v1/purchase-orders/import',files={'file':('x.csv',csv_bytes(),'text/csv')},data={'actor':' ','reason':' '})
        self.assertEqual(r.status_code,422)
        self.assertTrue(self.client.get('/v1/purchase-orders/template').text.startswith(','.join(COLUMNS)))

if __name__=='__main__':unittest.main()
