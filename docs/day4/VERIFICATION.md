# Day 4 verification

Verified October 23, 2026. **All 78 tests passed.** No LLM or external provider was used. The user selected local extraction rules instead of an LLM integration for this milestone.

## End-to-end example

For development invoice 0002, the pipeline extracted the supplier, reference, issue/due dates, EUR currency, subtotal, VAT, discount, printed total and six items. It preserved the printed total 188813.24 and reported total_mismatch with expected 183313.83 and difference 5499.41. Every observed field has resolvable source spans; the printed total was not replaced with an answer-key number.

## Development diagnostic: deliberately selected 20-PDF sample

| Measurement | Observed result |
|---|---:|
| Scored header values matched | 261 / 261 |
| Scored line-item cells matched | 286 / 286 |
| True / predicted rows | 81 / 81 |
| Missing / extra rows | 0 / 0 |
| Known-absent header targets kept empty | 78 / 78 |
| Exception-review routing | 13 / 20 (65%) |
| Failed documents | 0 / 20 |
| Human confirmation still required | 20 / 20 |
| External provider requests / charges | 0 / USD 0.00 |

These are development results, not held-out accuracy or generalization claims. The same 20 documents were inspected and used to debug the adapter. Shared templates and clean selectable-text PDFs make the sample easier than unfamiliar scans. Positive-value scoring omits missing/unprinted/derived/unmapped/disputed targets. Specifically, only 79 of 81 descriptions and 63 of 81 quantities/unit prices were eligible; implicit prose quantities and disputed glyph descriptions were not falsely treated as observed labels. Row exactness in the JSON is on available labeled cells, not every possible line attribute. Supplier address and SKU accuracy are not established.

## OCR checks

Ordinary and 90-degree rotated PNG versions of invoice 0002 both produced six items and the printed total 188813.24, with total_mismatch routing. These are two correlated checks on one invoice, not an OCR accuracy benchmark. The 20-document field diagnostic above uses native PDF text.

## Functional and integrity checks

- Complete header/table/prose observations, wrapped values and multipage continuation with repeated headers.
- VAT-inclusive arithmetic without adding VAT twice; mixed tax amounts remain derived when no global value is printed.
- Conditional payment discounts are not treated as already applied; unresolved stated discounts are not assumed zero.
- Ambiguous currencies/dates/numbers, unknown layouts, credit notes and missing implicit fields route to review.
- Source verifier rejects invented IDs, mismatched text, coordinates and methods.
- Text/extraction stages persist independently, and extraction survives application restart.
- Repeated/concurrent extraction requests reuse one profile job and successful candidate.
- Expired-worker fencing, attempt limits, input hashes and deadlines prevent stale/partial result publication.
- Discovery upgrades saved Day-3 text and records missing artifacts without crashing the queue.
- Existing Day-1/2/3 tests still pass; Day-3-specific tests select text-only mode deliberately.

## Actual saved artifacts

- reports/day4/development_metrics.json: per-field denominators, cases, routing and OCR checks.
- reports/day4/INV-2026-0002.pdf.result.json: complete example document/extraction/validation response.
- reports/day4/tests.log: final test output.
- reports/day4/code_provenance.json: source hashes and provider/version.

The demo uses an isolated runtime listed in development_metrics.json. Its IDs are not the normal API runtime IDs. Provider cost is zero because everything is local; local compute, storage and human review cost/time were not measured. Confidence calibration, purchase-order matching, business-duplicate precision/recall and human corrections/approval are later milestones.
