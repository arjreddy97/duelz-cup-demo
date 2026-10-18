from decimal import Decimal

from invoicer.ranking import leaderboard, top_customers, totals_by_customer


def test_totals():
    entries = [("Acme", "100.00"), ("Beta", "40.00"), ("Acme", "25.50")]
    assert totals_by_customer(entries) == {"Acme": Decimal("125.50"), "Beta": Decimal("40.00")}


def test_clear_winner():
    entries = [("Acme", "500.00"), ("Beta", "300.00"), ("Gamma", "100.00")]
    assert top_customers(entries) == ["Acme", "Beta", "Gamma"]


def test_equal_totals():
    entries = [("Zeta", "100.00"), ("Acme", "100.00"), ("Mid", "50.00")]
    assert top_customers(entries) == ["Acme", "Zeta", "Mid"]


def test_leaderboard_lines():
    entries = [("Orbit", "75.00"), ("Kite", "75.00"), ("Atlas", "90.00")]
    assert leaderboard(entries) == ["1. Atlas  $90.00", "2. Kite  $75.00", "3. Orbit  $75.00"]


def test_cut_falls_inside_a_tie():
    entries = [("Bravo", "200.00"), ("Alpha", "200.00"), ("Charlie", "200.00"), ("Delta", "300.00")]
    assert top_customers(entries, n=2) == ["Delta", "Alpha"]
