"""Source-driven local baseline: label rules, geometric tables and prose items.

No benchmark files, labels, supplier lists, LLMs or network calls are used here.
This deliberately limited adapter can later be replaced behind the same contract.
"""
from collections import defaultdict
from decimal import Decimal
import hashlib
import re

from invoice_intelligence.extraction.normalize import NUMBER, DATE, decimal, date_value
from invoice_intelligence.extraction.source import Line, choose, geometric_lines, missing, observed, verify_evidence
from invoice_intelligence.schemas.extraction import InvoiceExtraction

VERSION = "local-rules-v1"
PROVIDER = "local"
CURRENCIES = {"EUR", "USD", "GBP", "PKR", "INR", "CHF", "CAD", "AUD", "JPY", "CNY", "AED", "SAR"}


def numbers(line, start=0):
    return [(match, line.slice(match.start(), match.end())) for match in NUMBER.finditer(line.text, start)
            if not match.group().rstrip().endswith("%")]


def amount_field(line, start=0, *, reduction=False):
    candidates = numbers(line, start)
    if not candidates:
        return missing("amount_not_found")
    match, words = candidates[-1]
    if len(candidates) > 1 and not line.text[candidates[-2][0].end():match.start()].strip():
        return missing("ambiguous_spaced_number", candidates[-2][1]+words, ambiguous=True)
    try:
        value = decimal(match.group())
        return observed(str(abs(value) if reduction else value), words)
    except ValueError as error:
        return missing(str(error), words, ambiguous=True)


def first_rate(line):
    match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", line.text)
    if not match:
        return missing()
    return observed(str(abs(decimal(match[1], quantity=True)) / 100), line.slice(match.start(), match.end()))


def summary_kind(text):
    lower = text.lower()
    if re.match(r"(?:the\s+)?sub-?total\b", lower):
        return "subtotal"
    if re.search(r"\b(payment terms|bank|iban|bill to|credit note no|invoice no|invoice number)\b", lower):
        return "metadata"
    if "reverse charge" in lower:
        return "tax_mode"
    if re.search(r"\b(discount|rebate|adjustment per|less an agreed)\b", lower):
        return "document_discount"
    if re.search(r"\b(shipping|freight|delivery charge)\b", lower):
        return "shipping"
    if re.search(r"\b(vat|tax)\b", lower):
        return "tax"
    if re.search(r"\btotal\b|\bamount due\b|\bbalance due\b", lower):
        return "total"
    return None


def table_columns(line):
    words = line.words
    qty = next((w for w in words if w.text.lower().strip(".:#") in {"qty", "quantity"}), None)
    price = next((w for w in words if w.text.lower().strip(".:") == "price"), None)
    amount = next((w for w in reversed(words) if w.text.lower().strip(".:") in {"amount", "total"}), None)
    if not qty or not price or not amount or not any("description" in w.text.lower() or "item" == w.text.lower() for w in words):
        return None
    if not qty.bbox[2] < price.bbox[2] < amount.bbox[2]:
        return None
    return (max(0, qty.bbox[0] - .025), (qty.bbox[2] + price.bbox[0]) / 2,
            (price.bbox[2] + amount.bbox[0]) / 2)


def table_item(line, columns):
    q_start, p_start, a_start = columns
    groups = {"description": [], "quantity": [], "unit_price": [], "amount": []}
    for word in line.words:
        center = (word.bbox[0] + word.bbox[2]) / 2
        name = "description" if center < q_start else "quantity" if center < p_start else "unit_price" if center < a_start else "amount"
        groups[name].append(word)
    numeric = {name: numbers(Line(groups[name])) for name in ["quantity", "unit_price", "amount"]}
    if not numeric["amount"] or not numeric["unit_price"]:
        return None, groups["description"]
    item = {name: missing() for name in ["description", "sku", "quantity", "unit_price", "amount", "discount_amount", "tax_rate"]}
    if groups["description"]:
        item["description"] = observed(" ".join(w.text for w in groups["description"]), groups["description"])
    for name in ["quantity", "unit_price", "amount"]:
        if numeric[name]:
            match, refs = numeric[name][-1]
            cell_text = Line(groups[name]).text
            if len(numeric[name]) > 1 and not cell_text[numeric[name][-2][0].end():match.start()].strip():
                item[name] = missing("ambiguous_spaced_number", groups[name], ambiguous=True)
                continue
            try:
                item[name] = observed(str(decimal(match.group(), quantity=name == "quantity")), refs)
            except ValueError as error:
                item[name] = missing(str(error), refs, ambiguous=True)
    return item, []


def prose_item(line):
    text = line.text
    multi = re.match(r"(.+?):\s*(\d+(?:[.,]\d+)?)\s*[×x]\s*(.+?)\s*=\s*(.+)$", text, re.I)
    if multi:
        item = {name: missing() for name in ["description", "sku", "quantity", "unit_price", "amount", "discount_amount", "tax_rate"]}
        item["description"] = observed(multi[1].strip(), line.slice(*multi.span(1)))
        try:
            item["quantity"] = observed(str(decimal(multi[2], quantity=True)), line.slice(*multi.span(2)))
        except ValueError:
            item["quantity"] = missing("ambiguous_number", line.slice(*multi.span(2)), ambiguous=True)
        unit_line = Line(line.slice(*multi.span(3)))
        amount_line = Line(line.slice(*multi.span(4)))
        item["unit_price"] = amount_field(unit_line)
        item["amount"] = amount_field(amount_line)
        if item["amount"]["status"] == "observed":
            return item
    single = re.match(r"For\s+(.+?),\s+we invoice\s+(.+)$", text, re.I)
    if single and numbers(Line(line.slice(*single.span(2)))):
        return {"description": observed(single[1], line.slice(*single.span(1))),
            "quantity": missing("implicit_quantity_not_observed"),
            "unit_price": missing("implicit_unit_price_not_observed"),
            "amount": amount_field(Line(line.slice(*single.span(2)))),
            "sku": missing(), "discount_amount": missing(), "tax_rate": missing()}
    return None


def extract(document_id, source):
    lines = geometric_lines(source)
    candidates = defaultdict(list)
    problems = {}
    warnings = []
    tax_lines = []
    items = []
    columns = None
    previous_item = None
    pending = []
    supplier_done = False
    bill_to = False
    page_fingerprints = set()
    for page in source["pages"]:
        fingerprint = hashlib.sha256(" ".join(w["text"] for w in page["words"]).encode()).hexdigest()
        if page["words"] and fingerprint in page_fingerprints:
            warnings.append("repeated_page_content_requires_review")
        page_fingerprints.add(fingerprint)

    def add(name, value, refs):
        candidates[name].append((value, refs))

    def accept(name, field):
        if field["status"] == "observed":
            # Source refs are selected afresh by callers; resolve supplied evidence IDs.
            ids = {identifier for span in field["evidence"] for identifier in span["span_ids"]}
            refs = [word for line in lines for word in line.words if word.span_id in ids]
            add(name, field["value"], refs)
        elif field["status"] == "ambiguous":
            problems[name] = field

    for index, line in enumerate(lines):
        text, lower = line.text, line.text.lower()
        if not text:
            continue
        kind = summary_kind(text)
        header_columns = table_columns(line)
        if header_columns:
            columns, previous_item = header_columns, None
            pending = []
            continue
        # Explicit document labels precede positional party heuristics.
        reference = re.search(r"\b(?:invoice|credit note)\s*(?:no\.?|number|#)\s*:?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)", text, re.I)
        if not reference:
            reference = re.match(r"INVOICE\s+([A-Z0-9._/-]*\d[A-Z0-9._/-]*)$", text)
        if reference:
            add("invoice_number", reference[1], line.slice(*reference.span(1)))
        if re.search(r"\bcredit note\b", lower):
            add("document_type", "credit_note", line.words)
        elif re.fullmatch(r"invoice(?:\s+[A-Z0-9._/-]*\d[A-Z0-9._/-]*)?", text, re.I):
            add("document_type", "invoice", line.words)
        due_matches = list(re.finditer(r"\b(?:due(?: date)?|payment due)\s*:\s*("+DATE+r")", text, re.I))
        issue_matches = list(re.finditer(r"\b(?:invoice date|issue date|date issued|issued|date)\s*:\s*("+DATE+r")", text, re.I))
        for name, matches in [("due_date", due_matches), ("issue_date", issue_matches)]:
            for match in matches:
                if name == "issue_date" and any(d.start() <= match.start() < d.end() for d in due_matches):
                    continue
                refs = line.slice(*match.span(1))
                try:
                    add(name, date_value(match[1]), refs)
                except ValueError as error:
                    problems[name] = missing(str(error), refs, ambiguous=True)
        for word in line.words:
            code = word.text.strip(".,:;()")
            if code in CURRENCIES:
                add("currency", code, [word])
        terms = re.search(r"\bpayment terms\s*:\s*(.+)$", text, re.I)
        if terms:
            add("payment_terms", terms[1], line.slice(*terms.span(1)))
            conditional = re.search(r"(\d+(?:[.,]\d+)?)/\d+\s+net\s+\d+", terms[1], re.I)
            if conditional:
                add("conditional_discount_rate", str(decimal(conditional[1], quantity=True)/100), line.slice(*terms.span(1)))
        po = re.search(r"\b(?:purchase order|p\.?o\.?)\s*(?:no\.?|number|#)?\s*:\s*([A-Za-z0-9][A-Za-z0-9._/-]*)", text, re.I)
        if po:
            add("po_number", po[1], line.slice(*po.span(1)))

        if "reverse charge" in lower:
            add("tax_mode", "reverse_charge", line.words)
        elif re.search(r"\b(incl\.?|including)\s*(vat|tax)|prices include", lower):
            add("tax_mode", "inclusive", line.words)
        elif re.search(r"\bnet prices\b|\bexcl(?:ude[ds]?|uding|\.)?\s*(vat|tax)|\bplus\b.*\b(vat|tax)\b|statutory vat.*appl", lower):
            add("tax_mode", "exclusive", line.words)
        if kind == "subtotal":
            marker = re.search(r"sub-?total", lower)
            accept("subtotal", amount_field(line, marker.end()))
        elif kind in {"total", "shipping", "document_discount"} and not terms:
            amount = amount_field(line, reduction=kind == "document_discount")
            accept(kind, amount)
            if amount["status"] == "missing":
                problems[kind] = missing("stated_amount_unresolved", line.words)
        elif kind == "tax":
            # An inclusive banner has a rate but no printed tax amount.
            if not re.search(r"\b(incl\.?|including)\s*(vat|tax)|prices include", lower):
                amount = amount_field(line)
                if amount["status"] == "observed":
                    tax_lines.append({"rate": first_rate(line), "amount": amount})
            rate = first_rate(line)
            if rate["status"] == "observed":
                accept("tax_rate", rate)

        if re.match(r"bill\s+to\s*:?$", lower):
            bill_to = True
            columns = None
            continue
        if bill_to:
            add("customer_name", text, line.words)
            bill_to = False
        supplier_label = re.match(r"(?:supplier|vendor|from)\s*:\s*(.+)$", text, re.I)
        if supplier_label:
            add("supplier_name", supplier_label[1], line.slice(*supplier_label.span(1)))
            supplier_done = True
        elif not supplier_done and reference and reference.start() > 0:
            refs = line.slice(0, reference.start())
            if refs:
                add("supplier_name", " ".join(w.text for w in refs), refs)
                supplier_done = True
        elif not supplier_done and index > 0 and re.match(r"INVOICE(?:\s+\S+)?$", lines[index-1].text, re.I) and not kind and not issue_matches and not re.fullmatch(r"credit note", lower):
            add("supplier_name", text, line.words)
            supplier_done = True

        if kind or reference or issue_matches or due_matches or re.match(r"(invoice|credit note)\b", lower):
            if columns:
                columns = None
            pending = []
            continue
        if columns:
            item, continuation = table_item(line, columns)
            if item:
                items.append(item)
                previous_item = item
            elif continuation and previous_item is not None and len(continuation) == len(line.words):
                old = previous_item["description"]
                old_refs = [w for prior in lines for w in prior.words if any(w.span_id in e["span_ids"] for e in old["evidence"])]
                previous_item["description"] = observed(old["value"]+" "+text, old_refs+continuation)
            continue
        if lower.startswith("for the services"):
            continue
        combined = Line(pending + line.words)
        prose = prose_item(combined)
        if prose:
            items.append(prose)
            pending = []
        elif (pending or re.match(r"for\s+.+?,\s+we invoice|.+?:\s*\d+(?:[.,]\d+)?\s*[×x]", text, re.I)) and len(combined.text) < 3000:
            pending = combined.words
        else:
            pending = []

    # A credit note can also contain an invoice heading. Its explicit type wins.
    if any(value == "credit_note" for value, _ in candidates["document_type"]):
        candidates["document_type"] = [(value, refs) for value, refs in candidates["document_type"] if value == "credit_note"]
    rates = {entry["rate"]["value"] for entry in tax_lines if entry["rate"]["status"] == "observed"}
    if len(rates) > 1:
        candidates["tax_rate"] = []
    if len(tax_lines) == 1:
        accept("tax_amount", tax_lines[0]["amount"])
    result = {name: choose(candidates[name]) for name in InvoiceExtraction.model_fields
              if name not in {"schema_version", "document_id", "line_items", "taxes", "warnings"}}
    result.update(problems)
    if len(rates) > 1:
        result["tax_rate"] = missing("multiple_tax_rates")
    if not candidates["currency"] and any("$" in line.text for line in lines):
        result["currency"] = missing("ambiguous_currency_symbol", ambiguous=True)
    if pending:
        warnings.append("unparsed_prose_item_requires_review")
    if len(items) > 500:
        raise ValueError("too_many_line_items")
    record = InvoiceExtraction(document_id=document_id, **result, line_items=items, taxes=tax_lines,
        warnings=sorted(set(warnings + source.get("warnings", []))))
    verify_evidence(record, source)
    return record
