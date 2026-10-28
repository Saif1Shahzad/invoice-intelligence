# Day 2: dataset and extraction contract

Completed October 23, 2026. Start here to inspect today's work.

## What to open, in order

1. [Inspection findings](INSPECTION_FINDINGS.md): measured corpus inventory, notes for 20 documents, and limitations.
2. [Visual comparison report](../../reports/day2/inspection.html): local invoice images beside printed/corrected amounts, original JSON links, candidate-label links, and PDF text. Open the HTML in a browser if your editor shows its source. It uses relative paths, so keep it inside the project. It is a static report, not the future reviewer application.
3. [Field specification](FIELD_SPECIFICATION.md): the values our future extractor must return and how missing/ambiguous values and source evidence work.
4. [Label mapping](LABEL_MAPPING.md): how generator JSON becomes a valid comparison target. This is the most important evaluation detail.
5. [Dataset split policy](DATASET_SPLITS.md): why 125/33/42 documents, what each partition is for, and why this is not an unseen-layout test.
6. [Partial annotated example](../../examples/extraction.partial.json): four real source-grounded fields from development invoice 0002. Remaining fields default to not_extracted; this is not a complete prediction.

## Why this work matters

An OCR engine reads characters from an image. A model/parser organizes those characters into named fields. Validation checks arithmetic and business rules. Evaluation compares the output against a known answer. These are different jobs.

An answer key containing the mathematically correct total may disagree with a deliberately erroneous printed invoice. Our extraction target must reflect the source, while validation must expose the discrepancy. Otherwise we would train or score the extractor to hide errors.

A schema is a precise set of rules for structured data. The new Pydantic classes are the Python definition; `extraction.schema.json` is the machine-readable JSON Schema version. They describe a future extraction response. They do not yet change the Day-1 API's simpler validation input.

Source evidence means an actual page and a rectangular location containing the value. Normalized coordinates run from 0 to 1 so a highlight can scale with the page. Structural validation rejects missing or invalid boxes, but matching text to a box still needs the extraction implementation.

## How the partitions are used

- Development: inspect documents, adjust prompts/code and fix errors.
- Calibration: later choose review thresholds after extraction choices are frozen.
- Test: evaluate the final frozen version. Do not tune on these errors and still call the same run independent testing.

The splits keep supplier names separate. They do NOT keep the shared template styles separate. The calibration/test sets are small; they cannot substantiate rare-error production guarantees. Every invoice still gets human confirmation.

## Run the checks using your pip environment

From the project root:

```sh
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Rebuild the inventory, manifests, and development candidate labels without any extra library or network request:

```sh
python scripts/prepare_day2.py
```

For the optional PDF inspection report regeneration, install the audit tools in your virtual environment:

```sh
python -m pip install pdfplumber pypdf pillow
python scripts/inspect_day2.py
```

The original report was produced with the app's bundled PDF tools; these extra packages were not installed into your project environment during Day 2. Read-only PDF inspection has run; OCR has not.

## Inspect these three examples first

1. Invoice 0002: compare printed total 188813.24 with correct total 183313.83. Extraction must keep the printed number.
2. Invoice 0006: printed gross subtotal 15507.44 differs from net label 12918.70 and from actual row sum 15502.44. Read the tax-inclusive mapping before drawing conclusions.
3. Invoice 0018: read 2/10 net 30 and notice there is no applied-discount line. Conditional terms must not be deducted automatically.

## What is complete and what is next

Verification: all 24 tests passed. The existing health/validation endpoints also passed in-process smoke checks, including the deliberately incorrect total. The partial extraction example validates against the new contract.

Day 2 deliverables are complete: corpus audit, 20-document inspection, observation contract, explicit candidate-label mapping, supplier-grouped partitions, and regression/integrity checks. Mapping is deliberately partial where values are not visible, labels are missing, or rendering is disputed. No accuracy number has been fabricated.

Day 3 connects real documents to the backend: upload checks, protected storage, persistent document/job records, exact reupload handling, and document text/OCR preparation.
