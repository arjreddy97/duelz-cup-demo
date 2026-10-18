import pytest

from invoicer.paging import footer, page_count, paginate

ROWS = list(range(100))


def test_empty_report():
    page = paginate([], 1)
    assert (page.pages, page.items, page.has_next, page.has_prev) == (1, [], False, False)


def test_middle_page():
    page = paginate(ROWS[:25], 2)
    assert page.items == list(range(10, 20))
    assert page.has_prev and page.has_next


def test_short_last_page():
    page = paginate(ROWS[:25], 3)
    assert page.items == [20, 21, 22, 23, 24]
    assert not page.has_next


def test_page_counts():
    assert [page_count(n, 10) for n in (1, 9, 10, 11, 30)] == [1, 1, 1, 2, 3]


def test_last_page_of_twenty_rows():
    page = paginate(ROWS[:20], 2)
    assert page.items == list(range(10, 20))
    assert not page.has_next


def test_page_past_the_end():
    with pytest.raises(ValueError):
        paginate(ROWS[:30], 4)


def test_report_footer():
    assert footer(paginate(ROWS[:40], 1, per_page=20)) == "Page 1 of 2"
