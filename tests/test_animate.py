"""Tests für die animierte Slide (Balken bauen sich Zeile für Zeile auf)."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from stintlab.reels.animate import INTRO_S, HOLD_S, ROW_S, STAGGER_S, animate_slide, rows_of, timeline


def _chart():
    fig, ax = plt.subplots(figsize=(3.6, 4.5), dpi=60)
    for y, w in ((2, 300), (1, 236), (0, 199)):
        ax.barh(y, w, height=0.6)
        ax.text(w + 5, y, f"{w}")
    ax.text(0.99, 0.01, "footnote", transform=ax.transAxes)     # immer sichtbar
    ax.axvline(300)
    return fig, ax


def test_rows_group_bars_and_texts_by_y():
    fig, ax = _chart()
    rows = rows_of(ax)
    assert sorted(rows) == [0.0, 1.0, 2.0]
    assert all(len(r["bars"]) == 1 and len(r["texts"]) == 1 for r in rows.values())
    plt.close(fig)


def test_timeline_bottom_row_first_then_hold():
    total, starts = timeline(3)
    assert starts == pytest.approx([INTRO_S, INTRO_S + STAGGER_S, INTRO_S + 2 * STAGGER_S])
    assert total == pytest.approx(starts[-1] + ROW_S + HOLD_S)


def test_animation_ends_in_the_final_state(tmp_path):
    pytest.importorskip("imageio_ffmpeg")
    fig, ax = _chart()
    out = animate_slide(fig, ax, tmp_path / "r.mp4")
    assert out.exists() and out.stat().st_size > 0
    assert sorted(p.get_width() for p in ax.patches) == [199, 236, 300]
    assert all((t.get_alpha() or 1.0) == 1.0 for t in ax.texts)
    plt.close(fig)


def test_no_bars_is_a_clear_error(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    with pytest.raises(ValueError):
        animate_slide(fig, ax, tmp_path / "r.mp4")
    plt.close(fig)
