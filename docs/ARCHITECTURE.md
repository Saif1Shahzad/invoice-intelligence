# Architecture and contracts

Day-3 implementation note: local document/job persistence uses SQLite with unique hashes, atomic registration, leased jobs and fenced attempt commits. The tenant-aware PostgreSQL/invoice approval design below remains the production roadmap. See [current behavior and limits](day3/README.md).

Day-4 implementation note: local rule extraction and deterministic validation now run as a second durable stage, with source-word verification, input hashes, fenced retries and successful candidate history. The user deferred LLM integration. See [current extraction behavior](day4/README.md).

## Processing flow

```mermaid
flowchart LR
  A[Batch upload] --> B[Immutable original + intake transaction]
  B --> C[Durable worker job]
  C --> D[Pages + orientation transforms]
  D --> E[Text/OCR + bounding boxes]
  E --> F[Schema-constrained extraction]
  F --> G[Arithmetic + duplicates + PO checks]
  G --> H[Ready for confirmation or exception review]
  H --> I[Reviewer revision + explicit decision]
  I --> J[Approved revision export]
```

States: received → processing → ready_for_confirmation / needs_review / failed. Human transitions lead to approved, rejected, or confirmed_duplicate. Reprocessing creates a new extraction run and never silently overwrites corrections or approval. An approved invoice changed by a reviewer becomes a new pending revision before another export.

## Persistence model to implement

- tenants/users/roles: authorization boundaries, including source-image reads.
- batches/documents/pages: tenant, original storage key, content hash, media metadata, page transforms and rendered artifact versions.
- jobs/job_attempts: stage, status, attempt, next-attempt time, lease owner/expiry, input digest, pipeline version, error category.
- extraction_runs: provider/model/prompt/schema/OCR versions, raw output reference, timings, usage and cost; immutable.
- invoices/invoice_revisions/line_items/field_evidence: canonical business record, immutable snapshots, decimal amounts, source references, active revision pointer.
- validation_results: rule code/version, severity, affected field, expected/observed values.
- duplicate_candidates/duplicate_decisions: candidate pair, signal scores, reviewer outcome and canonical-record link.
- purchase_orders/po_lines/po_matches: ordered and previously billed quantities, tolerances, line associations.
- review_tasks/audit_events: assigned actor, status, revision, reason, before/after patch, timestamp and correlation ID. Application database role cannot mutate prior audit rows.
- outbox/export_receipts: pending downstream effect and stable external reference.

Use numeric/Decimal for money and quantity, ISO date values, explicit currency, UTC event timestamps, and tenant IDs in access paths and uniqueness keys. Canonical values and original source text remain separate.

## Evidence contract

An evidence entry references an extraction run, JSON field path (e.g. `line_items[2].unit_price`), source page (one-based), normalized upright-page box `[x0,y0,x1,y1]` in [0,1], and OCR span IDs/text. Retain original-to-upright transformation so UI coordinates remain correct after rotation/cropping. A field can have multiple evidence spans. Derived totals are tagged derived and reference their input fields; they do not get invented source boxes.

Extraction values are nullable and carry missing/ambiguous/unsupported reasons. Document text is untrusted input: model instructions must prevent invoice text from invoking tools or changing extraction policy. Parse against a strict schema and route parsing failures to retry/review.

## Reconciliation contract

For tax-exclusive invoices: line net = quantity × unit price − line discount; subtotal = sum(line net); total = subtotal − document discount + shipping + tax. Avoid subtracting a discount twice. Validate each tax component and its base separately where available. Tax-inclusive invoices use a separate explicit rule set. Discounts, shipping tax, withholding, credit notes and currency rounding need labeled examples before automatic readiness is enabled.

The implemented starter only checks sums of supplied line nets and a tax-exclusive header equation. It deliberately returns a human-confirmation result and does not claim to validate tax rates, row arithmetic, evidence, or duplicates.

## Retry and duplicate guarantees

An idempotency key identifies one tenant request and binds to a payload digest; reuse with different bytes returns 409. Uniqueness on `(tenant_id, content_sha256)` returns an existing document for exact reuploads. These are separate from fuzzy business-duplicate decisions.

A worker claims a job with a database lease; stage outputs have a unique `(document_id, pipeline_version, stage, input_digest)` key. Commit result and next-stage outbox/job in one transaction. A crashed worker may repeat OCR/model calls, so track attempt cost, but cannot create another canonical record. Use compare-and-swap/row locking for invoice revision and approval transitions. Concurrency tests must run against PostgreSQL with independent connections.

Business duplicate signals nominate candidate pairs rather than enforcing a hard supplier/invoice-number uniqueness rule, since vendors can reuse references. Resolve confirmed duplicates to a canonical invoice without deleting originals. Include tenant boundaries in all searches. Export uniqueness uses `(tenant_id, destination, invoice_id, revision)` and a destination idempotency key; reconcile uncertain remote outcomes before retrying. Exactly-once remote side effects require destination cooperation.

## HTTP API roadmap (Day 3 adds document upload/list/get/source/page/retry; other business endpoints remain proposed)

| Method/path | Purpose |
|---|---|
| POST /v1/batches | Create batch |
| POST /v1/documents | Upload; return 202 and document/job IDs |
| GET /v1/documents/{id} | Stage, errors, result, evidence |
| GET /v1/review-tasks | Filterable queue |
| PATCH /v1/invoices/{id}/revision | Field/item patch with expected revision |
| POST /v1/invoices/{id}/decisions | Confirm/reject/duplicate with actor and reason |
| GET /v1/invoices/{id}/audit | Revision and decision timeline |
| POST /v1/purchase-orders/import | Validated CSV import |
| POST /v1/exports | Export approved revisions |

Use 422 for schema failures, 409 for stale revision/key conflicts, stable error codes, and correlation IDs. Authenticate every business endpoint; the starter is local development only.

## Operational boundaries

Validate magic bytes as well as extension, enforce page/size/time limits, isolate PDF rendering, disallow arbitrary fetch URLs, and reject encrypted or malformed inputs with actionable reasons. Protect secrets through environment configuration, encrypt storage in deployment, log IDs rather than invoice text, and configure raw-document/provider retention. Explicitly authorize any external model transfer. Add access tests, backup/restore checks, deletion procedures, and audit retention before real-client use.
