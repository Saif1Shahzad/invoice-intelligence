"""Map benchmark generator truth into *candidate* printed-value targets.

This is an offline label adapter, never an invoice extractor. It reads answer
keys, so importing it into an extraction pipeline would leak the answers.
"""
from decimal import Decimal, ROUND_HALF_UP


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def amount(value) -> str:
    return format(money(value), ".2f")


def target(value=None, kind="expected_printed", note="") -> dict:
    return {"value": value, "kind": kind,
            "score_extraction": kind == "expected_printed",
            "score_absence": kind == "not_printed", "note": note}


def map_benchmark_label(raw: dict) -> dict:
    v = raw["variants"]
    inclusive = v["vat_variant"] == "explicit_included"
    reverse = v["edge_case"] == "reverse_charge"
    fields = {}
    for dest, src in {
        "supplier_name": "vendor", "customer_name": "recipient",
        "invoice_number": "invoice_id", "issue_date": "date",
        "due_date": "due_date", "currency": "currency", "total": "rendered_total",
        "payment_terms": "payment_terms",
    }.items():
        fields[dest] = target(raw[src])
    fields["document_type"] = target("credit_note" if raw["is_credit_note"] else "invoice")
    fields["tax_mode"] = target("reverse_charge" if reverse else "inclusive" if inclusive else "exclusive")
    displayed_subtotal = money(raw["rendered_subtotal"])
    if inclusive:
        displayed_subtotal += money(raw["vat_amount"])
    fields["subtotal"] = target(amount(displayed_subtotal), note="Gross when tax-inclusive; includes injected error.")
    for name in ["shipping", "po_number"]:
        fields[name] = target(kind="not_printed", note="Not supplied/printed by this benchmark; do not invent a zero or PO reference.")
    fields["supplier_address"] = target(kind="unmapped", note="Address exists in raw labels; manual assembly/localization deferred.")
    has_discount_line = raw["discount"] is not None and v["discount_variant"] != "trade_terms"
    fields["document_discount"] = (
        target(amount(raw["discount_amount"]), note="Signed reduction magnitude; normalize the printed minus sign.")
        if has_discount_line else target(kind="not_printed", note="No applied-discount amount is printed; validation may separately assume zero.")
    )
    fields["conditional_discount_rate"] = (
        target(raw["discount"]["value"], note="2/10 net 30; not an applied discount.")
        if v["discount_variant"] == "trade_terms" else target(kind="not_printed")
    )
    fields["tax_amount"] = (
        target(kind="not_printed", note="No explicit VAT amount; retain canonical amount only as mathematical truth.")
        if inclusive or reverse else
        target(amount(raw["vat_amount"]), kind="derived" if v["edge_case"] == "mixed_vat" and v["layout"] != "mixed" else "expected_printed",
               note="Mixed VAT may require summing printed per-rate components.")
    )
    fields["tax_rate"] = (
        target(raw["vat_rate"], note="Fraction, e.g. 0.20 means 20%.")
        if raw["vat_rate"] is not None and not reverse and v["vat_variant"] != "implicit_no_rate"
        and not (inclusive and v["layout"] == "mixed")
        else target(kind="not_printed", note="No single explicit rate; do not infer it for extraction scoring.")
    )
    lines = []
    for line in raw["line_items"]:
        unit = money(line["unit_price"])
        if inclusive:
            unit = money(unit * (Decimal("1") + Decimal(line["vat_rate"])))
        implicit_single = v["layout"] == "paragraph" and line["quantity"] == 1
        lines.append({
            "description": target(line["description"],
                kind="needs_adjudication" if "↔" in line["description"] else "expected_printed",
                note="Known rendering discrepancy: ↔ appears as « in inspected PDFs. Adjudicate visible text before exact-match scoring." if "↔" in line["description"] else ""),
            "quantity": target(str(line["quantity"]), kind="derived" if implicit_single else "expected_printed",
                               note="Paragraph single-item wording omits quantity=1." if implicit_single else ""),
            "unit_price": target(amount(unit), kind="derived" if implicit_single else "expected_printed"),
            "amount": target(amount(unit * Decimal(str(line["quantity"])))),
            "tax_rate": target(kind="not_printed", note="Raw per-row VAT rate is not a printed row cell."),
            "discount_amount": target(kind="unlabeled"),
            "sku": target(kind="unlabeled"),
        })
    return {
        "document_id": raw["invoice_id"], "mapping_version": "1.0",
        "notice": "Offline candidate targets from answer keys and generator rules. No OCR/model has run; source boxes are not supplied. Verify against rendered PDF before scoring.",
        "fields": fields, "line_items": lines,
        "mathematical_truth": {key: raw[key] for key in ["subtotal", "vat_amount", "discount_amount", "total"]},
        "validation_truth": {
            "injected_error": v["consistency"], "error_note": raw["error_note"],
            "unsupported_for_day1_validator": inclusive or raw["is_credit_note"] or v["edge_case"] in ["reverse_charge", "mixed_vat"],
        },
    }
