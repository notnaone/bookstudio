from studio_app.calendar_titles import effective_event_title, is_generic_title


def test_effective_event_title_uses_description_when_busy():
    assert effective_event_title("Busy", "Toomas - My Book") == "Toomas - My Book"
    assert effective_event_title("Busy", "Ingrid") == "Ingrid"


def test_effective_event_title_keeps_real_summary():
    assert effective_event_title("Roosileht - Minu raamat", None) == "Roosileht - Minu raamat"


def test_is_generic_title():
    assert is_generic_title("Busy")
    assert not is_generic_title("Toomas - Foo")
