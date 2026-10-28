# Extraction field specification v1.0

This is the contract for future extraction, implemented in `src/invoice_intelligence/schemas/extraction.py`. It does not change the Day-1 `/v1/validate` request. That endpoint accepts a simpler tax-exclusive arithmetic input; it is not yet connected to documents or this new contract.

## Observation rules

A field carries `value`, `status`, `reason`, and `evidence`. `observed` requires a non-null value, at least one source span, and `reason: null`. `missing` or `ambiguous` requires `value: null` and an explanatory reason. Use `missing/not_printed` for absence, `missing/not_extracted` for incomplete processing, and `ambiguous/unreadable` when source text exists but cannot be read reliably. Do not use zero as a substitute for missing data.

Day 4 adds optional `span_ids` to each evidence entry for backward compatibility. The runtime requires observed extraction fields to resolve these IDs to actual Day-3 words and verifies their source text/method/box before publishing. The earlier hand-annotated example remains a structural example, not runtime output.

The contract ensures structural consistency; it cannot prove that a supplied box contains the claimed text. The extraction stage must verify span references against the document. Evidence references one-based pages, normalized upright-page `[x0,y0,x1,y1]` boxes with top-left origin, actual source text, and `pdf_text`, `ocr`, or `human` method. Store rotation transforms separately with page artifacts in Day 3/4. Combine multiple spans when a value wraps. Never manufacture boxes for calculated values.

Calculated values belong to validation/derivation results with formulas and input references, outside this observation contract. Model confidence alone is not proof of correctness. Every record still requires human confirmation.

## Header and document fields

| Field | Type when present | Meaning / rule |
|---|---|---|
| document_id | Nonempty string | Internal stored-document ID; not necessarily printed invoice reference |
| document_type | invoice / credit_note | Read heading/wording; preserve credit notes |
| supplier_name | String | Issuer, not Bill to/customer |
| supplier_address | String | Preserve visible address; benchmark automatic mapping deferred |
| customer_name | String | Recipient; optional for initial release |
| invoice_number | String | Printed reference, retaining significant zeros/punctuation |
| issue_date | ISO date | Normalize an unambiguous date; do not guess ambiguous numeric dates |
| due_date | ISO date | Printed date only; calculate payment-term due dates separately |
| currency | Three uppercase letters | Currency established by source; do not infer from supplier country |
| po_number | String | Explicit purchase-order reference; a framework-agreement number is not automatically a PO |
| tax_mode | exclusive / inclusive / reverse_charge | Textual meaning; missing/ambiguous if unclear |
| subtotal | Decimal | Printed subtotal; gross when label says including VAT; preserve errors |
| document_discount | Decimal | Signed reduction: `subtotal - document_discount`; normalize printed minus as a positive reduction, unless source actually reverses it |
| shipping | Decimal | Printed shipping charge; absent remains null |
| tax_amount | Decimal | Printed overall tax amount; per-rate component sum is derived separately |
| tax_rate | Decimal fraction | Single explicit rate, e.g. `0.20`; mixed/unstated rate remains null |
| total | Decimal | Printed final amount due, even if arithmetic is wrong |
| payment_terms | String | Observed wording such as Net 30 or 2/10 net 30 |
| conditional_discount_rate | Decimal fraction | Conditional rate in payment terms; does not change amount due automatically |

## Line items and tax components

Each line item has the same field wrapper for description, SKU, quantity, unit_price, amount, discount_amount, and tax_rate. Quantity is Decimal to allow fractional units. Unit prices and amounts retain the document's tax basis; do not call every printed amount `net_amount`. Preserve order, wrapped descriptions and negative signs. An empty item list represents no extracted rows; it must require review later.

Tax components use rate and amount wrappers. A document may have several components without a single global rate or printed combined tax total. The benchmark adapter currently maps header/row targets; tax-component array labels and address assembly are deferred and must be excluded from claimed coverage until implemented.

For prose such as “For maintenance, we invoice EUR 100”, do not present quantity=1 and unit_price=100 as independently observed cells. Those can be derived with an explicit assumption outside extraction. A product description containing “50 seats” does not imply invoice quantity 50.

## Normalization policy

- JSON money values serialize as decimal strings; arithmetic uses Decimal, not binary float. Preserve negative credit amounts. EUR uses two decimal places in this corpus; broader currency precision needs explicit policies.
- Normalize English `1,234.56`, Swiss `1'234.56`, and German `1.234,56` using document/context cues; ambiguous separators trigger review.
- Normalize Unicode and whitespace conservatively for matching. Do not silently equate different symbols in descriptions; record rendering discrepancies for adjudication.
- Rates use fractions rather than whole percentages. A discount rate must not be mistaken for VAT.
- Never copy benchmark metadata, answer keys, corrected totals or injected-error flags into model input.

## Later validation

Exclusive: sum of line amounts vs subtotal; subtotal - applied discount + shipping + tax vs total. Inclusive: printed gross subtotal already contains VAT, so do not add tax twice. Reverse charge, mixed rates, credit notes and unsupported rounding policies go to explicit review until their rule sets are implemented. Discounts need an observed base or a documented policy; the benchmark computes some discounts on net values even when the displayed subtotal is gross.

Schema validity does not mean invoice accuracy or approval. Blank/unsupported inputs may fit the observation schema while still failing processing acceptance.
