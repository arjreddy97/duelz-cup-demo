from datetime import date

from invoicer.dates import add_months, billing_schedule, due_date, period_label


def test_due_date():
    assert due_date(date(2024, 2, 20)) == date(2024, 3, 21)
    assert due_date(date(2024, 2, 20), net_days=14) == date(2024, 3, 5)


def test_month_end_clamp():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)


def test_period_label():
    assert period_label(date(2024, 3, 5)) == "Mar 2024"


def test_monthly_schedule_for_new_customer():
    assert billing_schedule(date(2024, 9, 15), 6) == [
        date(2024, 9, 15), date(2024, 10, 15), date(2024, 11, 15),
        date(2024, 12, 15), date(2025, 1, 15), date(2025, 2, 15),
    ]


def test_quarterly_schedule_keeps_month_end():
    assert billing_schedule(date(2024, 3, 31), 4, every=3) == [
        date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31),
    ]


def test_annual_renewal():
    assert add_months(date(2023, 12, 15), 12) == date(2024, 12, 15)


def test_plan_signed_in_winter():
    assert billing_schedule(date(2024, 12, 1), 3) == [
        date(2024, 12, 1), date(2025, 1, 1), date(2025, 2, 1),
    ]
