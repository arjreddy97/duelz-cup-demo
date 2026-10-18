"""Split long reports into pages."""
from dataclasses import dataclass


@dataclass
class Page:
    number: int  # 1-based
    pages: int
    items: list

    @property
    def has_next(self):
        return self.number < self.pages

    @property
    def has_prev(self):
        return self.number > 1


def page_count(total, per_page):
    """How many pages `total` rows need. An empty report still has one (empty) page."""
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    if total == 0:
        return 1
    return total // per_page + 1


def paginate(rows, number, per_page=10):
    """Page `number` (1-based) of `rows`. Raises ValueError for a page that does not exist."""
    pages = page_count(len(rows), per_page)
    if not 1 <= number <= pages:
        raise ValueError(f"page {number} out of range 1..{pages}")
    start = (number - 1) * per_page
    return Page(number, pages, rows[start:start + per_page])


def footer(page):
    """'Page 2 of 5'."""
    return f"Page {page.number} of {page.pages}"
