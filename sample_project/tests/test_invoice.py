from datetime import date
from decimal import Decimal

import pytest

from invoicer.invoice import Invoice


def make():
    inv = Invoice("Acme", date(2024, 5, 10), tax_rate="0.08")
    inv.add("Mug", "12.50", qty=4).add("Pen", "2.00", qty=25)
    return inv


def test_subtotal():
    assert make().subtotal == Decimal("100.00")


def test_tax_and_total():
    inv = make()
    assert inv.tax == Decimal("8.00")
    assert inv.total == Decimal("108.00")


def test_due_date():
    assert make().due == date(2024, 6, 9)


def test_summary():
    assert make().summary() == "Acme: $108.00 due 2024-06-09"


def test_rejects_zero_quantity():
    with pytest.raises(ValueError):
        make().add("Lamp", "30.00", qty=0)
