import unittest
from copy import deepcopy

from invoice_intelligence.domain.benchmark_mapping import map_benchmark_label


def fixture():
    return dict(invoice_id='FIXTURE-1', vendor='Test supplier', recipient='Test buyer',
        date='2026-01-01', due_date='2026-01-31', currency='EUR', payment_terms='Net 30',
        subtotal='100.00', rendered_subtotal='100.00', total='120.00', rendered_total='125.00',
        vat_amount='20.00', vat_rate='0.20', discount=None, discount_amount='0.00',
        error_note='Injected total error', is_credit_note=False,
        line_items=[dict(description='Part', quantity=2, unit_price='50.00', amount='100.00', vat_rate='0.20')],
        variants=dict(layout='table', vat_variant='explicit_excluded', discount_variant='none',
                      edge_case='none', consistency='total_error', number_format='english'))


class BenchmarkMappingTests(unittest.TestCase):
    def test_wrong_printed_total_is_not_silently_corrected(self):
        result = map_benchmark_label(fixture())
        self.assertEqual(result['fields']['total']['value'], '125.00')
        self.assertEqual(result['mathematical_truth']['total'], '120.00')

    def test_inclusive_gross_subtotal_and_row_values(self):
        raw = fixture()
        raw['variants']['vat_variant'] = 'explicit_included'
        raw['rendered_subtotal'] = '105.00'
        result = map_benchmark_label(raw)
        self.assertEqual(result['fields']['subtotal']['value'], '125.00')
        self.assertEqual(result['line_items'][0]['unit_price']['value'], '60.00')
        self.assertEqual(result['line_items'][0]['amount']['value'], '120.00')
        self.assertFalse(result['fields']['tax_amount']['score_extraction'])
        self.assertIsNone(result['fields']['tax_amount']['value'])

    def test_conditional_discount_is_not_applied_discount(self):
        raw = fixture()
        raw['variants']['discount_variant'] = 'trade_terms'
        raw['discount'] = {'value': '0.02', 'conditional': True}
        result = map_benchmark_label(raw)
        self.assertIsNone(result['fields']['document_discount']['value'])
        self.assertEqual(result['fields']['conditional_discount_rate']['value'], '0.02')

    def test_implicit_quantity_is_not_scored_as_printed(self):
        raw = fixture()
        raw['variants']['layout'] = 'paragraph'
        raw['line_items'][0]['quantity'] = 1
        result = map_benchmark_label(raw)
        self.assertFalse(result['line_items'][0]['quantity']['score_extraction'])
        self.assertTrue(result['line_items'][0]['amount']['score_extraction'])

    def test_per_row_tax_and_missing_shipping_are_not_invented(self):
        result = map_benchmark_label(fixture())
        self.assertIsNone(result['line_items'][0]['tax_rate']['value'])
        self.assertIsNone(result['fields']['shipping']['value'])

    def test_mapper_does_not_modify_original_labels(self):
        raw = fixture()
        before = deepcopy(raw)
        map_benchmark_label(raw)
        self.assertEqual(raw, before)

    def test_known_rendering_discrepancy_is_not_silently_scored(self):
        raw = fixture()
        raw['line_items'][0]['description'] = 'Translation EN ↔ DE'
        result = map_benchmark_label(raw)
        self.assertEqual(result['line_items'][0]['description']['kind'], 'needs_adjudication')
        self.assertFalse(result['line_items'][0]['description']['score_extraction'])

    def test_reverse_charge_is_preserved_without_inventing_tax_amount(self):
        raw = fixture()
        raw['variants']['edge_case'] = 'reverse_charge'
        result = map_benchmark_label(raw)
        self.assertEqual(result['fields']['tax_mode']['value'], 'reverse_charge')
        self.assertIsNone(result['fields']['tax_amount']['value'])
        self.assertTrue(result['fields']['tax_amount']['score_absence'])

    def test_inclusive_prose_summary_does_not_print_a_vat_rate(self):
        raw = fixture()
        raw['variants'].update(vat_variant='explicit_included', layout='mixed')
        result = map_benchmark_label(raw)
        self.assertIsNone(result['fields']['tax_rate']['value'])
        self.assertTrue(result['fields']['tax_rate']['score_absence'])
