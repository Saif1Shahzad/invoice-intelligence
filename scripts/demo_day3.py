"""Create synthetic local fixtures and exercise Day 3 without a network service.

Uses DEVELOPMENT invoice 0002 only; never reads benchmark answer keys.
Stores synthetic demo records in the normal local runtime database.
"""
import io
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader, PdfWriter

from invoice_intelligence.api.main import create_app
from invoice_intelligence.config import Settings
from invoice_intelligence.workers.runner import run_once


def main():
    settings = Settings.from_env()
    generated = ROOT / 'data/generated/day3'
    report_dir = ROOT / 'reports/day3'
    generated.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'data/raw/invoicebenchmark/output'
    pdf = source / 'pdf/INV-2026-0002.pdf'
    png = source / 'png/INV-2026-0002.png'
    if not pdf.exists() or not png.exists():
        raise SystemExit('Download InvoiceBenchmark first; development invoice 0002 is required.')
    with Image.open(png) as image:
        image.rotate(90, expand=True).save(generated / 'rotated_scan.png')
        scan_buffer = io.BytesIO()
        image.convert('RGB').save(scan_buffer, format='PDF', resolution=200)
        (generated / 'scan_only.pdf').write_bytes(scan_buffer.getvalue())
    Image.new('RGB', (900, 1200), 'white').save(generated / 'blank.png')
    writer = PdfWriter()
    writer.append(pdf)
    writer.append(io.BytesIO(scan_buffer.getvalue()))
    writer.write(generated / 'two_page_fixture.pdf')
    writer = PdfWriter()
    writer.append(pdf)
    writer.encrypt('synthetic-demo-only')
    writer.write(generated / 'encrypted.pdf')
    (generated / 'malformed.pdf').write_bytes(b'%PDF-1.7\nNot a valid PDF document.\n')
    (generated / 'README.md').write_text('Synthetic Day-3 fixtures from DEVELOPMENT invoice 0002. The two-page fixture repeats the same invoice as a text page and image page to check page routing; it is not a realistic continuation invoice. The original contains a deliberate arithmetic error, which Day 3 reads but does not yet validate. Encrypted PDF password: synthetic-demo-only. Malformed PDF is intentionally broken.\n')
    cases = [('embedded_text_pdf', pdf, 'application/pdf'), ('scan_png', png, 'image/png'),
        ('rotated_scan', generated / 'rotated_scan.png', 'image/png'),
        ('mixed_two_page_pdf', generated / 'two_page_fixture.pdf', 'application/pdf'),
        ('blank_image', generated / 'blank.png', 'image/png')]
    summary = {'scope': 'Text/OCR integration demonstration, not structured extraction accuracy.',
        'data_dir': str(settings.data_dir), 'cases': [], 'rejections': [], 'network_model_calls': 0}
    with TestClient(create_app(settings)) as client:
        for name, path, mime in cases:
            response = client.post('/v1/documents', files={'file': (path.name, path.read_bytes(), mime)},
                headers={'Idempotency-Key': 'day3-demo:' + name})
            if response.status_code not in [200, 202]:
                raise RuntimeError(f'{name}: {response.text}')
            identifier = response.json()['id']
            while client.get('/v1/documents/'+identifier).json()['status'] in ['queued', 'processing']:
                outcome = run_once(settings, client.app.state.store)
                if outcome is None:
                    raise RuntimeError('A different worker owns this job; wait and rerun the demo.')
            result = client.get('/v1/documents/'+identifier).json()
            duplicate = client.post('/v1/documents', files={'file': ('renamed'+path.suffix, path.read_bytes(), mime)})
            assert duplicate.status_code == 200 and duplicate.json()['id'] == identifier
            # A new request key and a new filename still refer to the same bytes.
            pages = result['result']['pages'] if result['result'] else []
            summary['cases'].append({'case': name, 'document_id': identifier, 'status': result['status'],
                'reused_existing': response.json()['duplicate'], 'same_id_after_reupload': True,
                'methods': [p['method'] for p in pages], 'rotations_cw': [p['transform']['ocr_rotation_cw'] for p in pages],
                'word_counts': [len(p['words']) for p in pages], 'warnings': result['result']['warnings'] if result['result'] else [],
                'elapsed_seconds': result['result']['elapsed_seconds'] if result['result'] else None,
                'total_text_found': any("188'813.24" in p['text'] or '188813.24' in p['text'] for p in pages),
                'error': result['job']['error_code'], 'result_url': '/v1/documents/'+identifier})
            print(name, result['status'], [p['method'] for p in pages], flush=True)
            if result['result']:
                (report_dir / (name+'.result.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
        for path, expected_code in [(generated/'encrypted.pdf', 'encrypted_pdf'), (generated/'malformed.pdf', 'invalid_pdf')]:
            response = client.post('/v1/documents', files={'file': (path.name, path.read_bytes(), 'application/pdf')})
            assert response.status_code == 422, response.text
            assert response.json()['error']['code'] == expected_code
            summary['rejections'].append({'file': path.name, 'http_status': response.status_code, 'code': expected_code})
        conflict = client.post('/v1/documents', files={'file': ('other.png', png.read_bytes(), 'image/png')},
            headers={'Idempotency-Key': 'day3-demo:embedded_text_pdf'})
        assert conflict.status_code == 409
        summary['idempotency_conflict_status'] = conflict.status_code
    with TestClient(create_app(settings)) as restarted:
        summary['records_survive_restart'] = all(restarted.get(case['result_url']).status_code == 200 for case in summary['cases'])
    (report_dir / 'verification.json').write_text(json.dumps(summary, indent=2)+'\n')
    print('Saved', report_dir / 'verification.json')


if __name__ == '__main__':
    main()
