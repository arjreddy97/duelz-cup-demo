from decimal import Decimal

from invoicer.money import apply_rate, format_money, split_evenly, to_money


def test_parse_amounts():
    assert to_money("1,234.50") == Decimal("1234.50")
    assert to_money("$12") == Decimal("12.00")
    assert to_money(7) == Decimal("7.00")


def test_format_money():
    assert format_money("1234.5") == "$1,234.50"
    assert format_money("-3") == "-$3.00"


def test_split_bill_three_ways():
    assert split_evenly("10.00", 3) == [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")]


def test_sales_tax_on_small_lines():
    assert apply_rate("2.25", "0.10") == Decimal("0.23")
    assert apply_rate("4.05", "0.10") == Decimal("0.41")


def test_discount_amount():
    assert apply_rate("12.30", "0.15") == Decimal("1.85")


def test_refund_amount():
    assert to_money("-0.125") == Decimal("-0.13")


def test_split_uneven_amount():
    assert split_evenly("0.105", 2) == [Decimal("0.06"), Decimal("0.05")]
