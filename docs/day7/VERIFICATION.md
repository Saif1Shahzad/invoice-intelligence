# Release verification

Verified October 24, 2026, in the existing macOS environment. Release version: 1.0.0. No LLM integration or external model requests.

## Automated checks

`.venv/bin/python -m unittest discover -s tests -v`

**140 tests passed in 20.810 seconds**, including the previous 124 tests and 16 release checks. Output: local `reports/day7/tests.log`. JavaScript syntax checks passed for `app.js`, `timing.js` and `evaluation.js`; Python source/scripts compile successfully.

New coverage includes replay-safe timing sequences, identity conflicts, elapsed-time bounds, closed sessions, exclusion of unfinished sessions from completed-review medians, human/automated separation, worker expiry/cleanup, confirmed-only export, stale-context export exclusion, spreadsheet formula text, missing-artifact error responses, scoring of failures/extra rows/absence/readiness thresholds, and explicit resolution of optional ambiguity without silently clearing blank inputs.

## Frozen evaluation

The runner processed 66 calibration and 84 test file variants. All predictions for both partitions were saved and hashed before labels were opened. No model/rule tuning followed test scoring. See `EVALUATION.md` for measured denominators and limitations; local `reports/day7/latest-evaluation.json` identifies the full reproducible report, source hashes, prediction lock and errors. Every source PDF was replayed; document/job/extraction-run counts stayed unchanged in both partitions.

## Mixed demo

`python scripts/prepare_release_demo.py --port 8004` created a fresh isolated demo with eight accepted sources and one malformed-PDF rejection. Clean, wrong-total, OCR duplicate, rotated, multipage, blank and reserved-layout cases reached appropriate result/review states. Both synthetic POs were imported. Replaying all accepted files left record/job/run counts unchanged. Setup and replay counts: local `reports/day7/demo_setup.json`.

The reserved PDF was authored after extraction-rule freeze, rendered with Poppler and visually inspected. It is readable and routed to needs_review. This is a smoke test, not evidence of broad unseen-template accuracy. The bundled Poppler emitted font-cache configuration warnings, but rendering completed and the resulting page was inspected; the application's PDF renderer uses its existing pypdfium2 pipeline.

## Browser verification

Started the combined launcher on localhost port 8004 against that isolated demo. Verified:

- API and worker start together; the UI reports an active heartbeat.
- Existing queue/review, PO discrepancy, human confirmation and history workflows remain usable.
- An explicitly automated-demo timer starts, pauses/resumes, and closes on a synthetic confirmation. Its saved active time was 21.203 seconds. It is not presented as human review-time evidence.
- A human timing report correctly remains at zero completed sessions / null median.
- Confirmed JSON download succeeds. The CSV endpoint exported the one current confirmed demo invoice, retaining its deliberately accepted PO discrepancies.
- Batch input supports multiple files; duplicate/rejection handling is exercised with a known source and malformed PDF.
- Reload retains the decision and saved timing events. The UI links the measured aggregate release report.

Local artifacts: `reports/day7/release-overview.png`, `reports/day7/browser-timing.json`, test logs and demo/evaluation reports. Browser demonstration decisions are labeled automated and affect only the isolated runtime. Human acceptance testing is deliberately the next phase.

## Product boundaries

This is the agreed local single-user portfolio product. Self-reported reviewer/timing identity, shared corpus layouts, extraction errors, one missed held-out duplicate, broad tax compliance, production authentication/deployment, and real labor-saving evidence remain explicit limitations. No accounting posting or payment was added. The final source ZIP excludes private runtime data and the raw benchmark corpus. It was extracted into a fresh temporary directory and its own packaged source was used to verify UI serving, API version/schema, timer assets and the shipped test aggregate. API/worker shutdown and restart preserved the demo confirmation and timing record. Final screenshots include `reports/day7/evaluation-overview.png`.
