"""Reproducible inventory, supplier-grouped splits, audit sample and label mapping.

Run with: python scripts/prepare_day2.py
Reads local downloaded labels only; makes no network or model calls.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from invoice_intelligence.domain.benchmark_mapping import map_benchmark_label

SEED = "invoicebenchmark-day2-20261023-v1"
ANCHORS = ["INV-2026-0001", "INV-2026-0002", "INV-2026-0006", "INV-2026-0014", "INV-2026-0044"]


def stable_key(value):
    return hashlib.sha256((SEED + ":" + value).encode()).hexdigest()


def features(row):
    return {(key, value) for key, value in row["variants"].items()} | {
        ("row_count", str(len(row["line_items"])))
    }


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n")


def main():
    source = ROOT / "data/raw/invoicebenchmark"
    out = source / "output"
    records = [json.loads(p.read_text()) for p in sorted((out / "ground_truth").glob("*.json"))]
    if len(records) != 200:
        raise ValueError("Expected pinned corpus of 200 invoices")
    by_id = {r["invoice_id"]: r for r in records}
    # Previously opened documents and their supplier groups stay in development.
    anchor_vendors = {by_id[i]["vendor"] for i in ANCHORS}
    vendors = {r["vendor"] for r in records}
    remaining = sorted(vendors - anchor_vendors, key=stable_key)
    dev_vendors = anchor_vendors | set(remaining[:19 - len(anchor_vendors)])
    tail = [v for v in remaining if v not in dev_vendors]
    vendor_sets = {"development": dev_vendors, "calibration": set(tail[:6]), "test": set(tail[6:])}
    splits = {name: [r for r in records if r["vendor"] in group] for name, group in vendor_sets.items()}
    for a, ga in vendor_sets.items():
        for b, gb in vendor_sets.items():
            if a != b:
                assert not ga & gb
    selected = [by_id[i] for i in ANCHORS]
    covered = set().union(*(features(r) for r in selected))
    while len(selected) < 20:
        candidates = [r for r in splits["development"] if r not in selected]
        row = min(candidates, key=lambda r: (-len(features(r) - covered), stable_key(r["invoice_id"])))
        selected.append(row)
        covered |= features(row)
    sample_ids = [r["invoice_id"] for r in selected]
    metadata = json.loads((source / "DOWNLOAD_MANIFEST.json").read_text())
    for name, rows in splits.items():
        entries = []
        for r in rows:
            identifier = r["invoice_id"]
            paths = {k: str((out / folder / (identifier + suffix)).relative_to(ROOT)) for k, folder, suffix in [
                ("pdf", "pdf", ".pdf"), ("png", "png", ".png"),
                ("text", "invoices", ".md"), ("label", "ground_truth", ".json")
            ]}
            hashes = {key: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for key, path in paths.items()}
            entries.append({"document_id": identifier, "supplier_group": r["vendor"],
                            "layout": r["variants"]["layout"], "paths": paths, "sha256": hashes})
        write_json(ROOT / f"data/splits/invoicebenchmark/{name}.json", {
            "seed": SEED, "source_revision": metadata["revision"], "split": name,
            "grouping": "supplier_name; all formats stay together",
            "claim": "Held-out supplier identities, NOT unseen template families; shared three layout styles.",
            "documents": entries,
        })
    for row in splits["development"]:
        write_json(ROOT / f"data/labels/invoicebenchmark/development/{row['invoice_id']}.json", map_benchmark_label(row))
    inventory = {
        "source_revision": metadata["revision"], "seed": SEED, "documents": len(records),
        "suppliers": len(vendors), "currencies": dict(Counter(r["currency"] for r in records)),
        "variants": {k: dict(sorted(Counter(r["variants"][k] for r in records).items())) for k in sorted(records[0]["variants"])},
        "line_count_distribution": dict(sorted(Counter(len(r["line_items"]) for r in records).items())),
        "split_counts": {name: {"documents": len(rows), "suppliers": len(vendor_sets[name]),
            "layouts": dict(Counter(r["variants"]["layout"] for r in rows)),
            "consistency": dict(Counter(r["variants"]["consistency"] for r in rows))} for name, rows in splits.items()},
        "inspection_ids": sample_ids,
        "inspection_scope": "20 development invoices; no calibration/test invoice content in inspection sample",
        "limitations": ["Only EUR; reused layouts", "No supplied source boxes or PO pairs", "Clean generated files; no measured OCR robustness", "Global label/generator audit performed before split; not an untouched external benchmark"],
    }
    write_json(ROOT / "reports/day2/inventory.json", inventory)
    write_json(ROOT / "data/splits/invoicebenchmark/inspection_sample.json", {"split": "development", "document_ids": sample_ids})
    summary = {"seed": SEED, "source_revision": metadata["revision"],
               "split_counts": inventory["split_counts"], "inspection_ids": sample_ids,
               "limitation": "Supplier-disjoint splits reuse layouts. A genuinely unseen-template benchmark still needs additional templates.",
               "manifests": {name: hashlib.sha256((ROOT / f"data/splits/invoicebenchmark/{name}.json").read_bytes()).hexdigest() for name in splits}}
    write_json(ROOT / "docs/day2/split_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
