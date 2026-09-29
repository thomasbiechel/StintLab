"""StintLab Studio – Posts und Reels per Oberfläche statt post.toml von Hand.

Start (im StintLab-Ordner, mit aktivierter .venv):
    streamlit run studio.py

Was es kann:
- Seitenleiste: nächstes Wochenende mit Countdown und Session-Zeiten (deine Ortszeit)
- „Neuer Post“: Wochenende + Session wählen, Slides und Reels zusammenklicken
  (Fahrer aus der Session, Runden, Reifen …), Vorschau der post.toml, speichern
  und direkt erzeugen – Ausgabe von make_post live, danach Galerie
- „Vorhandene Posts“: jede post.toml öffnen, von Hand anpassen, neu erzeugen,
  Bilder und Videos ansehen
- „Analysen“: Übersicht, was es gibt und für welche Session

Unter der Haube schreibt das Studio nur eine normale post.toml und startet
make_post.py – alles bleibt auch ohne Studio nutzbar.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from stintlab import openf1
from stintlab.registry import ANALYSES, REELS
from stintlab.studio_core import (BAR_ANALYSES, COMPOUNDS, PARAMS, POSTS, REEL_PARAMS, REEL_SESSIONS, REPO,
                                  SESSION_LABELS, clean_values, countdown, current_or_last, default_folder,
                                  existing_posts, next_weekend, outputs, race_weekends, reel_entry,
                                  session_times, session_types, to_toml)

DESCRIPTIONS = {
    "results": "Offizielles Ergebnis als Tabelle",
    "podium": "Podium / Top 3",
    "gap_between": "Abstand zweier Fahrer Runde für Runde",
    "gap_on_lap": "Abstand an jedem Punkt der Runde (wo holt er auf?)",
    "sector_delta": "Sektorzeiten-Differenz zweier Fahrer",
    "pit_cycle": "Boxenstopp-Phase: Undercut / Overcut",
    "lap_times": "Rundenzeiten mehrerer Fahrer",
    "driver_pace": "Rennpace aller Fahrer (saubere Runden)",
    "team_pace": "Rennpace pro Team",
    "positions": "Positionsverlauf im Rennen",
    "long_runs": "Long Runs im Training",
    "ideal_lap": "Ideale Runde aus den besten Sektoren",
    "sectors": "Beste Sektorzeiten",
    "telemetry": "Tempo und Abstand über die Runde",
    "top_speed": "Topspeed an der Speed Trap",
    "speed_vs_sector": "Topspeed gegen Sektorzeit (Abtrieb vs. Gerade)",
    "tow_effect": "Windschatten: Speed Trap vs. Abstand zum Vordermann",
    "tow_split": "Windschatten vs. Overtake Mode vs. Restart",
    "championship": "WM-Stand nach dem Rennen (Fahrer oder Teams)",
    "title_fight": "Wer kann noch Weltmeister werden?",
    "teammate_duel": "Saison: Quali-Duelle gegen den Teamkollegen",
    "best_starters": "Saison: beste Starter (fair zum Startplatz)",
    "saturday_sunday": "Saison: Samstags- oder Sonntagsfahrer",
    "preview_track": "Preview: Strecke",
    "preview_weather": "Preview: Wetter",
    "preview_form": "Preview: Form der Teams",
    "preview_chances": "Preview: Siegchancen",
}
REEL_DESCRIPTIONS = {
    "ghost_lap": "Zwei Runden als Geister auf der Strecke (Pole vs. P2 oder vs. Vorjahr)",
    "gap_chase": "Verfolgungsjagd: Abstand zweier Fahrer im Rennen",
    "race_story": "Zweikampf über mehrere Runden mit 3D-Anfang",
    "comeback": "Aufholjagd eines Fahrers (P19 → P1)",
}

st.set_page_config(page_title="StintLab Studio", page_icon="🏁", layout="wide")


# ── Daten (gecacht, damit die Oberfläche nicht bei jedem Klick OpenF1 fragt) ──

@st.cache_data(ttl=3600, show_spinner=False)
def meetings(year: int) -> list[dict]:
    try:
        return openf1.meetings_of(year)
    except Exception as exc:
        st.warning(f"Kalender {year} nicht ladbar: {exc}")
        return []


@st.cache_data(ttl=600, show_spinner=False)
def sessions(meeting_key: int) -> list[dict]:
    try:
        return openf1.sessions_of(meeting_key)
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def drivers_of(meeting_key: int, stype: str) -> list[str]:
    """Kürzel der Fahrer dieser Session (für die Auswahlfelder)."""
    try:
        key = openf1.find_session_key(meeting_key, stype)
        ds = openf1.cached_fetch("drivers", key)
        return sorted({d.get("name_acronym") for d in ds if d.get("name_acronym")})
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def stories_for(meeting_key: int, stype: str, top: int = 10) -> list[dict]:
    """Story-Finder (stintlab/stories.py) für ein Rennen/einen Sprint – wie find_stories.py."""
    from stintlab.session import load_session
    from stintlab.stories import find_stories
    data = load_session(meeting_key, stype)
    return [{"kind": x.kind, "score": x.score, "question": x.question, "facts": list(x.facts),
             "slides": [dict(sl) for sl in x.slides]} for x in find_stories(data)[:top]]


def with_id(entry: dict) -> dict:
    """Jeder Eintrag bekommt eine feste ID – damit die Titel-Felder beim Umsortieren am Eintrag bleiben."""
    return {**entry, "_id": uuid.uuid4().hex[:8]}


def label(m: dict) -> str:
    return f"{str(m.get('date_start', ''))[:10]} · {m.get('location') or m.get('meeting_name')}"


# ── Seitenleiste: nächstes Wochenende ────────────────────────────────────────

now = datetime.now(timezone.utc)
year = st.sidebar.number_input("Saison", 2023, now.year + 1, now.year)
cal = race_weekends(meetings(int(year)))
st.sidebar.title("🏁 StintLab Studio")
nxt = next_weekend(cal, now)
if nxt:
    st.sidebar.subheader(f"Nächstes: {nxt.get('location')}")
    st.sidebar.caption(nxt.get("meeting_official_name") or nxt.get("meeting_name", ""))
    for name, t in session_times(sessions(nxt["meeting_key"])):
        mark = "✅" if t <= now else "⏳"
        st.sidebar.write(f"{mark} **{name}** · {t:%a %d.%m. %H:%M} · {countdown(t, now) if t > now else ''}")
else:
    st.sidebar.info("Kein kommendes Wochenende in dieser Saison.")
st.sidebar.divider()
st.sidebar.caption("Studio schreibt nur post.toml und startet make_post.py – alles bleibt auch per Befehl nutzbar.")


# ── Hilfen: Formularfelder aus der Einstellungs-Liste ───────────────────────

def widgets(params, key: str, drivers: list[str]) -> dict:
    """Zeichnet die Felder einer Analyse/eines Reels und gibt die Werte zurück."""
    vals = {}
    for p in params:
        k = f"{key}_{p.name}"
        lab = p.label + (" *" if p.required else "")
        if p.kind == "drivers":
            if drivers:
                vals[p.name] = st.multiselect(lab, drivers, key=k, help=p.help or None,
                                              max_selections=p.n or None)
            else:
                txt = st.text_input(lab + " (Kürzel, Komma getrennt)", key=k, help="Fahrerliste nicht ladbar")
                vals[p.name] = [x.strip().upper() for x in txt.split(",") if x.strip()]
        elif p.kind == "laps":
            on = p.required or st.checkbox(lab, key=k + "_on")
            if on:
                c1, c2 = st.columns(2)
                a = c1.number_input(("" if p.required else "  ") + (p.label if p.required else "von Runde"),
                                    1, 100, 1, key=k + "_a")
                b = c2.number_input("bis Runde", 1, 100, 10, key=k + "_b")
                vals[p.name] = [a, b]
        elif p.kind == "bool":
            vals[p.name] = st.checkbox(lab, bool(p.default), key=k, help=p.help or None)
        elif p.kind == "int":
            txt = st.text_input(lab, "" if p.default is None else str(p.default), key=k, help=p.help or None)
            vals[p.name] = int(txt) if txt.strip().lstrip("-").isdigit() else None
        elif p.kind == "float":
            txt = st.text_input(lab, "" if p.default is None else str(p.default), key=k, help=p.help or None)
            try:
                vals[p.name] = float(txt.replace(",", ".")) if txt.strip() else None
            except ValueError:
                st.error(f"„{p.label}“ ist keine Zahl")
                vals[p.name] = None
        elif p.kind == "select":
            opts = ([None] if p.default is None else []) + list(p.options)
            idx = opts.index(p.default) if p.default in opts else 0
            vals[p.name] = st.selectbox(lab, opts, idx, key=k, help=p.help or None,
                                        format_func=lambda o: "— automatisch —" if o is None else str(o))
        else:
            vals[p.name] = st.text_input(lab, key=k, help=p.help or None)
    return vals


def run_make_post(path: Path, refresh: bool) -> None:
    """make_post.py starten und die Ausgabe live zeigen."""
    cmd = [sys.executable, "make_post.py", str(path.relative_to(REPO)), "--keep-going"] + (["--refresh"] if refresh else [])
    box = st.empty()
    lines: list[str] = []
    with st.spinner("Erzeuge … (Reels dauern ein paar Minuten)"):
        # UTF-8 erzwingen: Unter Windows schreibt Python in eine Pipe sonst in cp1252 –
        # dann scheitert schon das ✓ in make_post (UnicodeEncodeError)
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=env)
        for line in proc.stdout:
            if "UserWarning" in line or "writer.grab_frame" in line or line.startswith("findfont"):
                continue                      # Rauschen von matplotlib
            lines.append(line.rstrip())
            box.code("\n".join(lines[-40:]))
        proc.wait()
    (st.success if proc.returncode == 0 else st.error)(
        "Fertig." if proc.returncode == 0 else f"make_post ist mit Fehler {proc.returncode} beendet – siehe Ausgabe.")


def gallery(path: Path) -> None:
    out = outputs(path)
    if out["videos"]:
        cols = st.columns(min(3, len(out["videos"])))
        for i, v in enumerate(out["videos"]):
            with cols[i % len(cols)]:
                st.caption(v.name)
                st.video(str(v))
    if out["images"]:
        cols = st.columns(3)
        for i, img in enumerate(out["images"]):
            with cols[i % 3]:
                st.image(str(img), caption=img.name)
    if not (out["images"] or out["videos"]):
        st.info("Noch nichts erzeugt.")


if not cal:
    st.error("Kein Kalender geladen (OpenF1 nicht erreichbar und nichts im Cache).")
    st.stop()
default = current_or_last(cal, now) or cal[0]
c1, c2 = st.columns([2, 1])
meeting = c1.selectbox("Wochenende", cal, cal.index(default), format_func=label)
types = session_types(sessions(meeting["meeting_key"])) or ["R"]
types = types + ["PREVIEW"]
stype = c2.selectbox("Session", types, len(types) - 2 if "R" in types else 0,
                     format_func=lambda t: SESSION_LABELS.get(t, t))
drivers = drivers_of(meeting["meeting_key"], stype) if stype != "PREVIEW" else []
st.session_state.setdefault("slides", [])
st.session_state.setdefault("reels", [])
# Ordner folgt Wochenende/Session – außer eine Story hat ihn gesetzt
if st.session_state.get("folder_for") != (meeting["meeting_key"], stype):
    st.session_state["folder_for"] = (meeting["meeting_key"], stype)
    st.session_state["folder_input"] = default_folder(meeting, stype)
# eine übernommene Story setzt den Ordner – das geht nur VOR dem Zeichnen des Feldes (daher über rerun)
if "folder_pending" in st.session_state:
    st.session_state["folder_input"] = st.session_state.pop("folder_pending")

tab_new, tab_story, tab_old, tab_ref = st.tabs(["➕ Neuer Post", "🔎 Stories finden", "📁 Vorhandene Posts",
                                                 "📚 Analysen"])

# ── Neuer Post ───────────────────────────────────────────────────────────────

with tab_new:

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Slides")
        avail = [a for a, spec in ANALYSES.items() if stype in spec["sessions"]]
        a = st.selectbox("Analyse", avail, format_func=lambda x: f"{x} – {DESCRIPTIONS.get(x, '')}")
        vals = widgets(PARAMS.get(a, []), f"s_{a}", drivers)
        title = st.text_input("Titel *", key=f"title_{a}", help="GROSSBUCHSTABEN werden automatisch gesetzt")
        subtitle = st.text_input("Untertitel", key=f"sub_{a}", help="max. 2 Zeilen à ~88 Zeichen")
        as_reel = st.checkbox("Zusätzlich als animiertes Reel", key=f"reel_{a}",
                              help="Balken bauen sich Zeile für Zeile auf") if a in BAR_ANALYSES else False
        if st.button("➕ Slide hinzufügen", type="primary"):
            try:
                if not title.strip():
                    raise ValueError("Titel fehlt")
                entry = {"analysis": a, **clean_values(vals, PARAMS.get(a, [])), "title": title.strip().upper()}
                if subtitle.strip():
                    entry["subtitle"] = subtitle.strip()
                if as_reel:
                    entry["reel"] = True
                st.session_state.slides.append(with_id(entry))
            except ValueError as exc:
                st.error(str(exc))

        st.subheader("Reels")
        ravail = [r for r in REELS if stype in REEL_SESSIONS.get(r, set())]
        if ravail:
            r = st.selectbox("Reel", ravail, format_func=lambda x: f"{x} – {REEL_DESCRIPTIONS.get(x, '')}")
            rvals = widgets(REEL_PARAMS.get(r, []), f"r_{r}", drivers)
            with st.expander("Titelbild (Cover)"):
                cover = {"title": st.text_input("Cover-Titel", key=f"ct_{r}"),
                         "kicker": st.text_input("Kicker (klein darüber)", key=f"ck_{r}"),
                         "sub": st.text_input("Unterzeile", key=f"cs_{r}")}
            if st.button("➕ Reel hinzufügen"):
                try:
                    entry = reel_entry(r, rvals)
                    if any(v.strip() for v in cover.values()):
                        entry["cover"] = {k: v.strip() for k, v in cover.items() if v.strip()}
                    st.session_state.reels.append(with_id(entry))
                except ValueError as exc:
                    st.error(str(exc))
        else:
            st.caption("Für diese Session gibt es kein Reel-Format.")

    with right:
        st.subheader("Dieser Post")
        for kind in ("slides", "reels"):
            for i, e in enumerate(list(st.session_state[kind])):
                e.setdefault("_id", uuid.uuid4().hex[:8])
                c_a, c_b, c_c, c_d = st.columns([6, 1, 1, 1])
                if kind == "slides":
                    c_a.markdown(f"**{i + 1}. {e['analysis']}**")
                    t = c_a.text_input("Titel", e.get("title", ""), key=f"t_{e['_id']}", label_visibility="collapsed",
                                       placeholder="TITEL *")
                    sub = c_a.text_input("Untertitel", e.get("subtitle", ""), key=f"u_{e['_id']}",
                                         label_visibility="collapsed", placeholder="Untertitel (optional)")
                    e["title"] = t.strip().upper()
                    if sub.strip():
                        e["subtitle"] = sub.strip()
                    else:
                        e.pop("subtitle", None)
                else:
                    c_a.write(f"**Reel: {e['analysis']}** · {e.get('hook', '')}")
                if c_b.button("↑", key=f"up_{kind}_{i}", disabled=i == 0):
                    lst = st.session_state[kind]
                    lst[i - 1], lst[i] = lst[i], lst[i - 1]
                    st.rerun()
                if c_c.button("↓", key=f"dn_{kind}_{i}", disabled=i == len(st.session_state[kind]) - 1):
                    lst = st.session_state[kind]
                    lst[i + 1], lst[i] = lst[i], lst[i + 1]
                    st.rerun()
                if c_d.button("✕", key=f"rm_{kind}_{i}"):
                    st.session_state[kind].pop(i)
                    st.rerun()
        if not (st.session_state.slides or st.session_state.reels):
            st.caption("Noch leer – links Slides oder Reels hinzufügen.")

        folder = st.text_input("Ordner", key="folder_input")
        strip = lambda es: [{k: v for k, v in e.items() if k != "_id"} for e in es]
        config = {"session": {"meeting_key": int(meeting["meeting_key"]), "type": stype},
                  "slides": strip(st.session_state.slides), "reels": strip(st.session_state.reels)}
        missing = [i + 1 for i, e in enumerate(st.session_state.slides) if not e.get("title")]
        if missing:
            st.warning(f"Titel fehlt bei Slide {', '.join(map(str, missing))} – ohne Titel kein Speichern.")
        comment = f"{meeting.get('location')} {str(meeting.get('date_start', ''))[:4]} · {SESSION_LABELS.get(stype, stype)} – erstellt im StintLab Studio"
        toml_text = to_toml(config, comment)
        with st.expander("post.toml ansehen"):
            st.code(toml_text, language="toml")
        path = REPO / folder / "post.toml"
        refresh = st.checkbox("Daten neu von OpenF1 laden (--refresh)", help="z. B. kurz nach der Session, wenn Strafen fehlten")
        if path.exists():
            st.warning(f"{folder}/post.toml existiert schon – Speichern überschreibt sie.")
        c_s, c_r, c_x = st.columns(3)
        empty = not (st.session_state.slides or st.session_state.reels) or bool(missing)
        if c_s.button("💾 Speichern", disabled=empty):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(toml_text, encoding="utf-8")
            st.success(f"Gespeichert: {folder}/post.toml")
        if c_r.button("▶ Speichern & erzeugen", type="primary", disabled=empty):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(toml_text, encoding="utf-8")
            run_make_post(path, refresh)
            gallery(path)
        if c_x.button("🗑 Alles leeren", disabled=empty):
            st.session_state.slides, st.session_state.reels = [], []
            st.rerun()

# ── Stories finden ───────────────────────────────────────────────────────────

with tab_story:
    st.caption("Sucht in den Daten nach Fragen für die tiefe Analyse (Zweikämpfe ohne Überholen, Zwischenfälle, "
               "Aufholjagden, Safety Car, knappe Zieleinläufe …). Leitfaden: Stellen sich Fans diese Frage? "
               "Sieht man die Antwort im TV? Wenn nicht → nächste Story.")
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
    if stype not in ("R", "S"):
        st.info("Stories gibt es für Rennen und Sprint – oben „Race“ oder „Sprint“ wählen.")
    else:
        top = st.slider("Anzahl Kandidaten", 3, 15, 8)
        if st.button("🔎 Stories suchen", type="primary"):
            with st.spinner("Lade das Rennen und suche … (beim ersten Mal etwas länger)"):
                try:
                    st.session_state["stories"] = (meeting["meeting_key"], stype, stories_for(meeting["meeting_key"], stype, top))
                except Exception as exc:
                    st.error(f"Stories nicht gefunden: {exc}")
        found = st.session_state.get("stories")
        if found and found[:2] == (meeting["meeting_key"], stype):
            if not found[2]:
                st.info("Keine Kandidaten gefunden.")
            for n, sto in enumerate(found[2], start=1):
                with st.container(border=True):
                    st.markdown(f"**{n}. {sto['question']}**")
                    st.caption(f"{sto['kind']} · Score {sto['score']:.1f} · Slides: "
                               + " → ".join(sl["analysis"] for sl in sto["slides"]))
                    for f in sto["facts"]:
                        st.write(f"· {f}")
                    if st.button("→ Als Post übernehmen", key=f"take_{n}", disabled=not sto["slides"]):
                        st.session_state.slides = [with_id({**sl, "title": sto["question"].upper() if k == 0 else ""})
                                                   for k, sl in enumerate(sto["slides"])]
                        st.session_state.reels = []
                        st.session_state["folder_pending"] = default_folder(meeting, stype, "-story")
                        st.session_state["flash"] = ("Übernommen – im Reiter „➕ Neuer Post“ die Titel der übrigen "
                                                     "Slides ergänzen und erzeugen. Slide 1 hat die Frage als Titel (kürzen!).")
                        st.rerun()

# ── Vorhandene Posts ─────────────────────────────────────────────────────────

with tab_old:
    posts = existing_posts(POSTS)
    if not posts:
        st.info("Noch keine post.toml im Ordner posts/.")
    else:
        sel = st.selectbox("post.toml", posts, format_func=lambda p: str(p.parent.relative_to(POSTS)))
        text = st.text_area("Inhalt (direkt bearbeitbar)", sel.read_text(encoding="utf-8"), height=320,
                            key=f"edit_{sel}")
        c1, c2, c3 = st.columns(3)
        if c1.button("💾 Änderungen speichern", key="save_old"):
            try:
                import tomllib
                tomllib.loads(text)
                sel.write_text(text, encoding="utf-8")
                st.success("Gespeichert.")
            except Exception as exc:
                st.error(f"Kein gültiges TOML: {exc}")
        refresh_old = c3.checkbox("--refresh", key="refresh_old")
        if c2.button("▶ Neu erzeugen", type="primary", key="run_old"):
            sel.write_text(text, encoding="utf-8")
            run_make_post(sel, refresh_old)
        st.divider()
        gallery(sel)

# ── Übersicht ────────────────────────────────────────────────────────────────

with tab_ref:
    st.subheader("Slides")
    rows = [{"Analyse": a, "Was": DESCRIPTIONS.get(a, ""), "Sessions": ", ".join(sorted(spec["sessions"])),
             "Als Reel": "✓" if a in BAR_ANALYSES else ""} for a, spec in ANALYSES.items()]
    st.dataframe(rows, hide_index=True)
    st.subheader("Reels")
    st.dataframe([{"Reel": r, "Was": REEL_DESCRIPTIONS.get(r, ""), "Sessions": ", ".join(sorted(REEL_SESSIONS.get(r, [])))}
                  for r in REELS], hide_index=True)
    st.caption(f"Reifen: {', '.join(COMPOUNDS)} · Neue Analyse: Eintrag in stintlab/registry.py, "
               "Einstellungen in stintlab/studio_core.py (PARAMS)")
