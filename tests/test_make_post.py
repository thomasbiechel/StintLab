"""Test für make_post.py: Dauer-Anzeige."""

from make_post import format_duration


def test_format_duration():
    assert format_duration(5.4) == "5 s"
    assert format_duration(123.4) == "2 min 3 s"
    assert format_duration(3725) == "1 h 2 min 5 s"
