# Day 7 local release guide

Version 1.0.0 was implemented October 24, 2026, ahead of the original October 28 target. Days 1–7 of the agreed local portfolio build are complete. User acceptance testing is the next phase. The original broad production roadmap remains a later project.

## One terminal startup

```sh
cd "/Users/saifshahzad/D Drive/My Projects/Automated Reciept"
source .venv/bin/activate
python -m invoice_intelligence serve --port 8000
```

Open `http://127.0.0.1:8000/`. The launcher starts API + worker using one inherited configuration and stops its own children on Control+C. It binds localhost only. If a previous server occupies the port, it exits with an actionable message. It never kills that server or silently switches ports.

Normal data defaults to `data/runtime`, relative to the project folder. `--data-dir` is the explicit way to use an isolated workspace. An exported `INVOICE_DATA_DIR` also works; the launcher passes the same absolute location to both children. `.env` is documentation, not automatically loaded. The launcher checks port range/availability; `/health` provides the current version, OCR availability, worker heartbeat and text/extraction queue counts.

Manual two-terminal operation still works: `uvicorn invoice_intelligence.api.main:app --host 127.0.0.1 --port 8000` and `python -m invoice_intelligence.workers.runner`, with the same environment in both. Do not start an extra worker merely because the combined launcher already started one.

## Daily workflow

1. Upload one or several PDFs/PNGs/JPEGs. The queue reports per-file acceptance/reuse/errors and refreshes every five seconds.
2. Select a processed invoice and compare fields with highlighted source text.
3. Resolve missing values, item/arithmetic issues, and duplicate candidates. Use **Mark absent** to explicitly resolve an ambiguous optional field that is absent after checking the source; a routine blank input never silently dismisses ambiguity. Save corrections with your name/reason.
4. Import PO CSVs when relevant and check item quantity/unit-price findings.
5. Acknowledge remaining warnings/assumptions and any explicit PO exception; confirm or reject.
6. Export confirmed item rows as CSV, or full reviewed records as JSON. Exports preserve values/decisions and do not post to an accounting service.

The original extraction stays immutable. Human overrides remain marked corrected. Editing a decided record or explicitly reopening it returns it to pending. Draft inputs do not get overwritten by queue polling. A retry button is available for failed processing/extraction jobs; existing bounded-attempt rules apply. Missing saved artifacts produce a repair/restore message instead of an unhandled server error.

## Review-time pilot

Enter your reviewer name, choose **Human review pilot**, and click **Start timer** on a pending invoice. Inspect/correct it, explicitly pause for interruptions, and confirm/reject. Confirmation/rejection finishes the timer; the session records its start and end review revisions/status. You can finish early, but closing without a decision is excluded from completed-review medians.

The timer counts active browser time, pauses while the tab is hidden, and stops counting after 60 seconds without pointer/keyboard/scroll activity. It saves cumulative milliseconds every ten seconds and on transitions using sequence-checked, replay-safe events. Lost responses can be retried without adding time twice. Browser crashes can lose the last unsent seconds. Parallel tabs can overlap; no claim is made that session sums represent nonoverlapping labor.

The session kind is fixed when started; automated browser verification uses **Automated demo**. `/v1/review-time-report` keeps human and automated groups separate and reports null, rather than an invented median, when there are no completed human sessions. Names and activity are self-reported, not authenticated proof of work. A paired manual-entry trial and final correctness adjudication are still required before claiming accounting-team time savings.

## Export rules

The menu exports all currently confirmed records. An individual confirmed record also has a JSON export link. Records whose matching context changed, that predate accepted checks, or that are currently marked duplicate are excluded. Reopen and review them again first. CSV response headers report exported and excluded counts; JSON includes excluded stale IDs. Every exported CSV row is an item, with repeated invoice header values. Formula-like text is escaped for spreadsheet safety; JSON preserves the original string values.

## Backup and restore

Stop API/worker before taking a simple file copy. Back up the entire selected data folder, including `documents.sqlite3`, any WAL/SHM files that remain, `objects/`, `artifacts/` and `extractions/`. For a consistent live backup use a database-aware process; this release's beginner workflow is to stop first. Restore all files together and launch with `--data-dir /restored/folder`. Keep a copy of the previous folder until the restored one is verified. Never delete or replace normal runtime data merely to reset a demo; create a fresh demo folder instead.

## Reproduction and distribution

`python scripts/prepare_release_demo.py` builds the local mixed demo. It relies on the already downloaded benchmark and Day-3 fixtures; no dataset is needed for ordinary application use. `python scripts/evaluate_release.py` makes fresh timestamped calibration/test predictions, source/split hashes, metrics and replay evidence. Full raw predictions remain under local `reports/day7/evaluation/`; aggregate metrics are included in the app's `/evaluation` page.

`python scripts/package_release.py` creates a ZIP with code, docs, tests, lock file, examples, aggregate metrics and the reserved synthetic PDF. It excludes `.venv`, runtime data, raw benchmark documents, private predictions, caches and secrets. Benchmark documents are not redistributed. Use the existing source workspace for the prepared corpus demo, or upload your own invoices in a clean installation.

## What remains outside this release

No LLM was added, as requested. No public deployment, authentication, PostgreSQL migration, accounting writes/payments, tax-law certification, receipt matching or cumulative/partial invoicing was added. Shared-template supplier-held-out evaluation is not arbitrary-layout validation. A newly reserved layout is demonstrated as a needs-review smoke test, not a statistically established unseen-layout result. Human pilot timing will be collected during your next testing phase; automated timing is not a substitute.
