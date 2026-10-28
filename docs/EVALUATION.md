# Long-term evaluation protocol

The measured local release uses the smaller frozen InvoiceBenchmark partitions described in [Day 7 results](day7/EVALUATION.md). The larger dataset/reviewer design below is a future validation protocol, not a claim that this release collected those samples.

## Dataset and labels

Start with 1,200 synthetic base invoices across 24 distinct supplier/template families: 12 training/development families, 6 calibration families, 6 locked test families. Split the first 12 families into training and development documents; all layouts in the last 12 families stay out of prompt/example development. Target at least 300 independent test base documents, while recognizing this may be too small to certify rare-error targets. Template families must differ structurally, not just in logo or color. Store deterministic generation seeds and split assignments before rendering.

Generate clean, rotated, blurred, noisy, low-contrast, cropped, multipage, long-table, missing-field, ambiguous-date, mixed-tax, and arithmetic-error variants. All variants and duplicates of one base invoice stay in its partition. Include nonduplicate hard negatives sharing supplier/date/total and duplicate scans with changed filenames/quality. Evaluate duplicate positives using separate gallery/query views within each partition. Define duplicate as the same underlying payable invoice, not equal image appearance.

Public documents are supplementary: record source URL, license text/link, permitted use/redistribution, retrieval date, and privacy assessment before inclusion. No public dataset is presumed licensed merely because it is downloadable. Publish synthetic-only and public-document results separately. Never redistribute documents without permission.

Labels include header values, line rows/cells, source boxes, tax mode, duplicate group, PO match/mismatch, and intentional corruption. Double-check synthetic labels against rendered pages; generator truth can diverge from visible content. Have a second reviewer adjudicate ambiguous benchmark labels. Keep test labels unavailable to extraction/prompt tuning.

## Metrics and denominators

| Metric | Definition |
|---|---|
| Header accuracy | Correct normalized values / labeled values, separately for each field; report missing and hallucinated values |
| Critical record accuracy | Fraction of records with every required critical field correct; report for all and automatically ready subsets |
| Line-cell accuracy | Correct cells / labeled cells after fixed row alignment; unmatched rows count as errors |
| Line-row precision/recall/F1 | Exact correct rows against predicted/true row counts; include extra and missing rows |
| Duplicate precision/recall | Correct duplicate decisions / all duplicate decisions; found true pairs / all true pairs; include retrieval misses |
| Exception-review rate | needs_review / successfully extracted documents; also publish failures / all uploaded documents |
| Total human touch rate | All requiring confirmation / uploads (100% of successful records in this product) |
| Coverage | Automatically ready documents / all uploads; report alongside error rate |
| Cost | Observed OCR + model + retry + infrastructure allocation per page and document; labor shown separately |
| Latency | Upload-to-result p50/p95, and stage timings with queue time separated |
| Review time | Active review seconds to correct confirmation; median/p90 and error rate, paired against manual entry |

Pre-register normalization: Unicode and whitespace handling, supplier canonical IDs, conservative invoice-number normalization (retain significant zeros), ISO dates, currency-specific quantization and a documented amount tolerance. Missing ground-truth values and false populated predictions require explicit handling. Never silently omit failed documents from headline end-to-end metrics.

Align rows with a frozen matching cost using SKU/description and row order, then score every required cell. Do not align solely on the amount being evaluated. Treat split/merged rows with a documented policy. Report per-template, document-quality, page-count and seen/unseen-layout slices. Bootstrap confidence intervals by base invoice or supplier family so image variants are not independent samples.

## Confidence policy

Collect features from OCR quality, required-field completeness, evidence agreement, arithmetic residuals, schema validity, duplicate similarity, PO agreement and extraction disagreement. An LLM self-score alone is not a probability of correctness. Begin with conservative deterministic routing; train a simple error-risk classifier only after sufficient labeled examples exist.

Fit the error model on training/development examples, choose/calibrate the routing threshold using calibration labels, then freeze everything for test evaluation. If calibration needs model selection, subdivide calibration data or use nested folds. Report reliability bins, Brier score where probabilities exist, and risk-versus-coverage curves. Missing critical evidence, unsupported tax mode, duplicate ambiguity, and failed reconciliation are hard review gates regardless of score.

Pick the largest readiness coverage satisfying the critical-error target and its uncertainty bound. If the sample does not support the claim, say so and keep more invoices in review. A corrected invoice is a new labeled example for a later version; it must not leak into the current locked test.

## Review-time experiment

Use at least two reviewers when available and 30–50 documents per workflow as an initial pilot. Randomize assignment and order, counterbalance comparable batches, and avoid the same reviewer seeing the same invoice in both conditions. Record start, active time, pause, decision, edits, and final accuracy; report whether training/waiting time is included. A solo self-timed run is a pilot, not a general claim about accounting teams.

## Reproducible reports

Each run records dataset/split hashes, git revision, OCR/model/prompt/rule versions, seeds, hardware, provider usage/prices as observed, attempt costs, thresholds, and complete predictions. Store aggregate metrics, per-document error categories, confidence intervals and limitations in `reports/<run-id>/`. Do not commit sensitive source data or unredacted outputs.

Final demo: a clean invoice, rotated scan, multipage table, unseen layout, corrupted totals, exact duplicate, rescanned duplicate, and PO mismatch. Show source highlights, routing reason, human correction, audit history, and safe batch replay. Display measured metrics from the same frozen pipeline.
