"""Invoices tie money and dates together."""
from dataclasses import dataclass, field
from datetime import date

from .dates import due_date
from .money import apply_rate, format_money, to_money


@dataclass
class Line:
    description: str
    unit_price: str
    qty: int = 1

    @property
    def amount(self):
        return to_money(to_money(self.unit_price) * self.qty)


@dataclass
class Invoice:
    customer: str
    issued: date
    tax_rate: str = "0.00"
    net_days: int = 30
    lines: list = field(default_factory=list)

    def add(self, description, unit_price, qty=1):
        if qty <= 0:
            raise ValueError("qty must be positive")
        self.lines.append(Line(description, unit_price, qty))
        return self

    @property
    def subtotal(self):
        return sum((line.amount for line in self.lines), to_money(0))

    @property
    def tax(self):
        return apply_rate(self.subtotal, self.tax_rate)

    @property
    def total(self):
        return self.subtotal + self.tax

    @property
    def due(self):
        return due_date(self.issued, self.net_days)

    def summary(self):
        return f"{self.customer}: {format_money(self.total)} due {self.due.isoformat()}"
