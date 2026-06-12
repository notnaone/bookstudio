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


def test_slugify_truncation_strips_trailing_hyphen():
    # Input that, when slugified, yields hyphens straddling the 60-char cutoff.
    result = slugify("a-" * 100)
    assert len(result) <= 60
    assert not result.endswith("-")
    assert not result.startswith("-")


def test_slugify_all_truncation_falls_back_to_book():
    # Pathological case: input where ALL chars within MAX_LEN are hyphens
    # after stripping (shouldn't happen with this slugifier, but the
    # `or "book"` guard must be in place).
    # Use a non-ASCII string that becomes empty after ASCII encode.
    assert slugify("中文" * 100) == "book"
