# Day 3: upload a real file and read its text

> Historical text-stage guide. [Day 4](../day4/README.md) now adds structured fields and validation. The current worker processes that stage too; set EXTRACTION_PROVIDER=disabled in both terminals to reproduce text-only behavior.

Implemented and tested October 23, 2026 (we advanced to the Day-3 milestone early). OCR is now installed and integrated. No API key or external model call is required for this stage.

Verification: **47 tests passed**, including real OCR, persistence/concurrency/retry checks, mixed-page PDFs and rotation. See [recorded results](VERIFICATION.md).

## What you can do now

```text
Upload a PDF / PNG / JPEG
        |
Check bytes, filename, type, size and page limits
        |
Save original + document + durable processing job
        |
Worker reads the file in an isolated process
        |
Embedded PDF text OR rendered-page/image OCR
        |
Save page text + word boxes + upright page images
        |
Retrieve the result by document ID
```

The system does not yet turn that text into supplier/date/total fields. That is Day 4. The Day-1 arithmetic endpoint still works but is not automatically called by uploads. `text_ready` means readable page text is available; it does not mean the invoice is correct, approved, or ready for payment.

## Start it: two terminals

If an old Day-1 server is running, stop it with Ctrl+C before starting the new server on the same port. Both processes must run from the project root and use the same INVOICE_DATA_DIR when customized.

Terminal 1 — API:

```sh
cd "/Users/saifshahzad/D Drive/My Projects/Automated Reciept"
source .venv/bin/activate
uvicorn invoice_intelligence.api.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — worker:

```sh
cd "/Users/saifshahzad/D Drive/My Projects/Automated Reciept"
source .venv/bin/activate
python -m invoice_intelligence.workers.runner
```

The API accepts requests. The worker picks up saved jobs and does the slower reading/OCR work. If the worker is stopped, uploads stay queued and can be processed when it restarts. A crashed active job becomes reclaimable after its lease expires (default approximately four minutes); it is not immediately duplicated.

## Test without curl

1. Open http://127.0.0.1:8000/docs.
2. Execute GET /health. `ocr_available` should be true. This does not check whether a worker is alive.
3. Expand POST /v1/documents and click Try it out.
4. Choose `data/raw/invoicebenchmark/output/pdf/INV-2026-0002.pdf`. You may leave Idempotency-Key empty for the first test.
5. Execute. A new file returns HTTP 202, an `id`, and a queued/processing status. A previously uploaded identical file returns HTTP 200 with `duplicate: true` and its existing ID. The demonstration has already uploaded invoice 0002, so a duplicate response here is expected.
6. Copy `id`, open GET /v1/documents/{document_id}, paste it and execute. If still queued/processing, wait briefly and execute again.
7. Inspect `result.pages[0].text`, `method`, `words`, and `image_url`. JSON arrays start at zero, so pages[0] is page 1.
8. Open the image URL on the same server to view the page used for coordinates.

For the PDF you should see `method: pdf_text`. The text includes the printed `188'813.24` total. Day 3 reads it but does not yet flag the deliberate arithmetic error.

Now upload `data/generated/day3/rotated_scan.png`. Its method should be `ocr`, rotation should be 90 degrees clockwise, and its saved page should be upright. These file bytes differ from the PDF, so it gets a separate document ID. Matching rescans to the same business invoice is a later feature.

## Equivalent curl commands

From the project root, with API and worker running:

```sh
curl -X POST http://127.0.0.1:8000/v1/documents \
  -H 'Idempotency-Key: my-day3-pdf' \
  -F 'file=@data/raw/invoicebenchmark/output/pdf/INV-2026-0002.pdf;type=application/pdf'
```

`-F` sends a multipart file upload. This differs from Day 1's JSON request. `Idempotency-Key` is an optional request identifier: repeat the same key with the same bytes to get the same document, or use that key with different bytes to receive HTTP 409.

Replace YOUR_DOCUMENT_ID with the returned ID:

```sh
curl http://127.0.0.1:8000/v1/documents/YOUR_DOCUMENT_ID
```

Upload the same bytes under another filename: it still returns the same ID even without a request key. Changing the scan quality or rendering the PDF as a PNG changes its bytes and is not an exact duplicate.

## Status meanings

| Status | Meaning |
|---|---|
| queued | Original and job saved; waiting for worker |
| processing | Worker owns a time-limited lease |
| text_ready | Text stage completed with no configured OCR quality warnings; human approval still pending |
| needs_review | Text stage completed, but blank/unreadable/uncertain-orientation/low-score page needs attention |
| failed | Text stage did not complete; inspect job.error_code and job.error |

OCR recognition scores and orientation heuristics are not calibrated extraction confidence. Document-level review routing here is conservative engineering behavior, not a measured accuracy guarantee.

## Deliberate failure tests

- Upload `data/generated/day3/blank.png`: expect needs_review and no_readable_text.
- Upload `encrypted.pdf`: expect HTTP 422 / encrypted_pdf before a job is created.
- Upload `malformed.pdf`: expect HTTP 422 / invalid_pdf.
- Reuse an Idempotency-Key with different valid file bytes: expect HTTP 409 / idempotency_conflict.
- Rename a PNG to .pdf: expect HTTP 415 / file_type_mismatch.
- Exceed 20 MiB, 10 PDF pages or 25 million pixels per rendered page/image: expect HTTP 413.

For an actual failed processing job, correct the underlying problem and POST /v1/documents/{id}/retry. Only failed jobs may retry. The same document and job IDs remain; attempts increase, up to three. Ordinary failures do not retry automatically in a tight loop. Expired worker leases can be reclaimed automatically.

## Automated tests and demo

```sh
python -m unittest discover -s tests -v
python scripts/demo_day3.py
```

OCR integration checks require Tesseract; they skip if it is missing. In this workspace Tesseract was installed and the real OCR checks ran. The demo writes `reports/day3/verification.json`, detailed result JSON, and synthetic fixtures. It uses development invoice 0002 only and does not read benchmark answer keys or call an LLM.

The two-page fixture repeats the source as one text page and one scanned page. It tests per-page routing, not realistic multipage line-item continuation. The original invoice deliberately contains an arithmetic error; a successful text stage is not a correct accounting result.

## Local files and database

Default runtime folder: `data/runtime/` (ignored by Git).

```text
data/runtime/
  documents.sqlite3            Document, idempotency, job and attempt records
  objects/<sha256>.<extension>  Original file, stored by hash
  artifacts/<document>/<attempt>/
    page_1.png                 Upright page used for source coordinates
    result.json                Page text, spans, transforms, versions, timings
  incoming/                    Temporary files removed after intake
```

SQLite replaces the initial PostgreSQL plan for this local single-user release because PostgreSQL/Docker were not installed. This has been recorded as a scope decision; PostgreSQL and tenant-aware authorization are not implemented. Failed/crashed attempt artifacts can remain unreferenced; a retention/cleanup policy is still future work.

A SHA-256 hash is a fingerprint of file bytes. A database unique constraint prevents duplicate document rows for that fingerprint. Registration inserts the document, job and request-key binding in one transaction. A transaction commits all its database changes together or rolls them back. Original files are published before registration, so a crash can leave an orphan original but does not create a document pointing to a partially uploaded file.

Each worker attempt writes to its own directory. A lease token prevents an expired worker from publishing over a newer attempt. SQLite BEGIN IMMEDIATE serializes competing claims/registrations. These checks were tested with independent connections; PostgreSQL concurrency has not been tested because it is not the current database.

## Installation on another machine

```sh
python -m pip install -e '.[dev]'
brew install tesseract
```

For a snapshot of the tested Python versions:

```sh
python -m pip install -r requirements.lock.txt
python -m pip install -e '.[dev]'
```

The lock file does not install the native Tesseract executable. The workspace used Tesseract 5.5.3 with English and OSD language data. Verify with `tesseract --version` and `tesseract --list-langs`. If it cannot be found, set TESSERACT_CMD to its executable path in the worker/API environment.

Settings are read from environment variables. The application does not automatically load .env files. See `.env.example` for names. Keep the data directory consistent in both terminals. Keep the server on localhost; this stage has no login or tenant isolation.

## Limits and next step

Supported: local single-user PDF/PNG/JPEG intake, embedded text, English OCR, right-angle scan orientation, multipage page-level text, persistence and exact-byte duplicate handling. Unsupported: encrypted PDFs, arbitrary-angle deskew guarantees, handwriting, full field extraction, accounting approval, business duplicate matching and production-grade hostile-file sandboxing. Parsing occurs in a separate process with deadlines, but that is not an OS security sandbox.

Day 4 will map the text/spans into the Day-2 extraction contract with supplier, invoice number, dates, line items and totals, then attach deterministic validation results. It will not read answer keys as input.

Implementation references: [FastAPI uploads](https://fastapi.tiangolo.com/tutorial/request-files/), [Tesseract CLI](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), [PDFium threading restrictions](https://pypdfium2.readthedocs.io/en/stable/python_api.html), [SQLite](https://docs.python.org/3/library/sqlite3.html).
