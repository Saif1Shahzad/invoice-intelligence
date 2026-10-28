"""Source-grounded unit tests; fixtures here are independent of benchmark labels."""
from copy import deepcopy
from decimal import Decimal
import re
import unittest

from invoice_intelligence.domain.invoice_validation import validate_extraction
from invoice_intelligence.extraction.local import extract
from invoice_intelligence.extraction.normalize import decimal,date_value
from invoice_intelligence.extraction.source import verify_evidence


def source(pages):
    output=[]
    for number,lines in enumerate(pages,1):
        words=[]
        for index,line in enumerate(lines):
            for match in re.finditer(r'\S+',line):
                words.append({'span_id':f'p{number}:w{len(words)+1}','text':match.group(),
                    'bbox':[.02+match.start()*.009,.03+index*.035,.02+match.end()*.009,.05+index*.035],
                    'recognition_score':None})
        output.append({'page':number,'method':'pdf_text','words':words,'text':'\n'.join(lines),'warnings':[]})
    return {'pages':output,'warnings':[]}


def header():
    return ['INVOICE','Test Supplier Limited Invoice No: TEST-0001','Date: 23 October 2026',
        'Due: 22 November 2026','Bill to:','Test Buyer Limited']


def table_header():
    return f"{'Description':<45}{'Qty':>5} {'Unit Price':>14} {'Amount':>14}"


def row(description='Paper cartons',quantity='2',price='50.00',amount='100.00'):
    return f'{description:<45}{quantity:>5} {price:>14} {amount:>14}'


def invoice_lines():
    return header()+[table_header(),row(),'Prices exclude VAT.','Subtotal: EUR 100.00',
        'VAT (20%): EUR 20.00','TOTAL: EUR 120.00','Payment terms: Net 30 days']


class LocalExtractionTests(unittest.TestCase):
    def parse(self,lines=None):
        return extract('doc-test',source([invoice_lines() if lines is None else lines]))

    def test_complete_header_and_table_with_actual_source_references(self):
        original=source([invoice_lines()])
        record=extract('doc-test',original)
        self.assertEqual(record.supplier_name.value,'Test Supplier Limited')
        self.assertEqual(record.invoice_number.value,'TEST-0001')
        self.assertEqual(str(record.issue_date.value),'2026-10-23')
        self.assertEqual(record.total.value,Decimal('120.00'))
        self.assertEqual(len(record.line_items),1)
        self.assertEqual(record.line_items[0].quantity.value,Decimal('2'))
        self.assertEqual(record.line_items[0].description.value,'Paper cartons')
        verify_evidence(record,original)
        self.assertTrue(record.total.evidence[0].span_ids)
        self.assertEqual(validate_extraction(record)['routing'],'ready_for_confirmation')

    def test_printed_wrong_total_is_retained_and_flagged(self):
        lines=invoice_lines()
        lines[lines.index('TOTAL: EUR 120.00')]='TOTAL: EUR 125.00'
        record=self.parse(lines)
        validation=validate_extraction(record)
        self.assertEqual(record.total.value,Decimal('125.00'))
        error=next(i for i in validation['issues'] if i['code']=='total_mismatch')
        self.assertEqual(error['expected'],'120.00')
        self.assertEqual(error['difference'],'5.00')
        self.assertTrue(validation['human_confirmation_required'])

    def test_vat_on_subtotal_sentence_is_tax_not_a_second_subtotal(self):
        lines=header()+[table_header(),row(),'The subtotal is 100,00 EUR.',
            'Plus 20% VAT on the subtotal, amounting to 20,00 EUR.',
            'The total amount due is 120,00 EUR.']
        record=self.parse(lines)
        self.assertEqual(record.subtotal.value,Decimal('100.00'))
        self.assertEqual(record.tax_amount.value,Decimal('20.00'))
        self.assertEqual(validate_extraction(record)['routing'],'ready_for_confirmation')

    def test_tax_inclusive_total_does_not_add_tax_again(self):
        record=self.parse(header()+[table_header(),row(price='60.00',amount='120.00'),
            'All prices include 20% VAT.','Subtotal (incl. VAT): EUR 120.00','TOTAL: EUR 120.00'])
        self.assertEqual(record.tax_mode.value,'inclusive')
        self.assertIsNone(record.tax_amount.value)
        validation=validate_extraction(record)
        self.assertEqual(validation['routing'],'ready_for_confirmation')
        self.assertEqual(next(v for v in validation['derived_values'] if v['field']=='calculated_total')['value'],'120.00')

    def test_conditional_terms_do_not_become_applied_discount(self):
        lines=invoice_lines()
        lines[-1]='Payment terms: 2/10 net 30'
        record=self.parse(lines)
        self.assertEqual(record.conditional_discount_rate.value,Decimal('.02'))
        self.assertIsNone(record.document_discount.value)
        self.assertFalse(any(i['code']=='total_mismatch' for i in validate_extraction(record)['issues']))

    def test_mixed_tax_total_is_derived_not_observed(self):
        record=self.parse(header()+[table_header(),row(),'Plus VAT as detailed below.',
            'Subtotal: EUR 100.00','VAT (20%): EUR 10.00','VAT (10%): EUR 5.00','TOTAL: EUR 115.00'])
        self.assertEqual(len(record.taxes),2)
        self.assertIsNone(record.tax_amount.value)
        self.assertIsNone(record.tax_rate.value)
        validation=validate_extraction(record)
        self.assertEqual(validation['routing'],'ready_for_confirmation')
        self.assertEqual(next(v for v in validation['derived_values'] if v['field']=='sum_tax_components')['value'],'15.00')

    def test_prose_rows_preserve_missing_implicit_quantity(self):
        record=self.parse(header()+['For the services rendered, we invoice as follows:',
            'Consulting hours: 2 × EUR 50.00 = EUR 100.00.',
            'For Annual service, we invoice EUR 100.00.',
            'Plus 20% VAT on the subtotal.','Subtotal: EUR 200.00','VAT (20%): EUR 40.00','TOTAL: EUR 240.00'])
        self.assertEqual(len(record.line_items),2)
        self.assertEqual(record.line_items[0].quantity.value,Decimal('2'))
        self.assertIsNone(record.line_items[1].quantity.value)
        self.assertEqual(record.line_items[1].amount.value,Decimal('100.00'))
        self.assertEqual(validate_extraction(record)['routing'],'needs_review')

    def test_wrapped_table_description_is_joined_with_separate_evidence(self):
        lines=invoice_lines()
        lines.insert(lines.index('Prices exclude VAT.'),'continued description')
        record=self.parse(lines)
        self.assertEqual(record.line_items[0].description.value,'Paper cartons continued description')
        self.assertEqual(len(record.line_items[0].description.evidence),2)

    def test_wrapped_prose_amount_is_read_from_next_line(self):
        record=self.parse(header()+['For Long maintenance description, we invoice EUR','100.00.',
            'Plus 20% VAT.','Subtotal: EUR 100.00','VAT (20%): EUR 20.00','TOTAL: EUR 120.00'])
        self.assertEqual(len(record.line_items),1)
        self.assertEqual(record.line_items[0].amount.value,Decimal('100.00'))

    def test_multipage_continuation_accumulates_items_not_repeated_header_fields(self):
        first=header()+[table_header(),row()]
        second=['Invoice No: TEST-0001',table_header(),row('Consulting','1','50.00','50.00'),
            'Prices exclude VAT.','Subtotal: EUR 150.00','VAT (20%): EUR 30.00','TOTAL: EUR 180.00']
        record=extract('doc-test',source([first,second]))
        self.assertEqual(len(record.line_items),2)
        self.assertEqual(record.invoice_number.value,'TEST-0001')
        self.assertEqual(record.line_items[1].amount.evidence[0].page,2)
        self.assertEqual(validate_extraction(record)['routing'],'ready_for_confirmation')

    def test_conflicting_references_and_dates_are_not_guessed(self):
        lines=invoice_lines()+['Invoice No: OTHER-0002','Date: 04/05/2026']
        record=self.parse(lines)
        self.assertEqual(record.invoice_number.status,'ambiguous')
        self.assertIsNone(record.issue_date.value)
        self.assertEqual(record.issue_date.reason,'ambiguous_date')
        self.assertEqual(validate_extraction(record)['routing'],'needs_review')

    def test_currency_symbol_alone_is_ambiguous(self):
        record=self.parse([line.replace('EUR ','$') for line in invoice_lines()])
        self.assertIsNone(record.currency.value)
        self.assertEqual(record.currency.reason,'ambiguous_currency_symbol')

    def test_credit_note_heading_is_not_a_supplier(self):
        lines=invoice_lines()
        lines.insert(1,'CREDIT NOTE')
        lines[2]='Test Supplier Limited Credit Note No: TEST-0001'
        record=self.parse(lines)
        self.assertEqual(record.supplier_name.value,'Test Supplier Limited')
        self.assertEqual(record.document_type.value,'credit_note')
        self.assertEqual(validate_extraction(record)['routing'],'needs_review')

    def test_unknown_layout_and_blank_input_require_review(self):
        for lines in [[],['Invoice document','The amount is unclear']]:
            record=self.parse(lines)
            self.assertIsNone(record.total.value)
            self.assertEqual(validate_extraction(record)['routing'],'needs_review')

    def test_evidence_verifier_rejects_fabricated_or_changed_spans(self):
        original=source([invoice_lines()])
        for change in ['id','text','box']:
            record=extract('doc-test',original)
            span=record.total.evidence[0]
            if change=='id':span.span_ids=['invented-id']
            elif change=='text':span.text='invented text'
            else:span.bbox=(0,0,.01,.01)
            with self.assertRaises((KeyError,ValueError)):
                verify_evidence(record,original)

    def test_repeated_pages_and_source_ocr_warnings_require_review(self):
        original=source([invoice_lines(),invoice_lines()])
        record=extract('doc-test',original)
        self.assertIn('repeated_page_content_requires_review',record.warnings)
        self.assertEqual(validate_extraction(record)['routing'],'needs_review')

    def test_line_arithmetic_failure_and_due_date_check(self):
        lines=invoice_lines()
        lines[3]='Due: 20 October 2026'
        lines[lines.index(row())]=row(price='40.00')
        issues=validate_extraction(self.parse(lines))['issues']
        self.assertTrue(any(i['code']=='line_amount_mismatch' for i in issues))
        self.assertTrue(any(i['code']=='due_date_before_issue_date' for i in issues))

    def test_decimal_and_date_normalization(self):
        for printed,expected in [("1'234.56",'1234.56'),('1.234,56','1234.56'),('1,234.56','1234.56'),('-100.00.','-100.00')]:
            self.assertEqual(decimal(printed),Decimal(expected))
        for printed in ['1,234','1.234','1.23.45']:
            with self.assertRaises(ValueError):decimal(printed)
        with self.assertRaises(ValueError):date_value('04/05/2026')
        self.assertEqual(date_value('23/10/2026'),'2026-10-23')
        self.assertEqual(date_value('10/23/2026'),'2026-10-23')

    def test_stated_discount_without_amount_is_not_assumed_zero(self):
        lines=invoice_lines()
        lines.insert(-1,'Discount: 10%')
        record=self.parse(lines)
        self.assertIsNone(record.document_discount.value)
        validation=validate_extraction(record)
        self.assertEqual(validation['routing'],'needs_review')
        self.assertTrue(any(i['code']=='optional_amount_unresolved' for i in validation['issues']))
        self.assertFalse(any(c['code']=='total_mismatch' for c in validation['checks']))

    def test_spaced_money_does_not_silently_drop_its_leading_digits(self):
        lines=invoice_lines()
        lines[lines.index('TOTAL: EUR 120.00')]='TOTAL: EUR 1 234.56'
        record=self.parse(lines)
        self.assertIsNone(record.total.value)
        self.assertEqual(record.total.reason,'ambiguous_spaced_number')
