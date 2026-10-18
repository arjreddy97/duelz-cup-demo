"""URL slugs for products and customers."""
import re
import unicodedata


def slugify(text, sep="-"):
    """Lower-case ASCII slug: letters and digits, everything else collapsed to `sep`.

    Accented and compatibility characters are folded to plain letters rather than dropped.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", sep, text)
    return text.strip(sep).lower()


def unique_slugs(names):
    """Slugs for names, adding -2, -3 ... when two names give the same slug."""
    seen = {}
    out = []
    for name in names:
        base = slugify(name)
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}-{n}")
    return out
