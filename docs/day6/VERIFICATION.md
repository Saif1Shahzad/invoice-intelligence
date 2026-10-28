# Day 6 verification

Verified October 23, 2026, using the existing virtual environment, local extraction rules, SQLite and Tesseract. No new dependencies or external model credentials were used.

## Automated checks

Command: `.venv/bin/python -m unittest discover -s tests -v`

Result: **124 tests passed in 19.102 seconds**, including the previous 100 tests and 24 new matching checks. Output: local `reports/day6/tests.log`. Focused matching tests were rerun after the final additive PO-exception response field; output: `reports/day6/matching_tests.log`.

Also passed: `node --check src/invoice_intelligence/web/app.js` and Python compilation of source/demo code.

The new tests cover:

- Normalized identity matches, OCR-like references, missing-reference support, invoice/credit-note exclusion, and sequential-reference/supplier/currency hard negatives.
- PO exact SKU/description mapping, split-row quantity aggregation, ambiguous matches, missing/extra lines, supplier/currency/quantity/price differences, missing references.
- Strict bounded CSV input, BOM handling, malformed/invalid amounts, duplicate line IDs, invalid currency, atomic batch rejection and import reviewer/reason.
- Concurrent/replayed imports create one version; old-file replay does not revert newer PO state.
- The real upload/text/extraction pipeline feeding durable duplicate/PO review.
- Duplicate confirmation blockers, canonical/duplicate direction, reversal, stale pair decisions, invalid canonical choices, cycle prevention, and simultaneous decisions.
- Stale matching tokens after another invoice edit or PO update; decision-time snapshots and explicit PO-exception acknowledgment.
- Restart persistence, queue duplicate holds/recheck flags, exact-upload reuse, incomplete matching coverage, and append-only history triggers.
- Reopening a decided invoice is revision checked and audited.

## Browser checks

Used an isolated Day-6 runtime on localhost port 8003. The automated setup left pair decisions unresolved; browser actions then exercised real API-backed review controls:

1. Opened invoice 0005 PDF: saw its image-copy candidate, quantity 3 vs 2 and unit price 30202.7 vs 30201.70; confirmation was disabled by the unresolved pair.
2. Classified the image as duplicate with a reviewer/reason. PDF became canonical; history recorded the pair event.
3. Attempted confirmation with normal acknowledgment but no PO exception. The backend refused it with `po_exception_not_acknowledged`.
4. Explicitly accepted the synthetic PO exception and confirmed the canonical PDF. Its discrepancies remain visible and the decision snapshot/reason are preserved.
5. Opened the image copy: it remained marked duplicate and confirmation stayed disabled.
6. Reimported the generated CSV through the browser file chooser/form. The UI reported zero new versions and an already imported file; the existing confirmation remained saved.
7. Verified queue cards show duplicate holds and PO discrepancy counts, and the review page offers direct navigation to matching results.

The final screen also explicitly labels the accepted PO exception while keeping the original discrepancy details visible. Screenshots: local `reports/day6/matching-overview.png` and `reports/day6/review-full.png`.

The normal application runtime is separate from this synthetic demonstration. Demo/browser actions do not post, pay, or merge accounting records.

See `BENCHMARK.md` for extraction/duplicate counts, timings, the observed OCR description error, and the limitations of the five-file development sample. Actual active review time and frozen held-out evaluation remain Day 7 work.
