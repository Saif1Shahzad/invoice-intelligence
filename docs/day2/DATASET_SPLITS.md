# Dataset split policy

Seed: `invoicebenchmark-day2-20261023-v1`.
Source revision: `f0699d8c94468fb2fefaa22f669684b22e68c3d3`.

| Partition | Documents | Suppliers | Use |
|---|---:|---:|---|
| development | 125 | 19 | Build prompts/parsers, inspect failures, write regression fixtures |
| calibration | 33 | 6 | Later explore routing thresholds after freezing extraction choices |
| test | 42 | 7 | Final evaluation after extraction and policy choices are frozen |

Supplier names do not overlap between partitions. All PDF/PNG/Markdown/JSON versions of one invoice share a partition. The 20 inspected documents, including five previously opened examples, are in development. SHA-256 hashes in each manifest identify exact file contents. `docs/day2/split_summary.json` records manifest hashes.

## Why counts are not exactly 120/40/40

We grouped whole suppliers to prevent supplier identity leakage rather than splitting individual files at random. Supplier groups have different sizes. The 19/6/7 supplier allocation produces 125/33/42 documents.

## Important limits

These are supplier-disjoint splits, NOT an unseen-template benchmark. Three layout styles recur in every partition, and table/mixed layouts share the same item-table structure. The generator and global metadata were audited before partitioning, and the agent inspected representative styles. Do not claim the final test is an untouched external benchmark. It is a reserved record-level/supplier evaluation with known shared templates.

The dataset consists of generated clean one-page EUR documents. It has no supplied source boxes, matching PO corpus, labeled duplicate pairs, rotated scans or multipage examples. Reserve newly created template families, with labels, before developing against them if an unseen-layout claim is required. Keep augmented variants of a base invoice in its existing partition. Do not count PDF and PNG of the same document as independent samples.

No duplicate labels have been established. A corpus hash check can detect exact files but cannot prove that different invoices are different business payables. Later add labeled rescan duplicate groups and hard negatives and update/freeze a versioned manifest before their evaluation.

The 33 calibration and 42 test documents are too small to certify rare-error rates such as 99% accuracy. Report denominators and uncertainty. Confidence policies this week are exploratory and must preserve human confirmation.

## Regeneration and change control

From the project root:

```sh
python scripts/prepare_day2.py
```

It reads the local raw dataset, produces the same split manifests and development labels, and makes no network/model calls. Keep these assignments stable while building. Do not rerun with a different seed simply to improve final results. If the dataset changes, create a new version and explain why. Do not include raw labels in API/model inputs.

Generated local files are covered by the project's existing data/report Git ignores. The preparation script, schema, policy and small split summary live outside ignored data so a clone can regenerate them after downloading the pinned corpus.
