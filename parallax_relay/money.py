"""Exact local estimate serialization beside compatible JSON numeric fields."""
from decimal import Decimal, DecimalException, localcontext
import math
import re


def total(values) -> Decimal:
    # Covers addition across the full finite binary64 exponent range without
    # throwing away small settlements when subtracting them from large caps.
    with localcontext() as context:
        context.prec = 1024
        return sum(values, Decimal(0))


def difference(a: Decimal, b: Decimal) -> Decimal:
    return total((a, b.copy_negate()))


def product(a: Decimal, b: int) -> Decimal:
    with localcontext() as context:
        context.prec = 1024
        return a * b


def json_fields(fields: dict) -> dict:
    result = dict(fields)
    for key, value in fields.items():
        if isinstance(value, Decimal):
            if value.is_zero():value=Decimal(0)
            number = float(value)
            if not value.is_finite() or not math.isfinite(number) or value < 0:
                raise ValueError('Invalid monetary estimate')
            result[key], result[key + '_decimal'] = number, str(value)
    return result


def amount(record: dict, key: str) -> Decimal | None:
    value, exact = record.get(key), record.get(key + '_decimal')
    if value is None:
        if exact is not None:
            raise ValueError('Contradictory monetary estimate')
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid monetary estimate')
    if exact is None:
        return Decimal(str(value))  # Historical numeric-only evidence.
    if (not isinstance(exact, str) or len(exact) > 1024 or
            not re.fullmatch(r'\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?', exact)):
        raise ValueError('Invalid exact monetary estimate')
    try:
        parsed = Decimal(exact)
    except DecimalException:
        raise ValueError('Invalid exact monetary estimate') from None
    # Rates originate in finite binary64 settings (down to ~1e-324); dividing
    # by a million can reach ~1e-330. Reject adversarial, unbounded exponents.
    if (not parsed.is_finite() or parsed < 0 or
            parsed and not -400 <= parsed.adjusted() <= 309 or float(parsed) != value):
        raise ValueError('Contradictory monetary estimate')
    return parsed if parsed else Decimal(0)
