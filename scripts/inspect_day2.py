"""Read-only PDF audit and local inspection report; does not run OCR/models.

Requires pdfplumber, pypdf and Pillow in the Python interpreter running this.
Run prepare_day2.py first. Supplied PNGs are used for visual contact sheets.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from invoice_intelligence.domain.benchmark_mapping import map_benchmark_label


def formatted(value, style):
    from decimal import Decimal
    number = format(Decimal(str(value)), ",.2f")
    if style == "german":
        return number.replace(",", "X").replace(".", ",").replace("X", ".")
    if style == "swiss":
        return number.replace(",", "'")
    return number


def main():
    import pdfplumber
    from pypdf import PdfReader
    from PIL import Image, ImageOps, ImageDraw
    out = ROOT / "data/raw/invoicebenchmark/output"
    report = ROOT / "reports/day2"
    report.mkdir(parents=True, exist_ok=True)
    ids = json.loads((ROOT / "data/splits/invoicebenchmark/inspection_sample.json").read_text())["document_ids"]
    review_path = ROOT / "docs/day2/visual_review.json"
    reviews = json.loads(review_path.read_text()) if review_path.exists() else {}
    page_counts = {p.stem: len(PdfReader(p).pages) for p in sorted((out / "pdf").glob("*.pdf"))}
    inspection = []
    for identifier in ids:
        raw = json.loads((out / "ground_truth" / f"{identifier}.json").read_text())
        mapped = map_benchmark_label(raw)
        with pdfplumber.open(out / "pdf" / f"{identifier}.pdf") as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        (report / f"{identifier}.txt").write_text(text + "\n")
        checks = {}
        for field in ["total", "subtotal"]:
            expected = mapped["fields"][field]["value"]
            checks[f"{field}_printed_number_found"] = formatted(expected, raw["variants"]["number_format"]) in text
        checks["invoice_number_found"] = identifier in text
        checks["supplier_found"] = raw["vendor"] in text
        checks["date_label_found"] = "Date:" in text and "Due:" in text
        checks["item_amounts_found"] = all(formatted(line["amount"]["value"], raw["variants"]["number_format"]) in text for line in mapped["line_items"])
        observations = ["Generated PDF has selectable text; this is not a scanned/OCR test."]
        v = raw["variants"]
        if v["consistency"] != "correct":
            observations.append(raw["error_note"])
        if v["vat_variant"] == "explicit_included":
            observations.append("Printed unit prices, row amounts and subtotal include VAT. JSON net values are not direct extraction targets; no separate VAT amount is printed.")
        if v["discount_variant"] == "trade_terms":
            observations.append("2/10 net 30 is conditional. Do not subtract 2% from the printed amount due.")
        if v["edge_case"] == "credit_note":
            observations.append("Credit note with negative prices/amounts: preserve signs and document type.")
        if v["edge_case"] == "reverse_charge":
            observations.append("Reverse-charge wording supplies no explicit VAT amount/rate. Zero VAT belongs to mathematical truth, not a fabricated source value.")
        if v["edge_case"] == "mixed_vat":
            observations.append("Multiple VAT rates. Per-row rates in the answer key are not printed row cells; a single global rate is not an extraction target.")
        if v["layout"] == "paragraph":
            observations.append("Items are prose. Quantity/unit price may be implicit for single-unit items; recipient block appears near the bottom in supplied PDF.")
        if v["layout"] == "mixed":
            observations.append("Line items are tabular; subtotal, VAT, discount and total appear in prose.")
        if v["number_format"] != "english":
            observations.append(f"Normalize {v['number_format']} thousands/decimal separators before arithmetic.")
        review = reviews.get(identifier, {})
        if review.get("note"):
            observations.append(review["note"])
        inspection.append({"document_id": identifier, "supplier": raw["vendor"], "variants": v,
            "page_count": page_counts[identifier], "line_count": len(raw["line_items"]),
            "printed_total": mapped["fields"]["total"]["value"], "correct_total": raw["total"],
            "printed_subtotal": mapped["fields"]["subtotal"]["value"], "canonical_net_subtotal": raw["subtotal"],
            "text_checks": checks, "observations": observations,
            "visual_review": review.get("status", "pending_agent_contact_sheet_review")})
    (report / "pdf_inventory.json").write_text(json.dumps({"page_counts": page_counts,
        "single_page_documents": sum(n == 1 for n in page_counts.values()),
        "multipage_documents": sum(n > 1 for n in page_counts.values())}, indent=2) + "\n")
    (report / "inspection.json").write_text(json.dumps(inspection, indent=2, ensure_ascii=False) + "\n")
    for batch in range(5):
        sheet = Image.new("RGB", (1600, 2320), "#e5e7eb")
        draw = ImageDraw.Draw(sheet)
        for j, identifier in enumerate(ids[batch * 4:batch * 4 + 4]):
            with Image.open(out / "png" / f"{identifier}.png") as im:
                thumb = ImageOps.contain(im.convert("RGB"), (780, 1110))
            x, y = (j % 2) * 800 + 10, (j // 2) * 1160
            draw.text((x + 8, y + 8), identifier, fill="black")
            sheet.paste(thumb, (x, y + 35))
        sheet.save(report / f"contact_sheet_{batch + 1}.png")
    esc = html.escape
    sections = []
    for row in inspection:
        identifier = row["document_id"]
        source = f"../../data/raw/invoicebenchmark/output"
        text = (report / f"{identifier}.txt").read_text()
        notes = "".join(f"<li>{esc(n)}</li>" for n in row["observations"])
        sections.append(f'''<section><h2>{identifier} · {esc(row['supplier'])}</h2>
<p>{esc(str(row['variants']))}</p><div class="pair"><a href="{source}/pdf/{identifier}.pdf"><img loading="lazy" src="{source}/png/{identifier}.png" alt="{identifier}"></a>
<div><p><a href="{source}/ground_truth/{identifier}.json">Original answer key</a> · <a href="../../data/labels/invoicebenchmark/development/{identifier}.json">Mapped candidate targets</a></p>
<table><tr><th>Value</th><th>Printed</th><th>Mathematical/net label</th></tr><tr><td>Total</td><td>{row['printed_total']}</td><td>{row['correct_total']}</td></tr><tr><td>Subtotal</td><td>{row['printed_subtotal']}</td><td>{row['canonical_net_subtotal']}</td></tr></table>
<ul>{notes}</ul><p>Visual review: {esc(row['visual_review'])}. Text presence checks: {esc(str(row['text_checks']))}</p><details><summary>PDF selectable text</summary><pre>{esc(text)}</pre></details></div></div></section>''')
    (report / "inspection.html").write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Day 2 invoice inspection</title>
<style>body{font:16px/1.6 system-ui;margin:32px auto;max-width:1500px;padding:0 24px;color:#172033;background:#f4f6fa}section{background:white;padding:24px;margin:24px 0;border:1px solid #dce1eb;border-radius:12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}img{width:100%;border:1px solid #ddd}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;font-size:13px}a{color:#1749a0}@media(max-width:850px){.pair{grid-template-columns:1fr}}</style>
<h1>Day 2 · 20 development invoices</h1><p>This is a static inspection report, not the application review UI. Images and answer keys are local. Candidate targets come from benchmark labels, not OCR or model predictions. Printed and corrected amounts serve different purposes.</p>
''' + "\n".join(sections) + "</html>\n")
    print(json.dumps({"sample_documents": len(inspection), "text_check_failures": {
        row["document_id"]: [k for k, value in row["text_checks"].items() if not value]
        for row in inspection if not all(row["text_checks"].values())},
        "single_page_documents": sum(n == 1 for n in page_counts.values()),
        "multipage_documents": sum(n > 1 for n in page_counts.values())}, indent=2))


if __name__ == "__main__":
    main()
