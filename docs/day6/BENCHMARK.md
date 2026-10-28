# First Day-6 development benchmark

Measured October 23, 2026 using `python scripts/demo_day6.py`. Full machine-readable outputs are local `reports/day6/development_metrics.json`; processing logs are `reports/day6/demo_run.log`.

Five source files represent three business invoices: three PDFs and two dataset PNG counterparts. The files are drawn only from the frozen development inspection sample. Invoice 0001 and invoice 0025 share a supplier, supplying two same-supplier negative pairs when PDF/image combinations are considered. Variants stay within the same partition.

| Metric | Measured result |
|---|---:|
| Processing failures | 0 / 5 |
| Correct scored positive header values | 69 / 69 |
| Correct labeled absence checks | 16 / 16 |
| Correct scored line-item cells | 67 / 68 (98.53%) |
| Rows exact on available scored cells | 16 / 17 (94.12%) |
| Expected / predicted item rows | 17 / 17 |
| Labeled duplicate / nonduplicate pairs | 2 / 8 |
| True positives / false positives | 2 / 0 |
| True negatives / false negatives | 8 / 0 |
| Duplicate precision / recall | 100% / 100% on this tiny pair set |
| Same-supplier negative pairs | 2 |
| Original extraction exception-review rate | 1 / 5 (20%) |
| Matching exception-review rate, before pair decisions | 4 / 5 (80%) |
| Combined exception-review rate | 5 / 5 (100%) |
| Human confirmation requirement | 5 / 5 (100%) |
| Median upload → extraction/validation time | 0.549 seconds |
| Observed external-provider cost | USD 0.00 |
| Human review time | Not measured yet |

The two PO workflow fixtures returned the expected outcomes: one matched, one reported both `po_quantity_mismatch` and `po_price_mismatch`. The repeated CSV import and exact-file upload both reused existing state.

## The observed error

The PNG version of invoice 0001 produced:

```text
Expected: Travel expenses (Frankfurt–Zürich)
OCR:      Travel expenses (Frankfurt—Zirich)
```

This is counted as an incorrect description cell and an inexact row. It was not silently normalized away or presented as perfect extraction.

## Interpretation limits

- These are previously inspected development examples sharing the dataset's template families. They are not a held-out accuracy estimate.
- The duplicate figures have only two positive pairs. They do not prove reliable general duplicate detection, especially for damaged/missing identifiers or unrelated suppliers.
- Positive field/cell scores use only available labeled targets. Implicit quantities/prices and other unscored fields are not included as if independently verified. Known-absence checks are reported separately.
- Row exactness covers the available scored cells, rather than every possible invoice attribute. No missing/extra rows occurred in this run.
- Provided synthetic raster counterparts exercise OCR but do not represent diverse physical scanner/camera noise. Stronger rescan stress tests remain necessary.
- The POs were deliberately generated from observed item values with known changes. This tests the workflow and comparison rules; it does not estimate real-world PO-matching accuracy.
- USD 0.00 means no paid external provider calls. It excludes local compute/electricity and reviewer labor. Timing is a sequential run on this local machine, not a throughput/SLA claim.
- Combined review rate includes arithmetic/source issues and unresolved duplicate/PO findings. Every invoice still requires human confirmation, even without exceptions.
- Similarity thresholds are hand-chosen heuristics, not calibrated probabilities. No invoice is automatically approved.
- Actual active human review time remains explicitly unmeasured until Day 7; browser testing is not substituted for accountant review-time evidence.
