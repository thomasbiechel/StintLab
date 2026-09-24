"""Tests für die Slide-Hülle."""

import pytest

from stintlab.style import new_slide


def test_long_subtitle_wraps_to_two_lines():
    fig, _ = new_slide("Title", "word " * 30)  # ~150 Zeichen → 2 Zeilen
    subtitle = [t for t in fig.texts if t.get_text().startswith("word")][0]
    assert subtitle.get_text().count("\n") == 1


def test_too_long_subtitle_is_rejected():
    with pytest.raises(ValueError, match="zu lang"):
        new_slide("Title", "word " * 60)  # ~300 Zeichen → mehr als 2 Zeilen