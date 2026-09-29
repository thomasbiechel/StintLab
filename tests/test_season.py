"""Tests für Saison-Ebene, WM-Status und Teamkollegen-Duell (ohne Netz)."""

import pytest

from stintlab.analyses.championship import standings, title_contenders
from stintlab.analyses.teammate_duel import duel, duel_rows
from stintlab.season import max_points_left, split_at

WEEKENDS = [{"meeting_key": k, "location": loc, "date_start": d}
            for k, loc, d in ((1, "A", "2026-03-06T00:00:00+00:00"), (2, "B", "2026-04-10T00:00:00+00:00"),
                              (3, "C", "2026-05-01T00:00:00+00:00"), (4, "D", "2026-06-05T00:00:00+00:00"))]


def test_split_at_includes_this_weekend():
    done, left = split_at(2, meeting=WEEKENDS[1], weekends=WEEKENDS)
    assert [m["meeting_key"] for m in done] == [1, 2]
    assert [m["meeting_key"] for m in left] == [3, 4]


def test_max_points_left_counts_sprints_and_unknown():
    sessions = {3: [{"session_name": "Sprint"}, {"session_name": "Race"}], 4: None}

    def fake_sessions(key, refresh=False):
        if sessions[key] is None:
            raise RuntimeError("keine Sessions")
        return sessions[key]

    left = max_points_left(2, weekends_left=WEEKENDS[2:], sessions_of=fake_sessions)
    assert left == {"races": 2, "sprints": 1, "unknown": 1, "points": 2 * 25 + 8}


def _champ(rows):
    return lambda endpoint, key: rows


def test_standings_gained_and_moved():
    data = {"session_key": 1, "numbers": {"ANT": "12", "RUS": "63", "SAR": "2"},
            "teams": {"ANT": "Mercedes", "RUS": "Mercedes", "SAR": "Williams"}}
    raw = [{"driver_number": 63, "points_start": 211, "points_current": 236, "position_start": 3, "position_current": 2},
           {"driver_number": 12, "points_start": 292, "points_current": 302, "position_start": 1, "position_current": 1},
           {"driver_number": 44, "points_start": 220, "points_current": 220, "position_start": 2, "position_current": 3}]
    rows = standings(data, fetch=_champ(raw))
    assert [r["name"] for r in rows] == ["ANT", "RUS", "44"]          # unbekannte Nummer bleibt Nummer
    assert rows[1]["gained"] == 25 and rows[1]["moved"] == 1 and rows[2]["moved"] == -1


def test_standings_without_data_is_a_clear_error():
    with pytest.raises(ValueError):
        standings({"session_key": 1}, fetch=_champ([]))


def test_title_contenders_reach_the_leader():
    rows = [{"name": "A", "points": 300}, {"name": "B", "points": 250}, {"name": "C", "points": 240}]
    out = title_contenders(rows, 58)
    assert [r["alive"] for r in out] == [True, True, False]          # 250+58 ≥ 300, 240+58 < 300
    assert out[1]["max"] == 308


def _q(drv, pos, times, **kw):
    return {"driver": drv, "position": pos, "duration": times, **kw}


def test_duel_uses_last_shared_session():
    # beide in Q2, nur A in Q3 → Q2 zählt
    res = duel(_q("A", 8, [80.0, 79.5, 79.2]), _q("B", 12, [80.1, 80.295, None]))
    assert res[0] == "A" and res[1] == pytest.approx((80.295 / 79.5 - 1) * 100)


def test_duel_without_shared_time_or_dsq_is_none():
    assert duel(_q("A", 1, [80.0, None, None]), _q("B", 22, [None, None, None])) is None
    assert duel(_q("A", 1, [80.0, 79.0, 78.0]), _q("B", 2, [80.1, 79.1, 78.1], dsq=True)) is None


def test_duel_rows_counts_wins_and_orients_winner_first():
    sessions = []
    for i, b_ahead in enumerate((False, False, True, False)):
        a, b = _q("AAA", 5, [80.0, 79.0, 78.0]), _q("BBB", 6, [80.2, 79.2, 78.156])
        if b_ahead:
            a, b = _q("AAA", 6, [80.0, 79.0, 78.2]), _q("BBB", 5, [80.2, 79.2, 78.0])
        sessions.append({"meeting_key": i, "place": str(i), "teams": {"AAA": "Ferrari", "BBB": "Ferrari"},
                         "results": [a, b]})
    rows = duel_rows(sessions)
    assert len(rows) == 1
    r = rows[0]
    assert (r["a"], r["b"], r["wins_a"], r["wins_b"], r["n"]) == ("AAA", "BBB", 3, 1, 4)
    assert r["median_pct"] == pytest.approx((78.156 / 78.0 - 1) * 100)


def test_duel_rows_drops_pairs_with_too_few_sessions():
    s = {"meeting_key": 1, "teams": {"X": "Audi", "Y": "Audi"},
         "results": [_q("X", 10, [80.0]), _q("Y", 11, [80.5])]}
    assert duel_rows([s, s]) == []
