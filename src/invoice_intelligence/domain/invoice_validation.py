"""Validate source observations or explicit reviewer overrides; never repair values."""
from decimal import Decimal, ROUND_HALF_UP

from invoice_intelligence.schemas.extraction import InvoiceExtraction

VERSION = "invoice-validation-v3"


def validate_extraction(invoice: InvoiceExtraction):
    issues, checks, derived, assumptions = [], [], [], []
    currency = invoice.currency.value
    quantum = Decimal("1") if currency == "JPY" else Decimal("0.01")

    def value(field):
        return field.value if field.status in {"observed", "corrected"} else None

    def issue(code, field, message, severity="warning", **extra):
        issues.append({"code": code, "field": field, "message": message, "severity": severity, **extra})

    def compare(code, field, expected, actual):
        expected = expected.quantize(quantum, rounding=ROUND_HALF_UP)
        difference = actual - expected
        passed = abs(difference) <= quantum
        checks.append({"code": code, "field": field, "status": "passed" if passed else "failed",
            "expected": str(expected), "observed": str(actual), "difference": str(difference)})
        if not passed:
            issue(code, field, "Recorded amount differs from the calculated amount.", "error",
                  expected=str(expected), observed=str(actual), difference=str(difference))

    def assumption(field, reason):
        assumptions.append({"field": field, "value": "0", "reason": reason})
        return Decimal("0")

    is_receipt=value(invoice.document_type)=="receipt"
    required=["supplier_name", "issue_date", "currency", "tax_mode", "total"]
    if not is_receipt:required += ["invoice_number","subtotal"]
    elif value(invoice.invoice_number) is None:
        issue("receipt_reference_absent","invoice_number","No printed receipt identifier; manually check duplicate identity.")
    for name in required:
        field = getattr(invoice, name)
        if value(field) is None:
            issue("required_field_unresolved", name, f"Resolve {name}: {field.reason}.")
    for name in ["due_date", "po_number", "document_discount", "shipping", "tax_amount", "tax_rate"]:
        field = getattr(invoice, name)
        if field.status == "ambiguous":
            issue("ambiguous_field", name, f"Conflicting or ambiguous source: {field.reason}.")
    # Every vision-only proposal needs an explicit per-field reviewer verification.
    def pending(obj,path=''):
        if isinstance(obj,dict):
            if obj.get('status')=='proposed':issue('provider_value_unverified',path,'Vision proposal is not corroborated by OCR; verify this field against the page.','error')
            else:
                for name,value_ in obj.items():pending(value_,f'{path}.{name}' if path else name)
        elif isinstance(obj,list):
            for index,value_ in enumerate(obj):pending(value_,f'{path}[{index}]')
    pending(invoice.model_dump(mode='json'))
    for warning in invoice.warnings:
        issue("source_or_extraction_warning", "document", warning)
    if value(invoice.issue_date) and value(invoice.due_date) and invoice.due_date.value < invoice.issue_date.value:
        issue("due_date_before_issue_date", "due_date", "The printed due date precedes the issue date.")
    if value(invoice.document_type) == "credit_note":
        issue("credit_note_requires_review", "document_type", "Confirm credit-note treatment and signs.")
    if not invoice.line_items:
        issue("missing_line_items", "line_items", "No supported line-item structure was extracted.")

    row_amounts = []
    for index, row in enumerate(invoice.line_items):
        prefix = f"line_items[{index}]"
        for name in (["description","amount"] if is_receipt else ["description", "quantity", "unit_price", "amount"]):
            field = getattr(row, name)
            if value(field) is None:
                issue("line_field_unresolved", f"{prefix}.{name}", f"Resolve line field: {field.reason}.")
        quantity, price, amount = value(row.quantity), value(row.unit_price), value(row.amount)
        if amount is not None:
            row_amounts.append(amount)
        if quantity is not None and price is not None and amount is not None:
            discount = value(row.discount_amount)
            if row.discount_amount.status == "ambiguous":
                issue("line_discount_ambiguous", prefix+".discount_amount", "Do not assume an ambiguous discount is zero.")
                continue
            if discount is None:
                discount = assumption(prefix+".discount_amount", "No applied line discount extracted; verify zero at confirmation.")
            compare("line_amount_mismatch", prefix+".amount", quantity * price - discount, amount)
        else:
            checks.append({"code": "line_arithmetic", "field": prefix, "status": "not_run", "reason": "Missing observed quantity, unit price or amount."})

    subtotal, total = value(invoice.subtotal), value(invoice.total)
    if invoice.line_items and len(row_amounts) == len(invoice.line_items):
        line_sum = sum(row_amounts, Decimal("0"))
        derived.append({"field": "sum_line_amounts", "value": str(line_sum), "formula": "sum(line_items[].amount)"})
        if subtotal is not None:
            compare("subtotal_mismatch", "subtotal", line_sum, subtotal)
        elif is_receipt:
            subtotal=line_sum
            assumptions.append({"field":"subtotal","value":str(line_sum),"reason":"Receipt subtotal is not printed; line sum used for arithmetic only. Verify every purchased-item row."})

    tax = value(invoice.tax_amount)
    components = [value(component.amount) for component in invoice.taxes]
    if components and all(amount is not None for amount in components):
        component_sum = sum(components, Decimal("0"))
        derived.append({"field": "sum_tax_components", "value": str(component_sum), "formula": "sum(taxes[].amount)"})
        if tax is not None:
            compare("tax_component_mismatch", "tax_amount", component_sum, tax)
        else:
            tax = component_sum
    mode = value(invoice.tax_mode)
    if mode == "reverse_charge":
        issue("reverse_charge_requires_review", "tax_mode", "Arithmetic can be checked, but legal reverse-charge applicability is not validated.")
        if tax is None:
            tax = assumption("tax_amount", "Explicit reverse-charge wording; assume no supplier-collected VAT for arithmetic only.")

    optional = {}
    ambiguous_optional = False
    for name in ["document_discount", "shipping", "tip", "service_fee"]:
        field = getattr(invoice, name)
        if field.status == "ambiguous" or field.reason == "stated_amount_unresolved":
            ambiguous_optional = True
            issue("optional_amount_unresolved", name, "An applied charge/discount is stated but its amount cannot be resolved; do not assume zero.")
        optional[name] = value(field)
        if optional[name] is None and field.status != "ambiguous" and field.reason != "stated_amount_unresolved":
            optional[name] = assumption(name, "No applied amount extracted; zero is an explicit arithmetic assumption, not a source observation.")
    if mode in {"exclusive", "inclusive", "reverse_charge"} and subtotal is not None and total is not None and not ambiguous_optional and (mode == "inclusive" or tax is not None):
        expected = subtotal - optional["document_discount"] + optional["shipping"] + optional["tip"] + optional["service_fee"]
        formula = "subtotal - applied_discount + shipping + tip + service_fee"
        if mode != "inclusive":
            expected += tax
            formula += " + tax"
        derived.append({"field": "calculated_total", "value": str(expected.quantize(quantum, rounding=ROUND_HALF_UP)), "formula": formula})
        compare("total_mismatch", "total", expected, total)
    else:
        issue("header_equation_incomplete", "total", "Required tax basis or amounts are unresolved; total reconciliation was not run.")
        checks.append({"code": "total_reconciliation", "field": "total", "status": "not_run", "reason": "Required observed values or tax basis missing/ambiguous."})

    for name in ["previous_balance", "amount_paid", "amount_due"]:
        if getattr(invoice,name).status == "ambiguous":
            issue("ambiguous_field",name,"Resolve the separate payment/balance amount before confirmation.")
    due=value(invoice.amount_due)
    if due is not None and total is not None:
        balance=value(invoice.previous_balance)
        paid=value(invoice.amount_paid)
        if balance is not None and paid is not None:
            compare("amount_due_mismatch","amount_due",total+balance-paid,due)
        else:
            checks.append({"code":"balance_reconciliation","field":"amount_due","status":"not_run",
                           "reason":"Previous balance or payment is not explicitly stated; no zero values inferred."})
    checks.append({"code": "tax_rate_compliance", "field": "taxes", "status": "not_run",
                   "reason": "Taxable bases, discount-tax policy and jurisdiction compliance are not inferred."})
    return {"rule_version": VERSION, "issues": issues, "checks": checks, "derived_values": derived,
        "assumptions": assumptions, "amount_tolerance": str(quantum),
        "routing": "needs_review" if issues else "ready_for_confirmation",
        "human_confirmation_required": True,
        "scope": "Arithmetic consistency of extracted observations; no accounting posting, tax-law verification or calibrated confidence."}
