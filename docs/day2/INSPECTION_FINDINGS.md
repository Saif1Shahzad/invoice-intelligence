# Day 2 inspection findings

Completed October 23, 2026. This is dataset preparation and source inspection, not OCR/model evaluation.

## Corpus inventory

- 200 PDFs, 200 supplied PNGs, 200 Markdown documents and 200 JSON answer keys.
- 32 supplier names; every record uses EUR.
- All 200 PDFs are one-page generated documents. The 20 inspected PDFs have selectable embedded text.
- Layout labels: 67 table, 67 paragraph and 66 mixed (table rows with prose summary).
- Deliberate consistency labels: 120 correct, 40 total errors, 40 subtotal errors.
- Item counts range from 1 to 8. Tax-inclusive, reverse-charge, mixed-rate, conditional-discount and credit-note cases exist.

## What was actually checked

20 development documents were inspected using supplied PNG contact sheets plus text extracted from their PDFs and the matching JSON labels. Automated source checks found each mapped printed subtotal, printed total, supplier name, invoice number, and expected row amounts in those PDFs. These are substring/presence checks, not field-level extraction metrics. They do not verify every field location or prove complete table reconstruction. Visual observations and exceptions are recorded per document.

## Document notes

| Invoice | Layout | Injected consistency | Rows | Printed total EUR | Main inspection note |
|---|---|---|---:|---:|---|
| INV-2026-0001 | mixed | correct | 7 | 248054.76 | Table row description wraps onto a second line; seven item rows and prose summary are legible. |
| INV-2026-0002 | table | total_error | 6 | 188813.24 | Swiss apostrophe formatting is visible. Printed total 188813.24 differs from canonical 183313.83. |
| INV-2026-0006 | table | subtotal_error | 2 | 14856.50 | VAT-inclusive row amounts are 6404.64 and 9097.80. Printed subtotal 15507.44 is 5.00 above their sum. |
| INV-2026-0014 | paragraph | correct | 3 | -79621.32 | Credit-note heading and negative item amounts visible; the recipient is below the invoice body. |
| INV-2026-0044 | paragraph | subtotal_error | 5 | 128063.97 | Two separate VAT lines (20% and 10%) are printed; no combined tax-total line. Adjustment reference is not a PO number. |
| INV-2026-0005 | paragraph | correct | 1 | 70671.98 | One line item can have quantity two; single_item metadata means one row, not quantity one. German decimal format. |
| INV-2026-0018 | paragraph | subtotal_error | 8 | 229466.64 | Eight prose rows; printed gross subtotal is 50.00 below total. Several quantity-one rows omit unit-price and quantity labels. |
| INV-2026-0120 | mixed | correct | 4 | 69616.05 | Tabular items with German-format values; summary is prose and 5% discount amount is printed. |
| INV-2026-0183 | paragraph | correct | 5 | 153389.40 | Reverse-charge statement is visible and no separate VAT value is printed; long prose lines wrap. |
| INV-2026-0148 | paragraph | correct | 5 | 161509.37 | Gross prices with a printed discount calculated from net subtotal; do not recompute it using a gross base without evidence. |
| INV-2026-0025 | table | total_error | 1 | 13156.92 | One row with quantity one explicitly printed in the table; total-error example. |
| INV-2026-0017 | mixed | correct | 5 | 173887.68 | Five tabular rows and prose summary; long descriptions remain in table boundaries. |
| INV-2026-0041 | paragraph | total_error | 6 | 154253.98 | Negative finding: Translation description renders EN « DE in PDF text/image rather than raw JSON EN ↔ DE. Treat as a rendering/label discrepancy requiring adjudication, not OCR failure. |
| INV-2026-0162 | paragraph | total_error | 1 | 26326.86 | Single prose row explicitly shows quantity two and unit price; printed total is deliberately wrong. |
| INV-2026-0125 | table | total_error | 6 | 140793.63 | A table description wraps; 2/10 net 30 is a payment condition, not a 2% reduction already applied. |
| INV-2026-0008 | mixed | correct | 6 | 201192.60 | German-format table with conditional payment terms. Printed total equals subtotal plus VAT without taking 2%. |
| INV-2026-0082 | paragraph | correct | 5 | 228867.00 | Negative finding: Translation description renders EN « DE rather than raw JSON EN ↔ DE. Quantity-one prose rows omit explicit quantity and unit-price values. |
| INV-2026-0161 | paragraph | correct | 1 | 7796.12 | The obfuscated percentage is a document-level adjustment; it is not a per-row discount. One row has quantity 50. |
| INV-2026-0058 | mixed | total_error | 2 | 72314.44 | VAT-inclusive summary in prose, with German number formatting and a deliberately incorrect final total. |
| INV-2026-0094 | table | correct | 2 | 61939.35 | VAT amount is printed without its rate. An adjustment percentage is a discount signal and must not be mistaken for the VAT rate. |

## Consequences for implementation

1. Map printed values before scoring. Canonical mathematical totals are independent validation labels.
2. Tax-inclusive unit prices and subtotals need explicit tax basis. The Day-1 net-only validator cannot accept every observation directly.
3. Conditional 2/10 net 30 terms do not imply a currently applied discount.
4. Missing shipping/tax/PO values must not become invented zeros or references.
5. Quantity-one prose items can omit explicit quantity/unit price. Calculated values need a separate derived status outside observed extraction.
6. The translation description in 0041/0082 has a ↔ vs « rendering discrepancy. Affected description labels are masked pending adjudication.
7. Supplier-disjoint partitions still share layouts. New template families and degraded/multipage/duplicate/PO examples are needed for the original broad evaluation goals.
8. Human review is required for every invoice; no calibrated approval policy or accuracy claim was produced today.

## Files you can inspect

- `reports/day2/inspection.html`: image/answer-key comparison with individual observations.
- `reports/day2/inspection.json`: structured observations and presence-check results.
- `reports/day2/pdf_inventory.json`: measured PDF page counts.
- `data/splits/invoicebenchmark/*.json`: fixed partition manifests.
- `data/labels/invoicebenchmark/development/*.json`: mapped candidate targets, not predictions.
- `docs/day2/visual_review.json`: authored visual-review notes retained outside ignored reports.

## What remains unimplemented

No upload, OCR/model inference, source highlighting UI, database persistence, PO matching, duplicate scoring or accuracy benchmark was added today. The Day-1 API remains available. The new schema and offline mapping are preparation for those steps. Addresses and tax-component array label mapping remain explicitly deferred.
