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

def test_font_is_resolved_to_one_installed_family():
    from stintlab.style import FONT_FAMILY, resolve_font
    assert resolve_font() in FONT_FAMILY


def test_header_page_and_meta_are_on_the_slide():
    fig, _ = new_slide("Russell on pole", "sub", meta="Baku · Qualifying · 2026", page="02 / 05")
    texts = [t.get_text() for t in fig.texts]
    assert "BAKU · QUALIFYING · 2026" in texts and "02 / 05" in texts
    assert "RUSSELL ON POLE" in texts                       # Titel in Großbuchstaben
    assert "STINT" in texts and "LAB" in texts              # Wortzeichen


def test_chart_texts_are_scaled_and_numbers_monospace():
    from stintlab.style import FONT_NUM, TEXT_SCALE, scale_chart_texts
    fig, ax = new_slide("T")
    num = ax.text(0, 0, "+0.837 s", fontsize=10)
    name = ax.text(0, 0, "Aston Martin", fontsize=10)
    scale_chart_texts(fig)
    assert num.get_fontsize() == pytest.approx(10 * TEXT_SCALE)
    assert FONT_NUM in num.get_fontfamily()
    assert FONT_NUM not in name.get_fontfamily()            # Namen bleiben schmal (sonst abgeschnitten)
