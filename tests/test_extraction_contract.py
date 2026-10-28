import unittest

from pydantic import ValidationError

from invoice_intelligence.schemas.extraction import Evidence, ExtractedField, InvoiceExtraction


class ExtractionContractTests(unittest.TestCase):
    def test_missing_field_is_null_not_zero(self):
        record = InvoiceExtraction(document_id='doc-1')
        self.assertIsNone(record.tax_amount.value)
        self.assertEqual(record.tax_amount.status, 'missing')

    def test_observed_value_requires_evidence(self):
        with self.assertRaises(ValidationError):
            ExtractedField[str](value='EUR', status='observed', reason=None)

    def test_bad_coordinate_or_page_is_rejected(self):
        for changes in ({'page': 0}, {'bbox': (0.6, 0.1, 0.2, 0.3)}, {'bbox': (0, 0, 2, 1)}):
            values = dict(page=1, bbox=(0.1, 0.1, 0.3, 0.2), text='EUR', method='pdf_text')
            with self.assertRaises(ValidationError):
                Evidence(**(values | changes))

    def test_missing_cannot_contain_invented_value(self):
        with self.assertRaises(ValidationError):
            ExtractedField[str](value='EUR', status='missing', reason='not_printed')

    def test_valid_observed_field_serializes_source(self):
        field = ExtractedField[str](value='EUR', status='observed', reason=None,
            evidence=[Evidence(page=1, bbox=(0.1, 0.1, 0.3, 0.2), text='EUR', method='pdf_text')])
        self.assertEqual(field.model_dump()['evidence'][0]['page'], 1)

    def test_extra_fields_and_nonfinite_money_are_rejected(self):
        with self.assertRaises(ValidationError):
            InvoiceExtraction(document_id='doc-1', invented_score=0.99)
        with self.assertRaises(ValidationError):
            InvoiceExtraction(document_id='doc-1', total={'value': 'NaN', 'status': 'observed',
                'reason': None, 'evidence': [{'page': 1, 'bbox': [0, 0, 1, 1], 'text': 'NaN', 'method': 'ocr'}]})
