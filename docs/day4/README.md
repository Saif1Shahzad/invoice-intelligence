# Day 4: structured local extraction and arithmetic review reasons

Implemented October 23, 2026, ahead of the original calendar schedule. At your request, this release uses **local extraction rules**, with no LLM, API key, model download or external invoice transfer. Adding an LLM remains a later integration, not a completed feature.

## What changed from Day 3

Day 3 produced readable page text and word locations. Day 4 organizes that text into the Day-2 field contract, verifies the source references, checks arithmetic and saves a versioned candidate result.

```text
PDF/image upload
  -> Day 3 text/OCR job
  -> saved page text and word boxes
  -> Day 4 extraction job
  -> supplier, reference, dates, currency, totals, tax components and items
  -> source-reference verification
  -> deterministic arithmetic checks
  -> ready_for_confirmation OR needs_review
```

Every successful extraction still requires a human. `ready_for_confirmation` is not an approval. The review/edit/confirm interface is Day 5.

## Start or restart both processes

Stop your old API and worker with Ctrl+C (Ctrl+Z only suspends them). Existing source files, text and database records are preserved. The schema update adds extraction tables; it does not reset documents.

Terminal 1:

```sh
cd "/Users/saifshahzad/D Drive/My Projects/Automated Reciept"
source .venv/bin/activate
export EXTRACTION_PROVIDER=local
uvicorn invoice_intelligence.api.main:app --reload --host 127.0.0.1 --port 8001
```

Terminal 2:

```sh
cd "/Users/saifshahzad/D Drive/My Projects/Automated Reciept"
source .venv/bin/activate
export EXTRACTION_PROVIDER=local
python -m invoice_intelligence.workers.runner
```

The same worker handles text and extraction as separate durable stages. It also discovers completed Day-3 text records that have no current extraction job. Existing uploads therefore do not need to be uploaded again. With many saved documents, allow the worker time to process the backlog.

The default provider is local. `EXTRACTION_PROVIDER=disabled` keeps text-only behavior for diagnosis. The application does not automatically load .env files; export settings in both terminals, and use the same INVOICE_DATA_DIR when customized.

## Test through /docs

1. Open http://127.0.0.1:8001/docs and check GET /health. It should show stage day4_local_extraction and extraction_provider local.
2. Upload `data/raw/invoicebenchmark/output/pdf/INV-2026-0002.pdf` through POST /v1/documents, or obtain its existing ID through GET /v1/documents. An exact reupload returning the old ID is expected.
3. Use GET /v1/documents/{document_id}. Poll while extraction.status is not_started, queued or processing.
4. Look at extraction.fields, extraction.validation and extraction.provenance.

For invoice 0002, the meaningful values are:

```text
extraction.fields.supplier_name.value -> ACME Laboratories International S.A.
extraction.fields.invoice_number.value -> INV-2026-0002
extraction.fields.total.value -> 188813.24
extraction.fields.line_items -> 6 rows
extraction.validation.issues -> total_mismatch
  expected -> 183313.83
  observed -> 188813.24
  difference -> 5499.41
extraction.status -> needs_review
```

The extractor reads the printed total, even when wrong. The validator computes an expected total from the extracted amounts. No answer-key total is supplied to the runtime.

Top-level document.status remains the Day-3 text-stage state, often text_ready. The new extraction.status describes the structured result. Job status succeeded means the program finished; it does not mean the invoice arithmetic passed.

## Process an already saved document explicitly

POST /v1/documents/{document_id}/extract queues extraction once for the current provider/version/text-input hash. It returns 202 for a new job or 200 with reused=true for an existing one. It does not rerun OCR.

```sh
curl -X POST http://127.0.0.1:8001/v1/documents/YOUR_DOCUMENT_ID/extract
curl http://127.0.0.1:8001/v1/documents/YOUR_DOCUMENT_ID
```

The worker must be running to execute queued jobs. Repeating the request does not create duplicate runs. Use POST /v1/documents/{id}/extract/retry for a failed extraction after fixing its cause; ordinary successful runs are reused. Retries have a three-attempt limit, independent of text-stage retries.

If an old text artifact is missing, the worker records a clear failed extraction instead of crashing the entire queue. Restore the text artifact and POST /extract again to establish its real input hash; retrying a placeholder missing-input profile cannot reconstruct deleted text.

## Source evidence: where did a field come from?

Each observed field includes:

- value: the normalized value, such as a decimal string or ISO date;
- status: observed, missing or ambiguous;
- evidence: page, normalized upright-page box, actual source text, method and span_ids.

`span_ids` refer to real words in result.pages[].words. Before saving a candidate, the runtime verifies that each referenced ID, source text, method and bounding box agree with the saved page data. This prevents invented locations. It does not mathematically prove that a semantic interpretation is correct.

Use the evidence page number to find the page's image_url. On Day 5 the UI will highlight those locations directly. A multi-line description has multiple evidence spans.

Missing information stays null. If a prose item only states an overall fee, quantity=1 and unit price are not invented as observations. Those missing details generate review reasons.

## What the local adapter supports

| Feature | Current behavior |
|---|---|
| Supplier/customer/reference | Explicit labels and a limited header-position fallback |
| Dates | English month names, ISO dates and unambiguous numeric dates |
| Currency | Explicit common ISO codes; dollar sign alone is ambiguous |
| Amounts | English, German and Swiss number separators; ambiguous forms require review |
| Table rows | Description / Qty / Unit Price / Amount columns with source geometry |
| Prose items | Explicit quantity × price = amount, or a named fee without invented quantity |
| Multipage | Repeated table headers and continued rows; conflicting references require review |
| Wrapped descriptions | Continuations retain multiple source spans |
| Tax basis | Explicit exclusive/inclusive/reverse-charge wording |
| Tax components | Printed per-rate amounts; their sum remains derived |
| Discounts | Printed applied amount, with conditional payment terms stored separately |
| Unsupported fields/layouts | Missing/ambiguous values and review reasons |

Supplier address assembly, broad SKU/table-column variation, arbitrary supplier layouts, languages, ambiguous number/date resolution and an LLM fallback are not implemented. The local rules are a baseline, not a general document-understanding model.

## Validation rules and limits

- quantity × unit price − observed/assumed line discount versus printed row amount;
- sum of complete observed row amounts versus printed subtotal;
- tax-component sum versus an explicitly printed tax amount where available;
- exclusive: subtotal − applied discount + shipping + tax versus printed total;
- inclusive: subtotal − applied discount + shipping versus printed total (do not add VAT twice);
- missing critical values, source/OCR warnings, conflicting fields, date ordering and repeated page content;
- credit notes and reverse-charge cases require explicit review.

Absent applied discounts/shipping can be treated as zero for arithmetic under a disclosed assumption. Their extraction values remain null. An explicitly stated but unresolved amount is not assumed zero. Conditional early-payment discounts do not automatically reduce the current balance.

These checks do not establish tax-law compliance or infer taxable bases/discount-tax policy. Every result lists skipped checks and assumptions. No calibrated confidence probability is produced. The tolerance is one currency minor unit for supported precision (JPY zero decimals, other current codes two).

## Saved results and safe retries

Three SQLite tables are added: extraction_jobs, extraction_attempts and extraction_runs. A job is keyed by document/provider/extractor-version/source-text hash. Each attempt has a lease token; stale workers cannot publish over a newer attempt. Successful candidates are append-only runs in the application code. Failed attempts publish no partial candidate and leave Day-3 page text intact.

Files live under data/runtime/extractions/<document>/<attempt>/extraction.json. Source documents and OCR artifacts remain separate. The API exposes successful run metadata through GET /v1/documents/{id}/extractions. Reviewer corrections and approval audit events have not been implemented yet.

Changing extraction rules for a later release requires a new VERSION so existing profiles are not silently overwritten. The current provider/version is local / local-rules-v1. Both the API and worker should be restarted after code changes.

## Automated checks and development demonstration

```sh
python -m unittest discover -s tests -v
python scripts/demo_day4.py
```

The demo uses only the 20 previously inspected DEVELOPMENT PDFs plus two OCR cases. It sends original files to the pipeline; only after extraction does the evaluation code read the mapped development labels. Calibration/test labels are not used for tuning or reporting here.

Each demo invocation creates a fresh runtime below data/runtime/day4_demo/ and writes reports/day4/development_metrics.json and per-document results. Demo IDs belong to that isolated database; use uploads in your normal API runtime for interactive testing. The report is a development diagnostic, not a held-out benchmark. Read [verification results](VERIFICATION.md) for denominators and exclusions.

There are no external requests or provider charges. Local CPU/storage/electricity and human review time are not priced. No review-time experiment has run yet.

## Next milestone

Day 5 adds the document-and-fields review interface, editable values/items, revalidation, human confirmation/rejection and an immutable correction history. Day 4 deliberately stops at versioned extraction candidates requiring confirmation.
