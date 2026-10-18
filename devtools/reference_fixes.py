"""Reference fixes for the bundled sample project (dev-only, excluded from the image).

Each entry maps a source file to exact (old, new) replacements. Used by the app's
tests to prove the sample is solvable, and by the scripted fake model.
"""
from pathlib import Path

FIXES = {
    "invoicer/money.py": [
        ("from decimal import Decimal\n", "from decimal import ROUND_HALF_UP, Decimal\n"),
        ("return Decimal(value).quantize(CENT)", "return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)"),
    ],
    "invoicer/dates.py": [
        ("    index = day.month + months\n    year = day.year + index // 12\n    month = index % 12\n",
         "    index = day.month - 1 + months\n    year = day.year + index // 12\n    month = index % 12 + 1\n"),
    ],
    "invoicer/paging.py": [
        ("return total // per_page + 1", "return (total + per_page - 1) // per_page"),
    ],
    "invoicer/slugs.py": [
        ('unicodedata.normalize("NFC", text)', 'unicodedata.normalize("NFKD", text)'),
    ],
    "invoicer/ranking.py": [
        ("key=lambda kv: (kv[1], kv[0]), reverse=True)", "key=lambda kv: (-kv[1], kv[0]))"),
    ],
    "invoicer/catalog.py": [
        ("def __init__(self, sku, name, price, tags=[]):", "def __init__(self, sku, name, price, tags=None):"),
        ("self.tags = tags\n", "self.tags = list(tags or [])\n"),
    ],
}


def apply_all(project_dir):
    """Apply every reference fix to a copy of the sample project."""
    for rel, edits in FIXES.items():
        path = Path(project_dir) / rel
        text = path.read_text()
        for old, new in edits:
            assert text.count(old) == 1, (rel, old)
            text = text.replace(old, new)
        path.write_text(text)
