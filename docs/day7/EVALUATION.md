# Release evaluation - October 24, 2026

Predictions were frozen for both partitions before labels were opened. Calibration: 33 business invoices / 66 PDF-image files. Test: 42 business invoices / 84 PDF-image files. Supplier identities are disjoint; the three dataset layout styles are shared. This is not an unseen-template test.

| Metric | Calibration | Test |
|---|---:|---:|
| Processing failures | 0 / 66 | 0 / 84 |
| Correct positive header values | 852 / 862 | 1093 / 1098 |
| Correct absence checks | 260 / 260 | 330 / 330 |
| Critical records correct | 63 / 66 | 83 / 84 |
| Correct item cells | 1047 / 1070 | 1445 / 1468 |
| Exact rows on scored cells | 265 / 282 | 368 / 390 |
| Missing / extra rows | 2 / 0 | 0 / 0 |
| Duplicate TP / FP / TN / FN | 31 / 0 / 2112 / 2 | 41 / 0 / 3444 / 1 |
| Duplicate precision / recall | 100.00% / 93.94% | 100.00% / 97.62% |
| Same-supplier negative pairs | 344 | 508 |
| Exception review rate | 57.58% | 59.52% |
| Human confirmation | 100% | 100% |
| Median / p95 processing seconds | 1.054 / 1.785 | 1.062 / 1.765 |
| External-provider cost USD | 0.00 | 0.00 |

## Readiness threshold exploration

OCR scores are not probabilities. We evaluated fixed thresholds against calibration labels after freezing predictions. Readiness also requires complete critical fields/evidence and no existing validation issues. It is routine human confirmation, never automatic approval.

| Minimum OCR score | Calibration ready | Incorrect on scored values | Critical errors |
|---|---:|---:|---:|
| 0 | 28 / 66 | 6 | 0 |
| 60 | 28 / 66 | 6 | 0 |
| 80 | 28 / 66 | 6 | 0 |
| 90 | 28 / 66 | 6 | 0 |
| 95 | 18 / 66 | 2 | 0 |
| 98 | 15 / 66 | 0 | 0 |
| 100 | 15 / 66 | 0 | 0 |

The zero-observed-error exploratory policy selected an OCR threshold of 100, retaining 15/66 calibration files; effectively this conservative setting retained native-text PDFs and excluded OCR files. On test it retained 18/84 files with zero errors on the available scored values. This small sample does not certify rare-error safety. The runtime keeps its existing deterministic review gates and human confirmation requirement; this analysis is not presented as a calibrated probability or a new auto-approval feature.

## Reproducibility and scoring

`python scripts/evaluate_release.py` records source/rule hashes, split hashes, source-file hashes, frozen prediction hashes, hardware/Python/Tesseract information, timings, errors and replay counts in a fresh timestamped directory. Its complete latest report is identified by local `reports/day7/latest-evaluation.json`. The app includes the aggregate at `/evaluation` and `/v1/release-report`.

Header normalization uses Unicode NFKC and whitespace normalization; numeric comparisons use exact Decimal values. Item rows use a fixed positional alignment, never amount-based matching. Missing rows count as errors, and each extra predicted row adds four incorrect cells to the denominator. Positive/absence/unscored targets remain separate. Row exactness covers available scored cells, not unprinted implicit quantities or every possible attribute.

All source PDFs were replayed in each partition. Documents, jobs, extraction jobs and successful extraction-run counts were unchanged. Review, timing and export checks run separately from this extraction benchmark.

## Limits and remaining evidence

- Supplier-held-out identities share layout families. No general arbitrary-layout or physical-rescan robustness is established.
- PDF/image variants and pair comparisons are correlated; the displayed denominators are not independent experiments. No unsupported confidence interval or rare-error guarantee is claimed.
- The held-out run intentionally retains extraction/duplicate mistakes. The extraction rules were not tuned after test scoring. A future tuned version requires a new untouched final test set.
- Cost is observed external-provider usage (zero requests); local compute, electricity and human labor are excluded. Timing is local sequential processing, not a production throughput SLA.
- Human review timing is instrumented, but no completed human pilot or paired manual-entry comparison has been collected. The scripted browser session is labeled automated_demo.
- Synthetic PO fixtures verify comparison behavior, not independent real-world matching accuracy.
- The new reserved layout is a separate needs-review smoke test authored after rule freeze, not part of these accuracy denominators.
