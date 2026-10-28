# One-week portfolio delivery plan

Updated October 24, 2026. Local release 1.0.0 is implemented ahead of the original October 28 target. Days 1–7 of the scoped local portfolio build are complete; user acceptance testing is next. This plan supersedes the delivery schedule in FIRST_SPRINT.md; PROJECT_PLAN.md remains the longer-term roadmap.

Day 2 completed October 23: see [the dataset and contract review guide](day2/README.md). This preparation does not claim extraction accuracy or unseen-template robustness.

Day 3 implemented early on October 23: [upload, text and OCR guide](day3/README.md). Local persistence uses SQLite because PostgreSQL/Docker were absent; PostgreSQL remains a later migration. This is an explicit change from the original storage proposal.

Day 4 implemented early on October 23: [structured extraction guide](day4/README.md). You selected local extraction rules; LLM integration is deferred. Current diagnostics are development-only, not held-out generalization results.

Day 5 implemented early on October 23: [human review guide](day5/README.md). The local review screen saves corrections, decisions and revision history while preserving original candidates. Two planned project days remain (Days 6–7); calendar target remains October 28.

Day 6 implemented early on October 23: [duplicate/PO review guide](day6/README.md) and [measured development benchmark](day6/BENCHMARK.md). One planned project day remains: final evaluation, active review timing and delivery checks. Original calendar target remains October 28.

Day 7 implemented October 24: [release guide](day7/README.md), [frozen evaluation](day7/EVALUATION.md), [verification](day7/VERIFICATION.md), and [acceptance checklist](day7/ACCEPTANCE_TESTING.md). Human review-time instrumentation is implemented; actual human pilot results will be collected during user testing. No human labor-saving measurement is fabricated.

## What finished means this week

A local application accepts a PDF or invoice image, extracts headers and line items, displays the document beside editable fields, explains validation/duplicate/PO issues, and saves a human confirmation with correction history. An evaluation command produces actual accuracy counts and timings on a fixed labeled sample. Every invoice requires human confirmation; no uncalibrated automatic approval.

This is a portfolio release with an explicit supported scope: English documents, bounded file/page sizes, one invoice per file, tax-exclusive arithmetic first, and local single-user use. Unsupported or unreadable inputs produce an actionable review/failure state. Public multiuser deployment, accounting-system writes, broad tax compliance and validated production reliability remain outside this week's release.

## Daily delivery

| Day/date | Work | Completion evidence |
|---|---|---|
| 1 / Oct 22 | Environment, API, arithmetic tests | Reported complete by developer |
| 2 / Oct 23 | Inspect 20 documents; map labels; freeze nullable extraction/evidence contract and development/calibration/test manifest | Dataset audit and mappings; printed and mathematically corrected amounts remain distinct |
| 3 / Oct 24 | Upload/storage, persistent records/jobs, file signature/limits, exact hashes and safe repeated requests; embedded text and OCR adapter | Clean and rotated document processed; repeated upload returns existing record |
| 4 / Oct 25 | Local extraction adapter (user-selected), multipage headers/items, source evidence, stage/error/usage capture, deterministic checks | Original PDF produces structured values; missing fields remain null; incorrect totals flagged |
| 5 / Oct 26 | Simple review UI, source highlights, editable items/fields, revalidation, approval/rejection and immutable correction history | Correct an invoice, confirm it, reload it, and inspect recorded changes; stale revision rejected |
| 6 / Oct 27 | Duplicate candidates, small CSV PO import and basic line matching; first benchmark and routing rules | Rescanned duplicate flagged for review, PO quantity/price mismatch explained, measured report generated |
| 7 / Oct 28 | Repair failures, frozen held-out run, replay checks, README/setup instructions and demo | Mixed batch demo, no extra records after replay, reproducible report with honest limits |

## Implementation choices

Keep the existing FastAPI/Pydantic backend and Decimal calculations. Use the implemented local SQLite store, durable job table and separate worker for this single-user release; PostgreSQL deployment is deferred. Serve a simple HTML/JavaScript review page from the backend to avoid a second application/toolchain. Use one OCR engine and the local extraction adapter; add an LLM provider later when explicitly selected. Do not build multiple provider integrations this week.

A model API integration requires the developer's local credentials and an agreed usage budget; never paste secrets into chat or commit them. External calls are optional until local upload, rendering and OCR work. The implemented local extraction provider remains usable without credentials. A future LLM provider must use actual configured credentials and real source inputs; fixture JSON is never represented as runtime extraction.

## Data and evidence limits

InvoiceBenchmark is a starting corpus, not proof of arbitrary-layout robustness. Inspect actual layout families before splitting; do not claim supplier-held-out evaluation if different suppliers share the same template. Keep invoice variants and business-duplicate groups together in one partition. Supplement with newly generated reserved layouts if the corpus lacks distinct families. Calibration is separate from prompt development and final test evaluation. A tiny calibration set only supports exploratory thresholds.

Map rendered invoice values to extraction targets; use corrected mathematical values only for checking validation decisions. Bound source evidence must resolve to actual OCR/PDF spans; missing evidence triggers review. Add separate original/scanned duplicate examples and labeled PO records, since these workflows are not established by the downloaded labels alone.

## Minimum acceptance checks

- Successful PDF and image uploads, malformed-file rejection, rotated scan, multipage example, and clear missing-data routing.
- Supplier/reference/currency/dates/totals/items displayed with source evidence or an explicit missing-evidence warning.
- Arithmetic mismatch, exact duplicate, candidate rescan duplicate, and PO discrepancy explained.
- Reviewer edits survive reload, remain distinguishable from initial extraction, and record actor/time/reason/revision.
- Repeated upload and crash/retry do not create extra canonical records; concurrent revision conflicts cannot silently overwrite edits.
- A fixed run reports field and line-item accuracy, processing failures, review rate, observed cost/latency, and measured review time. Duplicate precision/recall uses labeled pairs including hard negatives; report small-sample limitations.
- Final demo and limitations match the implemented behavior. No fabricated accuracy or cost claims.

## Deadline decisions

Prioritize the complete upload → extract → validate → review → save workflow. Limit PO matching to supplied CSVs and explicit quantity/unit-price comparisons; limit fuzzy duplicates to review candidates with reversible decisions. Keep OCR/model calls bounded with retry limits and record failed attempts. Advanced matching, learning from corrections and large-scale calibration belong after this release.

If an integration blocks progress for more than half a day, use a simpler documented implementation or mark that feature incomplete. A deadline does not justify silently omitting source evidence, human review or evaluation. Report remaining gaps on Day 7.
