# Project plan

## Product and scope

Build a reviewer-assisted accounts-payable intake system. A batch becomes traceable invoice records with source evidence, validation results, duplicate candidates, purchase-order discrepancies, and explicit human decisions. Passing automated checks means “ready for confirmation”; it does not authorize payment or posting.

Assumptions: one developer, approximately 8–10 weeks full time, English invoices first, PDF/PNG/JPEG, one invoice per uploaded document, multipage support, and no direct accounting-system writes in the first release. These are planning estimates. Start with USD and PKR test data; encode currency precision rather than assuming all currencies have two decimals. Split combined invoice bundles in a later release. Tax checks reconcile stated amounts; jurisdiction-specific tax compliance is outside this scope.

## Delivery stages

| Stage | Time | Deliverable | Exit condition |
|---|---|---|---|
| 0: contracts and dataset | Week 1 | Canonical schema, evidence format, generator design, frozen split manifest, labeled sample | Ten sample invoices independently checked; holdout template families reserved |
| 1: vertical slice | Week 2 | Upload → durable job → page render/OCR → structured extraction → stored result | One clean and one rotated multipage invoice retrievable with field evidence; failed job can retry |
| 2: validation and duplicates | Weeks 3–4 | Decimal reconciliation, required-field checks, duplicate retrieval and scoring | Known mismatch and duplicate fixtures routed correctly; concurrent retries produce one record |
| 3: human review | Weeks 5–6 | Source viewer, field edits, reasons, confirm/reject, immutable revisions | Reviewer can trace each field, correct it, and confirm; stale edit receives conflict |
| 4: PO matching and robustness | Week 7 | CSV PO import, line matching, partial-billing checks, degradation tests | Quantity/price/currency mismatches explained; PO remainder considers prior approved invoices |
| 5: calibration and benchmark | Week 8 | Frozen policy, supplier-held-out evaluation, cost and timing report | Reproducible report includes denominators, confidence intervals, and failure slices |
| 6: demonstration and hardening | Weeks 9–10 | Batch demo, access controls, retry fault tests, operator guide | Demo replay produces no extra records; results match report and all decisions have audit entries |

## Architecture choices

Use a Python modular monolith with FastAPI and Pydantic contracts. PostgreSQL stores records, versions, jobs, audit events, and matching indexes. Keep PDFs/page images in local protected storage during development, behind an interface that can later use object storage. Start with a PostgreSQL job table and a separate worker process; add a queue service only if workload demonstrates a need.

Compare PaddleOCR against a simple OCR baseline on representative pages before selecting it. Preserve PDF text when reliable, use OCR for scans, and measure mixed-page behavior. Put any document model or LLM behind an adapter so it can be compared on the same inputs. Select the model after accuracy/cost measurements; do not couple business logic to a provider.

Build the review UI in React/TypeScript when the API and evidence contracts stabilize. Use a two-panel document-and-fields layout. This repository intentionally starts with the API and money checks so the first work can be tested immediately.

Reference documentation: [FastAPI](https://fastapi.tiangolo.com/), [PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html), [PaddleOCR](https://www.paddleocr.ai/). The supplied Upwork page returned HTTP 403 during planning; this plan uses the requirements included in the project brief.

## Functional backlog

1. Intake: batch identifiers, file signature validation, page/size limits, immutable original, SHA-256, tenant-scoped idempotency key.
2. Preprocessing: detect page orientation, deskew, render and retain transforms, classify blank/unreadable pages, extract embedded text when useful.
3. Extraction: supplier identity/name, invoice number, currency, issue/due dates, PO reference, subtotal, document discount, shipping, taxes, total, and line descriptions/SKU/quantity/unit price/line discount/net/tax.
4. Evidence: page number, bounding box, original text, extraction version, and field path for every extracted value. Missing evidence triggers review.
5. Validation: schema, required values, ambiguous date/currency checks, line arithmetic, subtotal, tax breakdown, total, and payment-term consistency. Never invent missing values.
6. Duplicates: exact bytes first; normalized supplier/invoice references and amount/date second; image/text similarities as candidate signals. Keep distinct scans as document versions; require reviewer confirmation for uncertain business duplicates.
7. PO matching: supplier/currency/PO-reference checks, SKU-first line matching, description candidates, quantity/price/tax tolerances, partial receipts/billing support. No PO is a distinct state rather than a false successful match.
8. Review: prioritized queue, source highlights, editable fields and items, revalidation, duplicate/PO decisions, reviewer identity, reason, before/after values, timestamp, optimistic locking.
9. Export: approved revision only; CSV first, with escaped spreadsheet formula prefixes; stable export key per destination/invoice/revision. Integration writes follow later.
10. Operations: stage timings, tokens/provider cost, attempt count, bounded retries with backoff, dead-letter state, cancellation, retention, model/prompt/version registry.

## Release acceptance targets

These are proposed targets, not results or client promises. Revisit feasibility using development data; lock targets and policies before opening the test labels.

- Header exact-match accuracy ≥97% overall; publish each field and seen/unseen template slice separately.
- Critical-field accuracy among automatically ready records ≥99%, with 95% confidence intervals; a small test set cannot establish this reliably.
- Line-row exact-match F1 ≥90%, with separate per-cell metrics.
- Duplicate precision ≥99% and recall ≥95% on a labeled candidate corpus; uncertain matches always need confirmation.
- Aim for ≤40% exception-review rate at the stated critical-field accuracy. All records still receive final human confirmation.
- Aim for ≥50% reduction in median active review time against manual entry on comparable randomized tasks.
- Set a cost budget after the week-2 baseline; report observed cost per page/document and retries. Never substitute provider list prices for measured usage.

If targets fail, publish the failure and reduce automatic readiness coverage; preserve review routing. Portfolio credibility comes from an honest benchmark.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Correct-looking invented values | Required evidence and independent arithmetic checks; missing data remains null |
| OCR failure on unusual tables | Page-level diagnostics, alternate OCR experiments, manual fallback |
| Leakage from synthetic variants | Split by supplier/template family before generating degradation variants |
| False duplicate merges | Candidate review, reversible links, no deletion based on fuzzy similarity |
| Concurrency or worker crash | Unique constraints, leases, transactional stage writes, replay tests |
| Overfitting calibration | Separate train/development/calibration/test partitions and frozen policies |
| Tax/rounding ambiguity | Explicit tax-inclusive/exclusive modes and configurable currency policies; unsupported cases reviewed |
| Provider outage or cost spike | Timeouts, bounded attempts, per-document spend cap, queued review fallback |
