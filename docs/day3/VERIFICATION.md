# Day 3 verification

Implemented and verified October 23, 2026. All 47 automated tests passed, including real Tesseract integration checks. No OCR tests were skipped in this workspace. `pip check` reports no broken requirements.

## Recorded demonstration

| Case | Result | Reading methods | Correction clockwise | Word counts | Pipeline seconds |
|---|---|---|---|---|---:|
| embedded_text_pdf | text_ready | pdf_text | [0] | [129] | 0.078 |
| scan_png | text_ready | ocr | [0] | [128] | 1.131 |
| rotated_scan | text_ready | ocr | [90] | [128] | 1.155 |
| mixed_two_page_pdf | text_ready | pdf_text, ocr | [0, 0] | [129, 129] | 1.161 |
| blank_image | needs_review | ocr | [0] | [0] | 0.483 |

The timings above are individual local demonstration runs and exclude queue delay, intake validation and interpreter startup. They are not a latency benchmark. The same development source invoice underlies the successful cases; these are not independent accuracy samples.

- All five cases retained the same document ID on exact byte reupload under another filename.
- Records remained retrievable after recreating the application against the saved database.
- Encrypted/malformed PDFs were rejected with 422 before creating processing jobs.
- Reusing a request key for different valid file bytes returned 409.
- A real temporary localhost server returned a healthy response and accepted an exact-reupload request through curl. That temporary server was stopped after verification.
- PDF and OCR source-box overlays were visually checked against the saved upright page images.
- The native engine is Tesseract 5.5.3 with English and OSD data. The Python dependency snapshot is requirements.lock.txt.

## Test coverage

Existing tests cover arithmetic, extraction contract, answer-key mapping and split integrity. Day-3 integration checks cover PDF/image intake, bytes/type/size/page/pixel checks, multipage text and mixed scanned/native PDF routing, native PDF rotation, rotated scan OCR, blank-page review, source coordinate bounds, persistence after restart, exact duplicates, request-key conflicts, concurrent registrations and claims, expired-lease fencing, bounded explicit retries, parser/worker deadlines, missing OCR configuration and original-file integrity.

## Scope decision and remaining limits

The prototype uses SQLite because no local PostgreSQL or Docker service was installed. No PostgreSQL or multiuser behavior is claimed. All stored documents are local single-user data. Model-based field extraction, accounting validation of uploaded text, approval history, business duplicate matching, PO matching and the reviewer application remain future stages.

The two-page demonstration repeats the same invoice in native and scanned form; it does not establish line-item continuation accuracy. Generated blank/encrypted/malformed fixtures test failure handling. No test labels were read by the runtime text pipeline, and no external model calls were made. OCR scores are not calibrated probabilities.

## Detailed local artifacts

- reports/day3/verification.json: actual case IDs, states, timings and replay results.
- reports/day3/*.result.json: full saved page text and word boxes.
- reports/day3/tests.log: full final test output.
- reports/day3/environment.json: exact tested runtime/engine versions.
- reports/day3/embedded_text_pdf.boxes.png and rotated_scan.boxes.png: diagnostic overlays.
