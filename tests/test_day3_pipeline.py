"""Real local ingestion, persistence, parser and optional OCR integration checks."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
import unittest

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.persistence.store import Store
from invoice_intelligence.workers.runner import run_once


def text_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    lines = ['INVOICE TEST-001', 'Synthetic Supplier Limited', 'Date 23 October 2026',
             'Description Quantity Price Amount', 'Paper cartons 2 50.00 100.00',
             'Subtotal EUR 100.00', 'VAT EUR 20.00', 'TOTAL EUR 120.00']
    content = 'BT /F1 16 Tf 40 790 Td 28 TL ' + ' '.join(f'({line}) Tj T*' for line in lines) + ' ET'
    stream.set_data(content.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_bytes(*, rotated=False, blank=False, format='PNG'):
    image = Image.new('RGB', (1200, 1600), 'white')
    if not blank:
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=34)
        lines = ['SYNTHETIC INVOICE TEST-001', 'SYNTHETIC SUPPLIER LIMITED', 'Date 23 October 2026',
            'Customer Example Company', 'Invoice items and quantities', 'Paper cartons 2 at EUR 50.00',
            'Subtotal EUR 100.00', 'VAT EUR 20.00', 'TOTAL EUR 120.00', 'Payment due in thirty days',
            'This is a generated test invoice', 'Contact the supplier for questions']
        for index, line in enumerate(lines):
            draw.text((50, 80 + index * 85), line, fill='black', font=font)
    if rotated:
        image = image.rotate(90, expand=True)
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    image.close()
    return buffer.getvalue()


class Day3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = text_pdf()
        cls.png = image_bytes()
        cls.jpeg = image_bytes(format='JPEG')
        writer = PdfWriter()
        writer.append(io.BytesIO(cls.pdf))
        writer.append(io.BytesIO(cls.pdf))
        output = io.BytesIO()
        writer.write(output)
        cls.multipage = output.getvalue()
        writer = PdfWriter()
        writer.append(io.BytesIO(cls.pdf))
        writer.encrypt('test-password')
        output = io.BytesIO()
        writer.write(output)
        cls.encrypted = output.getvalue()
        scan_buffer = io.BytesIO()
        with Image.open(io.BytesIO(cls.png)) as scan:
            scan.save(scan_buffer, format='PDF', resolution=150)
        writer = PdfWriter()
        writer.append(io.BytesIO(cls.pdf))
        writer.append(io.BytesIO(scan_buffer.getvalue()))
        output = io.BytesIO()
        writer.write(output)
        cls.mixed_pdf = output.getvalue()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings(data_dir=Path(self.temp.name), extraction_provider='disabled')
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.store = self.app.state.store

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def upload(self, body=None, name='invoice.pdf', mime='application/pdf', key=None):
        return self.client.post('/v1/documents', files={'file': (name, self.pdf if body is None else body, mime)},
            headers={'Idempotency-Key': key} if key else {})

    def test_pdf_upload_worker_result_and_source_coordinates(self):
        response = self.upload()
        self.assertEqual(response.status_code, 202, response.text)
        identifier = response.json()['id']
        self.assertEqual(response.json()['status'], 'queued')
        self.assertEqual(self.client.get('/v1/documents/'+identifier).json()['result'], None)
        self.assertEqual(run_once(self.settings, self.store)['status'], 'text_ready')
        record = self.client.get('/v1/documents/'+identifier).json()
        page = record['result']['pages'][0]
        self.assertEqual(page['method'], 'pdf_text')
        self.assertIn('120.00', page['text'])
        for word in page['words']:
            x0, y0, x1, y1 = word['bbox']
            self.assertTrue(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1)
        self.assertEqual(self.client.get(page['image_url']).status_code, 200)
        self.assertEqual(self.client.get(record['source_url']).content, self.pdf)
        self.assertIsNone(run_once(self.settings, self.store))

    def test_renamed_exact_duplicate_reuses_id_and_job(self):
        first = self.upload(key='first').json()
        second = self.upload(name='renamed.pdf', key='second')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first['id'], second.json()['id'])
        self.assertTrue(second.json()['duplicate'])
        self.assertEqual(first['job']['id'], second.json()['job']['id'])
        with self.store.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM documents').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
        self.assertEqual(self.upload(key='second', body=self.png, name='other.png', mime='image/png').status_code, 409)

    def test_idempotency_key_conflict_and_retry_rules(self):
        first = self.upload(key='fixed-key').json()
        conflict = self.upload(body=self.png, name='invoice.png', mime='image/png', key='fixed-key')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['error']['code'], 'idempotency_conflict')
        self.assertEqual(self.client.post(f"/v1/documents/{first['id']}/retry").status_code, 409)
        self.assertEqual(self.upload(key='bad key').status_code, 400)

    def test_malformed_spoofed_and_empty_files_rejected(self):
        for body, name, mime, status in [
            (b'', 'invoice.pdf', 'application/pdf', 400),
            (b'not a PDF', 'invoice.pdf', 'application/pdf', 415),
            (b'%PDF-1.7\nthis is broken', 'invoice.pdf', 'application/pdf', 422),
            (b'\x89PNG\r\n\x1a\nbroken', 'invoice.png', 'image/png', 422),
            (self.png, 'invoice.pdf', 'application/pdf', 415),
            (self.pdf, 'invoice.pdf', 'image/png', 415),
            (self.pdf, 'invoice.exe', 'application/pdf', 415),
        ]:
            with self.subTest(name=name, body=body[:12]):
                self.assertEqual(self.upload(body=body, name=name, mime=mime).status_code, status)
        self.assertEqual(len(self.store.list_documents()), 0)

    def test_encrypted_pdf_and_page_limit_rejected(self):
        self.assertEqual(self.upload(body=self.encrypted).json()['error']['code'], 'encrypted_pdf')
        with TestClient(create_app(replace(self.settings, max_pages=1))) as client:
            response = client.post('/v1/documents', files={'file': ('multi.pdf', self.multipage, 'application/pdf')})
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()['error']['code'], 'too_many_pages')

    def test_upload_bytes_and_image_pixel_limits(self):
        with TestClient(create_app(replace(self.settings, max_upload_bytes=20))) as client:
            self.assertEqual(client.post('/v1/documents', files={'file': ('invoice.pdf', self.pdf, 'application/pdf')}).status_code, 413)
            self.assertEqual(client.post('/v1/documents', content=b'x' * 70_000).status_code, 413)
        with TestClient(create_app(replace(self.settings, max_pixels=100))) as client:
            self.assertEqual(client.post('/v1/documents', files={'file': ('large.png', self.png, 'image/png')}).status_code, 413)

    def test_multipage_pdf_all_pages_retained(self):
        identifier = self.upload(body=self.multipage).json()['id']
        run_once(self.settings, self.store)
        record = self.client.get('/v1/documents/'+identifier).json()
        self.assertEqual(len(record['result']['pages']), 2)
        self.assertEqual([p['page'] for p in record['result']['pages']], [1, 2])

    def test_png_and_jpeg_uploads_accepted(self):
        for body, name, mime in [(self.png, 'invoice.png', 'image/png'), (self.jpeg, 'invoice.jpg', 'image/jpeg')]:
            self.assertEqual(self.upload(body=body, name=name, mime=mime).status_code, 202)

    def test_data_survives_application_restart(self):
        identifier = self.upload().json()['id']
        run_once(self.settings, self.store)
        with TestClient(create_app(self.settings)) as restarted:
            record = restarted.get('/v1/documents/'+identifier).json()
            self.assertEqual(record['status'], 'text_ready')
            self.assertIn('120.00', record['result']['pages'][0]['text'])

    def test_concurrent_uploads_create_one_document_and_job(self):
        def submit(index):
            response = self.upload(name=f'copy-{index}.pdf', key=f'parallel-{index}')
            self.assertIn(response.status_code, [200, 202], response.text)
            return response.json()['id']
        with ThreadPoolExecutor(max_workers=4) as pool:
            identifiers = list(pool.map(submit, range(4)))
        self.assertEqual(len(set(identifiers)), 1)
        with self.store.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_expired_worker_is_fenced_after_reclaim(self):
        identifier = self.upload().json()['id']
        original_job = self.store.claim()
        with self.store.connect() as connection:
            connection.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (original_job['id'],))
        replacement_job = self.store.claim()
        self.assertEqual(replacement_job['attempts'], 2)
        self.assertFalse(self.store.finish(original_job, result_key='old/result.json'))
        self.assertTrue(self.store.finish(replacement_job, error=DocumentError('test_failure', 'Intentional test failure.')))
        history = self.store.document(identifier)['attempt_history']
        self.assertEqual([attempt['status'] for attempt in history], ['lease_expired', 'failed'])
        self.assertEqual(self.store.document(identifier)['status'], 'failed')

    def test_two_workers_cannot_claim_same_active_job(self):
        self.upload()
        stores = [Store(self.settings), Store(self.settings)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda store: store.claim(), stores))
        self.assertEqual(sum(job is not None for job in claims), 1)

    def test_retry_is_bounded_and_reuses_document(self):
        identifier = self.upload().json()['id']
        for attempt in range(1, 4):
            job = self.store.claim()
            self.assertEqual(job['attempts'], attempt)
            self.store.finish(job, error=DocumentError('test_failure', 'Intentional test failure.'))
            response = self.client.post('/v1/documents/'+identifier+'/retry')
            self.assertEqual(response.status_code, 202 if attempt < 3 else 409)
        self.assertEqual(len(self.store.list_documents()), 1)

    def test_tampered_original_does_not_publish_result(self):
        identifier = self.upload().json()['id']
        original = self.settings.data_dir / self.store.document(identifier)['original_key']
        original.write_bytes(b'tampered')
        self.assertEqual(run_once(self.settings, self.store)['status'], 'failed')
        record = self.client.get('/v1/documents/'+identifier).json()
        self.assertEqual(record['job']['error_code'], 'original_integrity_error')
        self.assertIsNone(record['result'])

    def test_absent_document_and_page_return_404(self):
        self.assertEqual(self.client.get('/v1/documents/missing').status_code, 404)
        identifier = self.upload().json()['id']
        self.assertEqual(self.client.get('/v1/documents/'+identifier+'/pages/0/image').status_code, 404)

    def test_parser_deadline_rejects_without_creating_job(self):
        with TestClient(create_app(replace(self.settings, inspect_timeout=0.001))) as client:
            response = client.post('/v1/documents', files={'file': ('invoice.pdf', self.pdf, 'application/pdf')})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['error']['code'], 'processing_timeout')
        self.assertEqual(self.store.list_documents(), [])

    def test_worker_deadline_records_failure_without_partial_result(self):
        identifier = self.upload().json()['id']
        run_once(replace(self.settings, process_timeout=0.001), self.store)
        record = self.store.document(identifier)
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['last_error_code'], 'processing_timeout')
        self.assertIsNone(record['result_key'])

    def test_original_filename_cannot_choose_storage_path(self):
        identifier = self.upload(name='../../outside.pdf').json()['id']
        record = self.store.document(identifier)
        self.assertEqual(record['filename'], 'outside.pdf')
        self.assertTrue(record['original_key'].startswith('objects/'))
        self.assertNotIn('outside', record['original_key'])

    @unittest.skipUnless(shutil.which('tesseract'), 'Install Tesseract for real OCR integration checks')
    def test_rotated_scan_real_ocr_and_coordinate_bounds(self):
        response = self.upload(body=image_bytes(rotated=True), name='rotated.png', mime='image/png')
        identifier = response.json()['id']
        run_once(self.settings, self.store)
        record = self.client.get('/v1/documents/'+identifier).json()
        self.assertIsNotNone(record['result'], record['job'])
        page = record['result']['pages'][0]
        self.assertEqual(page['method'], 'ocr')
        self.assertIn('120.00', page['text'])
        self.assertEqual(page['transform']['ocr_rotation_cw'], 90)
        self.assertEqual((page['width'], page['height']), (1200, 1600))
        for word in page['words']:
            x0, y0, x1, y1 = word['bbox']
            self.assertTrue(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1)

    @unittest.skipUnless(shutil.which('tesseract'), 'Install Tesseract for real OCR integration checks')
    def test_blank_image_routes_to_review_not_successful_reading(self):
        identifier = self.upload(body=image_bytes(blank=True), name='blank.png', mime='image/png').json()['id']
        run_once(self.settings, self.store)
        record = self.client.get('/v1/documents/'+identifier).json()
        self.assertEqual(record['status'], 'needs_review')
        self.assertIn('no_readable_text', record['result']['warnings'])

    def test_missing_ocr_engine_failure_and_retry_after_configuration_fix(self):
        identifier = self.upload(body=self.png, name='scan.png', mime='image/png').json()['id']
        broken = replace(self.settings, tesseract_cmd='missing-tesseract-test')
        run_once(broken, self.store)
        self.assertEqual(self.store.document(identifier)['last_error_code'], 'ocr_unavailable')
        self.assertEqual(self.client.post('/v1/documents/'+identifier+'/retry').status_code, 202)
        self.assertEqual(self.store.document(identifier)['attempts'], 1)

    @unittest.skipUnless(shutil.which('tesseract'), 'Install Tesseract for mixed PDF OCR integration checks')
    def test_mixed_pdf_uses_embedded_text_and_ocr_per_page(self):
        identifier = self.upload(body=self.mixed_pdf).json()['id']
        run_once(self.settings, self.store)
        record = self.client.get('/v1/documents/'+identifier).json()
        self.assertIsNotNone(record['result'], record['job'])
        pages = record['result']['pages']
        self.assertEqual([p['method'] for p in pages], ['pdf_text', 'ocr'])
        self.assertTrue(all('120.00' in p['text'] for p in pages))

    @unittest.skipUnless(shutil.which('tesseract'), 'Install Tesseract for rotated PDF integration checks')
    def test_rotated_pdf_metadata_is_read_upright(self):
        writer = PdfWriter()
        writer.append(io.BytesIO(self.pdf))
        writer.pages[0].rotate(90)
        output = io.BytesIO()
        writer.write(output)
        identifier = self.upload(body=output.getvalue()).json()['id']
        run_once(self.settings, self.store)
        record = self.client.get('/v1/documents/'+identifier).json()
        self.assertIsNotNone(record['result'], record['job'])
        page = record['result']['pages'][0]
        self.assertIn('120.00', page['text'])
        self.assertLess(page['width'], page['height'])
