# Benchmark label mapping v1.0

Implemented in `src/invoice_intelligence/domain/benchmark_mapping.py`. This module is an OFFLINE answer-key adapter, not an invoice extractor. It must not be called by upload/OCR/model inference. It produces candidate expected labels; no model has been evaluated.

## Mapping table

| Benchmark label | Project target | Treatment |
|---|---|---|
| vendor | supplier_name | Expected printed supplier |
| recipient | customer_name | Expected printed recipient |
| invoice_id | invoice_number | Printed reference; document storage ID is separate |
| date / due_date | issue_date / due_date | ISO labels corresponding to printed dates |
| currency | currency | EUR in this dataset |
| rendered_total | total | Printed total, including deliberate errors |
| total | mathematical_truth.total | Correct total for checking validation, never a substitute extraction target |
| rendered_subtotal | subtotal, exclusive | Printed subtotal, including deliberate errors |
| rendered_subtotal + vat_amount | subtotal, inclusive | Actual displayed gross subtotal; rendered_subtotal alone is still net-basis metadata |
| subtotal | mathematical_truth.subtotal | Net mathematical truth, not always printed subtotal |
| vat_amount | tax_amount | Printed for ordinary exclusive invoices; hidden for inclusive/reverse charge; derived sum for non-prose mixed VAT |
| vat_rate | tax_rate | Only when a single rate is actually stated; implicit-no-rate, mixed-rate and inclusive prose-summary cases are masked |
| discount_amount | document_discount | Only when an applied amount is printed; absence is null, not invented zero |
| discount.value where trade_terms | conditional_discount_rate | Observed payment condition; not an amount already deducted |
| payment_terms | payment_terms | Printed terms |
| is_credit_note | document_type | Credit note vs invoice |
| line_items[].description | description | Expected printed wording; known ↔/« discrepancy is marked needs_adjudication |
| line_items[].quantity | quantity | Printed for tables and multiunit prose; quantity-one prose is derived, not separately scored |
| line_items[].unit_price | unit_price | Net normally; round(net × (1 + row VAT rate), 2) for inclusive; implicit prose values are derived |
| line_items[].amount | amount | round(displayed unit price × quantity, 2), matching generator rendering |
| per-row vat_rate | line tax_rate | Not printed as row cells; do not score as observed |
| vendor_address | supplier_address | Present in raw labels; automatic assembly/localization deferred |
| shipping / PO / SKU | respective fields | No usable positive labels in this corpus; missing cannot measure positive extraction ability |
| variants / error_note | validation/evaluation metadata | Never model input; not extracted fields |

## Candidate target kinds

- `expected_printed`: expected visible value based on generator rules; eligible for value scoring after source verification.
- `derived`: calculated/inferred from printed inputs; excluded from observed-value scoring.
- `not_printed`: no source value; `value: null`; can score hallucinations through `score_absence`.
- `unlabeled`: this mapping has no ground-truth value; do not claim value accuracy.
- `unmapped`: label exists but mapping has not been implemented.
- `needs_adjudication`: known source/label discrepancy requiring manual judgment; excluded pending resolution.

`score_extraction` marks expected value comparisons; it is NOT a measured accuracy. An evaluator must separately count incorrect populated values on `not_printed` fields as hallucinations. Excluding absent values from the value denominator must not hide invented output.

The adapter writes normalized targets for DEVELOPMENT ONLY. It does not expose calibration/test labels to the extraction pipeline. Raw labels stay in the downloaded dataset, immutable. The 20 audited invoices are all in development. Do not blindly declare the other 105 development targets source-verified.

## Concrete examples from inspected documents

### Invoice 0002: incorrect total

Printed: 188813.24 EUR. Correct mathematical total in JSON: 183313.83 EUR. Extraction should return 188813.24 with source evidence. Validation should report a 5499.41 difference. Returning 183313.83 as the observed total would conceal the error.

### Invoice 0006: inclusive VAT and incorrect subtotal

Raw net subtotal is 12918.70; raw rendered_subtotal is 12923.70; canonical VAT is 2583.74. Printed gross subtotal is 15507.44 (= 12923.70 + 2583.74). Printed item amounts 6404.64 and 9097.80 sum to 15502.44: a 5.00 discrepancy. No separate VAT amount is printed; do not falsely claim that 2583.74 came from a source box.

### Invoice 0018: conditional terms

Payment terms say 2/10 net 30. The 2% applies only under a payment condition; the printed total does not already deduct it. Store the terms/rate separately. Do not treat a canonical discount_amount of 0.00 as a printed discount line.

### Invoice 0044: multiple tax lines

VAT lines are 13863.24 and 4886.17. Their sum, 18749.41, is derived, not a printed global tax amount. Raw per-item tax rates have no printed row cells. A framework-agreement reference is not a PO reference.

### Invoices 0041 and 0082: description glyph discrepancy

The raw translation description contains EN ↔ DE, but the inspected supplied PDF/image renders EN « DE. Treat this as a rendering/label issue. The adapter masks description targets containing ↔ rather than reporting a correct visible reading as an OCR error. Each affected record needs adjudication before exact description scoring.
