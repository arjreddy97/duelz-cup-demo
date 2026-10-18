from invoicer.slugs import slugify, unique_slugs


def test_plain_names():
    assert slugify("Blue Mug") == "blue-mug"
    assert slugify("  Mug, Large!! ") == "mug-large"


def test_unique_ascii_names():
    assert unique_slugs(["Mug", "mug", "MUG!"]) == ["mug", "mug-2", "mug-3"]


def test_dessert_menu():
    assert slugify("Crème Brûlée (Large)") == "creme-brulee-large"


def test_customer_cities():
    assert [slugify(c) for c in ("São Paulo", "Zürich", "Kraków")] == ["sao-paulo", "zurich", "krakow"]


def test_cafe_variants_collide():
    assert unique_slugs(["Café", "Cafe"]) == ["cafe", "cafe-2"]


def test_department_names():
    assert slugify("ﬁnance oﬃce") == "finance-office"
