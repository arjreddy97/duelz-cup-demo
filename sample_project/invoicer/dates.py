"""Billing dates."""
import calendar
from datetime import date, timedelta


def add_months(day, months):
    """The same day-of-month `months` later, clamped to the end of shorter months.

    add_months(date(2024, 1, 31), 1) -> date(2024, 2, 29)
    """
    index = day.month + months
    year = day.year + index // 12
    month = index % 12
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def billing_schedule(start, count, every=1):
    """`count` billing dates from `start`, one every `every` months.

    Each date is computed from `start`, not from the previous date, so a plan that
    starts on the 31st bills on the last day of every shorter month.
    """
    return [add_months(start, i * every) for i in range(count)]


def due_date(issued, net_days=30):
    return issued + timedelta(days=net_days)


def period_label(day):
    """date(2024, 3, 5) -> "Mar 2024"."""
    return day.strftime("%b %Y")
