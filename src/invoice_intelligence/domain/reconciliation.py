"""Small, deterministic tax-exclusive reconciliation baseline using Decimal."""
from decimal import Decimal


def reconcile(*, line_nets: list[Decimal], subtotal: Decimal,
              discount: Decimal, shipping: Decimal, tax: Decimal,
              total: Decimal, tolerance: Decimal = Decimal("0.01")) -> list[dict[str, str]]:
    values = [*line_nets, subtotal, discount, shipping, tax, total, tolerance]
    if any(not value.is_finite() for value in values) or tolerance < 0:
        raise ValueError("Amounts must be finite and tolerance nonnegative")
    if not line_nets:
        return [{"code": "missing_line_items", "field": "line_items"}]
    issues = []
    checks = [
        ("subtotal_mismatch", "subtotal", sum(line_nets, Decimal("0")), subtotal),
        ("total_mismatch", "total", subtotal - discount + shipping + tax, total),
    ]
    for code, field, expected, observed in checks:
        if abs(expected - observed) > tolerance:
            issues.append({"code": code, "field": field,
                           "expected": str(expected), "observed": str(observed)})
    return issues
