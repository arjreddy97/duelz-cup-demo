import pytest

from invoicer.catalog import Catalog, Product


def test_lookup_by_sku():
    catalog = Catalog([Product("MUG-1", "Mug", 8), Product("PEN-1", "Pen", 2)])
    assert catalog.get("PEN-1").name == "Pen"


def test_duplicate_sku_rejected():
    catalog = Catalog([Product("MUG-1", "Mug", 8)])
    with pytest.raises(KeyError):
        catalog.add(Product("MUG-1", "Other mug", 9))


def test_tagging_a_product():
    product = Product("LAMP-1", "Lamp", 30)
    product.add_tag(" Sale ")
    assert product.tags == ["sale"]


def test_new_products_have_no_tags():
    first = Product("PEN-1", "Pen", 2)
    first.add_tag("office")
    second = Product("PEN-2", "Pen", 2)
    assert second.tags == []


def test_clearance_filter():
    catalog = Catalog([Product("A", "a", 1), Product("B", "b", 1), Product("C", "c", 1)])
    catalog.get("B").add_tag("clearance")
    assert catalog.tagged("clearance") == ["B"]


def test_caller_tag_list_untouched():
    tags = ["new"]
    product = Product("X", "x", 1, tags)
    product.add_tag("gift")
    assert tags == ["new"]
    assert product.tags == ["new", "gift"]
