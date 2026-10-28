# Day 5 — review and correction

Day 4 gave the computer a first draft. Day 5 gives a person a screen for checking that draft and recording a decision. No paid API, frontend framework, npm install, or new Python dependency is required.

## Start your application

From this project's folder, stop any old API and worker using **Control+C** in their terminals. Control+Z suspends a process and may leave its port occupied. The worker does not reload automatically.

Terminal 1:

```sh
source .venv/bin/activate
uvicorn invoice_intelligence.api.main:app --reload --host 127.0.0.1 --port 8001
```

Terminal 2, in the same project folder:

```sh
source .venv/bin/activate
python -m invoice_intelligence.workers.runner
```

Open **http://127.0.0.1:8001/**. This is the new review screen. `/docs` still opens the FastAPI API explorer. Use the same `INVOICE_DATA_DIR` in both terminals if you previously customized it; default is `data/runtime`.

Existing documents remain in place. Starting the app creates the review tables in the existing database; it does not reupload invoices. Each successfully extracted document receives its initial review revision when first opened in the review screen.

## What the screen does

- **Documents:** upload an invoice, select an existing one, refresh, and page through the queue. The filter applies to the displayed page of 25. The extraction label describes the original computer draft; the review status describes the human decision.
- **Source:** the saved upright page image, page selector, zoom, and original download. A field's **Source** button highlights its original text. Missing fields and manually added rows may have no source box. Multiple evidence boxes can span several pages; use the page selector to see each page.
- **Review record:** edit header fields, line items, and tax components. Add/remove rows when necessary. Dates use the date picker; amounts use a decimal point and no thousands separator, for example `183313.83`. Rates are fractions: enter `0.20` for 20% and `0.02` for 2%; these units are shown in the labels.
- **Validation:** required-field gaps, line arithmetic, subtotal and total mismatches, and warnings. Saving reruns these checks on the reviewed values using Python Decimal arithmetic.
- **Decision:** enter a reviewer name and reason. Save corrections first, check the warnings/assumptions checkbox, then confirm. Reject is available even when required fields or arithmetic remain unresolved. A reason is required for rejection too.
- **History:** revision 0 is the original candidate; later revisions show who changed or decided what, the timestamp, reason, and before/after values. Saved edits survive a reload and server restart.

A value marked `corrected` is a human override. Its source box remains **original context**, not proof that the corrected value was printed. The initial extraction is never overwritten. Confirmation records a local review decision; it does not pay, post, or certify tax compliance.

## A concrete example from your dataset

`INV-2026-0002.pdf` has six extracted line items and a printed total of `188813.24`. The arithmetic currently gives:

```text
Subtotal          155350.70
Applied discount   -3107.01
Shipping                0  (explicit assumption)
Tax                31070.14
Calculated total  183313.83
Printed total     188813.24
Difference          5499.41
```

The extraction correctly preserves the printed amount. Therefore, the mismatch is a problem in the synthetic source invoice, not evidence that OCR read the number incorrectly. A reviewer can reject it and explain the discrepancy. Do not change a real invoice's payable amount merely to make a check pass; obtain an appropriate correction or follow the accounting team's policy.

For a **synthetic demonstration only**, you can save `183313.83` as an explicit human override with a reason describing the difference, then confirm after checking all rows and assumptions. You should see a new corrected revision followed by a separate confirmed revision. The source highlight and original extraction must still show `188813.24`.

## Test without touching your normal records

```sh
source .venv/bin/activate
python scripts/demo_day5.py
```

This processes three already inspected **development** PDFs into a new timestamped folder under `data/runtime/day5_demo/`. It prints an `INVOICE_DATA_DIR=... uvicorn ... --port 8002` command. Run that exact printed command, then open **http://127.0.0.1:8002/**. These three invoices are already processed, so the worker is unnecessary for this prepared demo. New uploads still require a worker using that demo folder.

Try these checks:

1. Open invoice `0002`; click **Source** beside Total. The printed value is highlighted. Confirmation is blocked by `total_mismatch`.
2. Reject it with your name and a reason, or perform the explicitly labeled synthetic correction described above. Open history and reload: the saved values and decision remain.
3. Open `0001` or `0005`, inspect every value and arithmetic assumption, enter your name/reason, check the acknowledgment, and confirm. Confirmed is a separate human state; “ready for confirmation” alone is never approval.
4. Open the same record in two browser tabs. Save a real change in the first. Attempt a change from the second without reloading: it receives a conflict and cannot overwrite the first. Copy any draft text you need, then use **Reload selected**.
5. Edit a value and try switching documents. The screen asks whether to discard unsaved changes. Selecting Keep editing preserves the draft.
6. Try adding/removing an item, clearing a required field, and entering invalid money in the isolated demo. Invalid typed values do not create revisions; valid but incomplete edits can be saved, but cannot be confirmed.

## How it is built

`api/main.py` serves the page and review endpoints. `web/index.html`, `style.css`, and `app.js` provide a plain HTML/CSS/JavaScript interface, packaged with the Python application. The browser uses `fetch` to send JSON value changes to FastAPI; the server validates their types and recalculates the invoice.

`persistence/reviews.py` stores immutable snapshots in `review_revisions` and a current pointer in `review_heads`. Every mutation checks `expected_revision` inside a SQLite write transaction. For example, after revision 2 is saved, an old request expecting revision 1 receives HTTP 409. Retrying the exact old decision also receives 409 and cannot append a duplicate decision. Reload to see whether a request succeeded if its response was lost.

Row edits carry `source_index`, preserving the correct source context when a different row is removed. Client requests contain values only; clients cannot invent source coordinates or mark an extraction observed. Human-added fields use `corrected` and an explicit reason without invented evidence. Provider extraction verification rejects a provider claiming human corrections.

Review revisions pin the extraction run and its text/page artifact. A newer extraction does not replace corrections silently. The reviewer can explicitly use the latest extraction, supplying their name/reason and resetting the current review to pending; all earlier revisions remain accessible. Saving actual corrections to an approved/rejected record also reopens it as pending. A no-op save does not reopen it or create history noise.

### Review API

| Method and suffix after `/v1/documents/{id}` | Purpose |
|---|---|
| `GET /review` | Current snapshot; initializes revision 0 once |
| `GET /review?revision=0` | Inspect an older snapshot |
| `PATCH /review` | Save corrected field/row values with actor/reason/expected revision |
| `POST /review/decision` | Approve or reject; confirmation enforces arithmetic and acknowledgment |
| `POST /review/rebase` | Explicitly adopt a newer extraction |
| `GET /review/history` | Correction/decision timeline |
| `GET /review/source/{run_id}/{page}` | Page image pinned to that document's extraction |

The extraction JSON contract adds `corrected` as a field status. `observed`, `missing`, and `ambiguous` retain their existing meanings. `docs/day2/extraction.schema.json` has been regenerated. Original candidates still use schema version `1.0`; this is an additive status extension. Validation rule version is now `invoice-validation-v2` to identify support for human overrides.

## Verification and remaining work

Run the full suite:

```sh
python -m unittest discover -s tests -v
```

See `VERIFICATION.md` for the measured checks. This remains a single-user localhost application. Reviewer names are self-reported, and SQLite triggers prevent ordinary updates/deletes of revision rows; a database administrator can still alter the database. This is not an authenticated or tamper-proof accounting audit system.

**Two planned project days remain:** Day 6 adds business duplicate candidates and basic purchase-order matching; Day 7 finishes evaluation, measured review timing, reliability checks, documentation, and the final demo. Business duplicate/PO matching, calibrated confidence, held-out evaluation, and active review timing are not implemented by Day 5.
