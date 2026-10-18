"""Leaderboards for the monthly report."""
from collections import defaultdict
from decimal import Decimal

from .money import format_money, to_money


def totals_by_customer(entries):
    """(customer, amount) pairs -> {customer: Decimal total}."""
    totals = defaultdict(Decimal)
    for customer, amount in entries:
        totals[customer] += to_money(amount)
    return dict(totals)


def _ranked(totals):
    # Highest total first; customers with equal totals in alphabetical order.
    return sorted(totals.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)


def top_customers(entries, n=3):
    return [name for name, _ in _ranked(totals_by_customer(entries))[:n]]


def leaderboard(entries, n=3):
    """Lines like '1. Acme  $500.00'."""
    rows = _ranked(totals_by_customer(entries))[:n]
    return [f"{i}. {name}  {format_money(total)}" for i, (name, total) in enumerate(rows, 1)]
