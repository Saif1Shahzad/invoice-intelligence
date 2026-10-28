# Whole-application acceptance checklist

Use a fresh isolated demo with `python scripts/prepare_release_demo.py --port 8000`, then run the printed launcher command. Existing demo decisions can be discarded by creating another fresh folder; do not delete normal data.

Record pass/fail, exact error text, document filename and reproduction steps. Expected review findings and HTTP 409 conflicts are not automatically software failures.

| Check | Action | Expected result |
|---|---|---|
| Startup | Run combined launcher | UI opens; Worker active; one API and worker use the same folder |
| Port conflict | Start a second launcher on the same port | Clear refusal; existing server is left running |
| Batch | Upload several supported files | Each accepted/reused/rejected result reported; queue refreshes |
| Native PDF | Inspect clean invoice 0001 | Structured values/items and source highlights |
| OCR duplicate | Inspect the image version of 0001 | OCR results; duplicate candidate despite different bytes |
| Rotation | Open rotated scan | Upright rendered source and extracted text or actionable review issues |
| Multipage | Open two-page fixture, change page selector | Both pages accessible; repeated/incomplete content requires review |
| Unfamiliar layout | Open reserved-layout.pdf | Source is readable; unresolved fields/items block confirmation |
| Blank/malformed | Open blank example; attempt malformed PDF | Blank cannot be confirmed; malformed bytes are rejected |
| Arithmetic | Open invoice 0002 | Printed total retained; calculated mismatch explained |
| Correction | Save a changed value with name/reason | Revalidation, new revision, original extraction unchanged |
| History/restart | Reload, stop/restart same data folder | Values, decisions, reasons and history persist |
| Duplicate decision | Inspect and classify image/PDF pair | Canonical direction saved; duplicate record cannot be confirmed |
| Reversal | Reopen a pair classification | Prior decision retained; pair becomes unresolved |
| PO match | Check 0001 assigned demo PO | Item/quantity/price match shown |
| PO discrepancy | Check 0005 assigned demo PO | Quantity 3 vs 2 and price 30202.7 vs 30201.70 flagged |
| Exception | Confirm without/with explicit PO acceptance | Missing acceptance refused; accepted exception remains visible/audited |
| Concurrent tabs | Edit same revision in two tabs | Second stale write returns conflict without overwriting |
| Changed context | Import changed PO after loading invoice | Old matching token cannot confirm unseen results |
| Replay | Upload identical source under new filename | Same document ID; no extra jobs/runs |
| Timer | Start human pilot, pause/resume, hide tab | Active time excludes pause/hidden/idle intervals; saves persistently |
| Timing honesty | Inspect timing report | Human and automated groups separate; no invented human median |
| Export | Export current confirmed record | Downloaded CSV/JSON has expected header/item/decision data |
| Export exclusion | Change matching context on a confirmed record | It is excluded until rechecked; no duplicate-held export |
| Shutdown | Control+C in launcher | Both owned processes stop; records remain |

After functional checks, collect a small human review-time pilot on fresh pending records. Avoid mixing your practice runs into the measured pilot. Record final correctness, interruptions and session type. A single reviewer's pilot is not a general labor-saving claim; a paired manual-entry comparison needs separate randomized/counterbalanced documents.

Developer verification: `python -m unittest discover -s tests -v`. The final verified suite has 140 tests. See `VERIFICATION.md` for the release's measured checks and limits.
