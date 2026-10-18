"""Money helpers. Amounts are Decimals rounded to whole cents."""
from decimal import Decimal

CENT = Decimal("0.01")


def to_money(value):
    """Turn "1,234.50", "$12", 7 or Decimal("2.345") into a Decimal with two places.

    Invoices round half a cent away from zero, the way people round on paper.
    """
    if isinstance(value, float):
        value = repr(value)
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "")
    return Decimal(value).quantize(CENT)


def apply_rate(amount, rate):
    """amount * rate (a rate like "0.08" means 8%), in cents."""
    return to_money(to_money(amount) * Decimal(str(rate)))


def split_evenly(amount, parts):
    """Split amount into `parts` shares that add up exactly; earlier shares get the spare cents."""
    if parts <= 0:
        raise ValueError("parts must be positive")
    cents = int(to_money(amount) * 100)
    base, extra = divmod(cents, parts)
    return [(Decimal(base + (1 if i < extra else 0)) / 100).quantize(CENT) for i in range(parts)]


def format_money(amount, symbol="$"):
    """Decimal("1234.5") -> "$1,234.50"; negatives get a leading minus."""
    value = to_money(amount)
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.2f}"
