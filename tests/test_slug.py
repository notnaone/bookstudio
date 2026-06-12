from __future__ import annotations

from studio_app.slug import slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"


def test_slugify_strips_punctuation():
    assert slugify("Chris - SciFi: Project!") == "chris-scifi-project"


def test_slugify_collapses_whitespace():
    assert slugify("  many   spaces  ") == "many-spaces"


def test_slugify_unicode_transliteration():
    assert slugify("Café Olé") == "cafe-ole"


def test_slugify_empty_returns_book():
    assert slugify("") == "book"


def test_slugify_max_length_60():
    s = slugify("a" * 200)
    assert len(s) <= 60
    assert s == "a" * 60
