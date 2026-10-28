# Day 6 — duplicate detection and purchase-order matching

Day 5 checked whether an invoice made sense by itself. Day 6 checks it against **other invoices** and **what the business ordered**.

A purchase order (PO) records what a customer agreed to buy. For example, a PO might order 3 design sessions at EUR 100 each. An invoice for 4 sessions at EUR 120 should be flagged even when its own arithmetic is correct.

## Start the normal app

No new Python libraries, API keys, npm install, or external services are required. Stop and restart both old processes with **Control+C** (Control+Z suspends them).

Terminal 1, from the project folder:

```sh
source .venv/bin/activate
uvicorn invoice_intelligence.api.main:app --reload --host 127.0.0.1 --port 8001
```

Terminal 2, from the same folder:

```sh
source .venv/bin/activate
python -m invoice_intelligence.workers.runner
```

Open **http://127.0.0.1:8001/**. If you customized `INVOICE_DATA_DIR`, set the same value for both processes. Existing documents/reviews remain usable; startup adds the Day-6 tables (SQLite schema version 4).

The review page now has a **Duplicate & PO checks** jump link, matching results, pair-decision buttons, a CSV import form, and a PO-exception checkbox. Queue cards show duplicate holds and PO discrepancy counts. A previously confirmed record whose matching context changes is shown as `needs_recheck`; the earlier confirmation remains in history.

## Duplicate detection in simple terms

There are two different checks:

1. **Identical file bytes:** already implemented on Day 3. Uploading the exact same file under a different filename returns the existing document ID. No new record/job is created.
2. **The same business invoice in different files:** new on Day 6. A PDF and an image copy have different bytes and remain separate source documents, but their invoice identity can match. The app flags the pair for a person to inspect.

The rules compare normalized supplier/invoice number, then use date, currency, amount, and item descriptions as supporting evidence. Punctuation/case changes can normalize to the same identity. A narrow fuzzy rule supports OCR-like letter/digit substitutions (such as O/0), with matching date/currency/total. Missing references require matching supplier/date/currency/total and similar item descriptions. Different clean sequential invoice numbers do not match just because they look similar. Invoice/credit-note pairs with known different document types are excluded.

Thresholds in `matching/rules.py` are **development heuristics**, not calibrated probabilities: reference similarity 0.88, supplier similarity 0.90, and item-description similarity 0.92. There is no “99% confident” claim and no automatic approval or merge.

### Resolve a pair

Enter your reviewer name and a reason, then choose:

- **This is a duplicate:** keep the other source document as canonical. This record cannot be confirmed separately.
- **Other is a duplicate:** keep the currently selected document as canonical.
- **Different invoices:** record that you checked the pair and they represent different bills.
- **Reopen pair decision:** undo the classification by recording a new unresolved decision. Previous decisions remain in history.

“Canonical” means the record chosen to represent the bill. No source document is deleted or physically merged. The app rejects duplicate chains/cycles: choose a canonical record that is not itself already a duplicate. Reopen a prior pair decision before reversing its canonical direction.

Unresolved pairs block confirmation. Duplicate decisions are valid for the invoice values/extraction runs reviewed at that time. If either record changes, a prior decision becomes stale and requires another check. The card displays the latest reviewer/reason; `GET /v1/documents/{id}/duplicates/history` exposes the complete pair history for either document.

Failed, unfinished, or unreadable extractions are reported as incomplete duplicate coverage. They cannot be compared reliably. “No candidates” therefore means no match under the supported rules and current readable data, not a uniqueness guarantee.

## Import purchase orders

Expand **Import purchase orders** in the left panel. Download the template, fill it with your PO data, supply your name/reason, and upload the CSV. A local example is `examples/day6/purchase_orders_template.csv`.

The exact header order is:

```csv
po_number,supplier_name,currency,line_number,sku,description,quantity,unit_price
PO-DEMO-001,Example Supplier,EUR,1,PAPER-A,Paper cartons,2,50.00
```

One row represents one PO line. Repeat the same PO reference/supplier/currency for additional lines. `sku` may be blank; the other columns require values. Line numbers must be unique within a PO. Use UTF-8, a decimal point, no thousands separators, and uppercase three-letter currency codes. Quantity must be positive; unit price can be zero. Numbers support at most six decimal places and a value up to 1,000,000,000,000.

Limits: 1 MiB, 1000 item rows, and 100 POs per import. The whole CSV is validated before anything is saved: a bad last row cannot leave earlier rows partially imported.

Set the invoice's **Purchase order** field to its PO reference, supply a review reason, and save. If the invoice did not print a PO reference, this is an explicit manual assignment, marked corrected with no invented source evidence. Do not claim the extractor found an unprinted reference.

### What matching checks

- Supplier and currency agree with the PO.
- Match by an explicit invoice SKU when available; otherwise use exact normalized description.
- Flag ambiguous matches instead of choosing a line arbitrarily.
- Compare each matched invoice unit price with the PO price.
- Sum quantities when several invoice rows map to one PO line, then compare with the ordered quantity.
- Flag unmatched invoice items and PO lines missing from the invoice.

Quantity/unit-price comparison tolerance is 0.000001. A printed PO reference with no imported match produces `po_not_found`. No invoice reference produces **not_requested**, rather than a false “matched” result.

This version compares a **whole PO**. It does not track goods receipts, historical/cumulative invoicing, partial deliveries, units of measure, price conversion, or whether an order was already billed. A legitimate partial invoice can therefore need an explicit exception. These are later extensions, not hidden capabilities.

### Handle discrepancies

Fix genuinely incorrect data and save, reject the invoice, or explicitly accept the PO discrepancies with a reason. The **PO exception** checkbox is separate from the normal warnings/assumptions acknowledgment. Accepting a PO exception preserves the discrepancies and decision-time findings in history; it does not repair source values or bypass arithmetic/required-field/duplicate blockers.

Importing the identical CSV again reuses its import. Changed PO data creates an immutable version. Replaying an old file or already known content does not roll back a newer PO version. Import history is available through the API. There is no PO deletion/version-restore interface in this release.

## Try the prepared Day-6 demonstration

```sh
source .venv/bin/activate
python scripts/demo_day6.py
```

It creates a fresh timestamped runtime under `data/runtime/day6_demo/`, processes five development documents, creates/imports two explicitly synthetic POs, and writes a measured report. It prints an `INVOICE_DATA_DIR=... uvicorn ... --port 8003` command. Run that exact command and open **http://127.0.0.1:8003/**.

The five sources are PDFs `0001`, `0025`, `0005`, plus the provided image versions of `0001` and `0005`. They are already in the frozen Day-2 development partition; calibration/test labels are untouched. The images exercise OCR but are raster counterparts of the synthetic dataset documents, not independent physical scans.

The setup deliberately records manual PO assignments on the two PDFs. Its POs derive from observed item values, with known differences injected in one fixture. These are workflow tests, not independent client PO data or model predictions.

Try this:

1. Select **INV-2026-0001.pdf**. It has an image duplicate candidate and a matching `PO-DEMO-MATCH`. Confirmation is blocked until the pair is classified.
2. Inspect the image copy, enter your name/reason, and choose **Other is a duplicate** while on the PDF. The PDF is canonical; the image record remains blocked.
3. Select **INV-2026-0005.pdf**. Its `PO-DEMO-DIFFERENCE` orders quantity **3** at **30202.7**, while the invoice has quantity **2** at **30201.70**. Both differences are shown.
4. Resolve its image duplicate. Try confirming with only the ordinary acknowledgment: the server refuses the unaccepted PO exception. For this synthetic demo, provide a reason and check the PO-exception box to demonstrate explicit acceptance. The original differences remain visible.
5. Reload, inspect history, and open the image record. The decision survives reload; the duplicate record cannot be confirmed.
6. Reimport `reports/day6/purchase_orders.csv` through the page. It should reuse the import and create zero new versions.
7. Change a reviewed matching input in a second tab or import a changed PO after loading the first tab. An approval using the old matching context receives HTTP 409 and requires reload. Earlier confirmations are flagged for rechecking instead of being silently rewritten.

The running demo may already contain browser verification decisions. Rerun the script and use its newly printed command for a clean scenario. Your normal runtime is separate.

## How the pieces fit together

- `matching/rules.py`: deterministic duplicate and PO comparison rules.
- `matching/purchase_orders.py`: bounded CSV parser and value validation.
- `persistence/matching.py`: versioned POs, pair decisions, live findings, matching-context fingerprints, queue summaries.
- `schemas/matching.py`: typed duplicate-decision request.
- `persistence/reviews.py`: approval gates and immutable decision-time snapshots; reopening a decided review.
- `api/main.py` and `web/`: HTTP endpoints and review controls.
- `scripts/demo_day6.py`: development benchmark and reproducible demo preparation.
- `tests/test_day6_matching.py`: 24 new rule/integration checks.

A matching token is a digest of the reviewed inputs and findings, not a confidence score. Approvals recompute it inside the SQLite write transaction. If another invoice or relevant PO changes the findings, the old token cannot approve unseen results. Pair decisions additionally check the review revision, so retries/concurrent tabs cannot append the same stale action twice.

PO import/versions and duplicate decisions are append-only under SQL triggers. Reviewer names remain self-reported. A database administrator can alter the database; this remains a local prototype.

### New API routes

| Method and path | Purpose |
|---|---|
| `GET /v1/documents/{id}/matching` | Live duplicate and PO results plus matching token |
| `POST /v1/documents/{id}/duplicates/decision` | Record/reopen a pair classification with revision/token/actor/reason |
| `GET /v1/documents/{id}/duplicates/history` | Pair decisions involving this source |
| `POST /v1/documents/{id}/review/reopen` | Reopen a confirmed/rejected record with audit history |
| `GET /v1/purchase-orders/template` | Download CSV template |
| `POST /v1/purchase-orders/import` | Multipart file, actor, reason; atomic versioned import |
| `GET /v1/purchase-orders` | Current imported PO versions |
| `GET /v1/purchase-orders/{reference}/history` | All saved versions and import reviewer/reason |

Review approval requests now include `matching_token` and `acknowledge_po_exception`. The UI always sends the token. Older Day-5 API requests without it remain accepted only when there is no duplicate candidate and no requested PO match. Rejections still require a revision, reviewer and reason; they can be recorded despite unresolved matching findings.

`GET /review` matching results are explicitly **live**, including when inspecting an old revision. For the findings accepted at a historical confirmation, inspect its `matching_checks` entry in history. Queue summaries compare across all stored readable invoices, even though queue pagination/filtering shows 25 records at a time.

## Measured results and next day

Read `VERIFICATION.md` and `BENCHMARK.md`. Reproduce checks with:

```sh
python -m unittest discover -s tests -v
python scripts/demo_day6.py
```

**One planned project day remains: Day 7.** It covers frozen held-out evaluation, active human review-time measurement, final reliability/replay checks, fixes, and the final setup/demo documentation. Today's small development results do not establish unseen-template accuracy, broad rescan robustness, or calibrated confidence.
