"""Conservative printed-value normalization; ambiguous dates/numbers stay unknown."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

NUMBER = re.compile(r"(?<![A-Za-z0-9])[-−]?\(?\d[\d.,'’]*(?:\))?(?:\s*%)?")
DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4})"


def decimal(text, *, quantity=False):
    value = text.strip().replace("−", "-").replace("’", "'")
    if value.endswith("."):
        value = value[:-1]  # prose punctuation, not a decimal digit
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()")
    if not re.fullmatch(r"-?\d[\d.,']*", value):
        raise ValueError("unrecognized_number")
    if "'" in value:
        if not re.fullmatch(r"-?\d{1,3}(?:'\d{3})+(?:\.\d+)?", value):
            raise ValueError("ambiguous_number")
        value = value.replace("'", "")
    if "," in value and "." in value:
        point = "," if value.rfind(",") > value.rfind(".") else "."
        grouping = "." if point == "," else ","
        if not re.fullmatch(r"-?\d{1,3}(?:"+re.escape(grouping)+r"\d{3})+"+re.escape(point)+r"\d+", value):
            raise ValueError("ambiguous_number")
        value = value.replace(grouping, "").replace(point, ".")
    elif "," in value or "." in value:
        separator = "," if "," in value else "."
        parts = value.split(separator)
        if len(parts) > 2:
            if not all(len(part) == 3 for part in parts[1:]):
                raise ValueError("ambiguous_number")
            value = "".join(parts)
        elif len(parts[-1]) == 3 and not quantity:
            raise ValueError("ambiguous_number")
        else:
            value = value.replace(separator, ".")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("unrecognized_number") from None
    if not result.is_finite():
        raise ValueError("unrecognized_number")
    return -result if negative else result


def date_value(text):
    for pattern in ["%Y-%m-%d", "%d %B %Y", "%d %b %Y"]:
        try:
            return datetime.strptime(text.strip(), pattern).date().isoformat()
        except ValueError:
            pass
    numeric = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text.strip())
    if numeric:
        first, second, year = map(int, numeric.groups())
        if first <= 12 and second <= 12 and first != second:
            raise ValueError("ambiguous_date")
        day, month = (first, second) if first > 12 or first == second else (second, first)
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            pass
    raise ValueError("unrecognized_date")
