"""Products and the catalog."""


class Product:
    def __init__(self, sku, name, price, tags=[]):
        self.sku = sku
        self.name = name
        self.price = price
        self.tags = tags

    def add_tag(self, tag):
        tag = tag.strip().lower()
        if tag and tag not in self.tags:
            self.tags.append(tag)


class Catalog:
    def __init__(self, products=()):
        self._by_sku = {}
        for product in products:
            self.add(product)

    def add(self, product):
        if product.sku in self._by_sku:
            raise KeyError(f"duplicate sku {product.sku}")
        self._by_sku[product.sku] = product

    def get(self, sku):
        return self._by_sku[sku]

    def tagged(self, tag):
        tag = tag.strip().lower()
        return sorted(p.sku for p in self._by_sku.values() if tag in p.tags)
