# Day 5 verification

Verified October 23, 2026, in the existing Python 3.15 virtual environment on macOS. Runtime extraction provider: local rules. No external model requests were made.

## Automated checks

Command: `.venv/bin/python -m unittest discover -s tests -v`

Result: **100 tests passed** in **15.955 seconds**. The full output is in local `reports/day5/tests.log`. This includes 78 previous checks and 22 review checks. `node --check src/invoice_intelligence/web/app.js` also passed, including after the final display-label update.

The review tests exercise the real upload → embedded-text processing → local extraction pipeline once, then copy its isolated runtime per test. Manual missing-date/row corrections in the tests are explicitly reviewer inputs, not fabricated extraction outputs.

Covered:

- Real saved page images and review/static endpoints.
- Saving corrections, rerunning validation, retaining original extraction/evidence, restart persistence, and historical snapshot reads.
- Confirmation blocked by arithmetic errors, missing required values, and unavailable source pages.
- Acknowledgment required for warnings and arithmetic assumptions, even with no warnings.
- Rejection with unresolved fields; saving a later correction reopens a decided record.
- Simultaneous edits: one success, one HTTP 409; simultaneous initial reads create one baseline.
- Retried old decisions do not create extra revisions; equivalent decimals create no revision noise.
- Atomic rejection of invalid dates, invalid currency/tax mode, nonfinite/extreme money, unknown fields, supplied boxes, blank reviewer/reason, invalid/repeated row indices.
- Row addition/removal/reordering retains the correct source context using current source indices.
- Append-only SQL triggers reject ordinary history updates/deletes.
- New extraction does not overwrite corrections; adopting it requires an explicit revision-checked action.
- Pinned source routes reject another document's run ID.
- A provider cannot claim to have made human corrections.

The existing Starlette/httpx deprecation warning remains non-fatal. No new Python dependencies were added.

## Browser verification

Ran the app against three prepared development PDFs in an isolated timestamped Day-5 runtime on localhost port 8002. Manual browser actions verified:

1. Queue loads three extracted invoices with original extraction state separate from review state.
2. Selecting invoice 0002 displays six items and its total mismatch.
3. Clicking Total's Source button highlights the actual printed `188813.24` location on the saved page.
4. Saving a clearly labeled **synthetic demo override** to `183313.83` produces revision 1, marks the field corrected, retains the printed evidence, and clears the arithmetic mismatch.
5. Explicit acknowledgment and confirmation create approved revision 2. Reloading retains the correction/decision and shows all three revisions in history.
6. Invoice 0005 was rejected with a synthetic demonstration reason; its state persists after reload.
7. Switching documents with unsaved edits opens the discard dialog. Keep editing retains the draft; explicit discard/reload restores the saved version.
8. Final UI labels explain fractional rates (`0.20 = 20%`), matching the extraction contract. Browser console reported no warnings or errors in the final check.

Screenshots are local artifacts: `reports/day5/review-screen.png` (full page) and `reports/day5/review-overview.png` (viewport). `reports/day5/demo_setup.json` records the isolated runtime and IDs. These are demonstration artifacts, not measured accountant review time or extraction-accuracy evaluation.

## Limits

This is a localhost, single-user review application with self-reported reviewer names. SQL triggers are not protection against an administrator changing the database. Confirmation does not create a payment or accounting-system entry. Source highlights for corrected values show the original context, which may differ from the override.

Business duplicate/PO matching, active review-time measurement, calibrated routing, and frozen held-out evaluation remain in Days 6–7. No new claim of arbitrary-layout accuracy is made by these workflow tests.
