"""The bundled sample project: the intended tests fail, each reference fix clears
exactly its own group, and all fixes together make the whole suite pass."""
import asyncio

from app import sandbox
from devtools.reference_fixes import FIXES, apply_all

EXPECTED_FAILING = {
    "invoicer/catalog.py": ["test_new_products_have_no_tags", "test_clearance_filter",
                            "test_caller_tag_list_untouched"],
    "invoicer/dates.py": ["test_monthly_schedule_for_new_customer", "test_quarterly_schedule_keeps_month_end",
                          "test_annual_renewal", "test_plan_signed_in_winter"],
    "invoicer/money.py": ["test_sales_tax_on_small_lines", "test_discount_amount", "test_refund_amount",
                          "test_split_uneven_amount"],
    "invoicer/paging.py": ["test_page_counts", "test_last_page_of_twenty_rows", "test_page_past_the_end",
                           "test_report_footer"],
    "invoicer/ranking.py": ["test_equal_totals", "test_leaderboard_lines", "test_cut_falls_inside_a_tie"],
    "invoicer/slugs.py": ["test_dessert_menu", "test_customer_cities", "test_cafe_variants_collide",
                          "test_department_names"],
}


def _ids(owner):
    stem = owner.split("/")[-1][:-3]
    return {f"tests/test_{stem}.py::{name}" for name in EXPECTED_FAILING[owner]}


ALL_FAILING = set().union(*(_ids(o) for o in EXPECTED_FAILING))


def test_bugged_sample_fails_exactly_the_intended_tests(ws):
    r = asyncio.run(sandbox.run_pytest(ws))
    assert {f["nodeid"] for f in r["failures"]} == ALL_FAILING
    assert (r["failed"], r["passed"]) == (22, 21)


def test_failures_group_into_six_owning_files(ws):
    r = asyncio.run(sandbox.run_pytest(ws))
    groups = sandbox.group_failures(r["failures"], ws)
    assert set(groups) == set(EXPECTED_FAILING)
    for owner, g in groups.items():
        assert {f["nodeid"] for f in g["failures"]} == _ids(owner)
    assert groups["invoicer/dates.py"]["how"] == "traceback"


def test_each_fix_clears_only_its_own_group(ws):
    original = {rel: sandbox.read(ws, rel) for rel in FIXES}
    for owner, edits in FIXES.items():
        text = original[owner]
        for old, new in edits:
            text = text.replace(old, new)
        (ws / owner).write_text(text)
        r = asyncio.run(sandbox.run_pytest(ws))
        assert {f["nodeid"] for f in r["failures"]} == ALL_FAILING - _ids(owner), owner
        (ws / owner).write_text(original[owner])


def test_reference_fixes_make_everything_pass(ws):
    apply_all(ws)
    r = asyncio.run(sandbox.run_pytest(ws))
    assert (r["failed"], r["passed"]) == (0, 43)
