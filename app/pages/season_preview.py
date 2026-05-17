import html

import pandas as pd
import streamlit as st

from app.components import stat_card
from app.data_loader import get_medisports_roster_df, normalize_player_key
from app.image_helpers import image_data_uri_thumbnail, resolve_player_photo
from app.page_layout import section_header
from app.presentation_helpers import nationality_label


NOT_AVAILABLE = "Not available"


def _season_col(df: pd.DataFrame) -> str | None:
    for col in ("resolved_season", "season"):
        if col in df.columns:
            return col
    return None


def _season_options(df: pd.DataFrame) -> list[int]:
    col = _season_col(df)
    if df.empty or not col:
        return []
    values = pd.to_numeric(df[col], errors="coerce").dropna().astype(int).unique().tolist()
    return sorted(set(values))


def _filter_season(df: pd.DataFrame, season: int) -> pd.DataFrame:
    col = _season_col(df)
    if df.empty or not col:
        return df.iloc[0:0].copy()
    season_values = pd.to_numeric(df[col], errors="coerce")
    return df[season_values == int(season)].copy()


def _match_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    return int(df["match_id"].nunique()) if "match_id" in df.columns else int(len(df))


def _unique_count(df: pd.DataFrame, col: str) -> int:
    if df.empty or col not in df.columns:
        return 0
    values = df[col].dropna().astype(str).str.strip()
    values = values[values != ""]
    return int(values.nunique())


def _date_range(df: pd.DataFrame) -> str:
    if df.empty or "date" not in df.columns:
        return NOT_AVAILABLE
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return NOT_AVAILABLE
    return f"{dates.min().strftime('%Y-%m-%d')} → {dates.max().strftime('%Y-%m-%d')}"


def _fmt_float(value, decimals: int = 2) -> str:
    if pd.isna(value):
        return NOT_AVAILABLE
    return f"{float(value):.{decimals}f}"


def _safe(value) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none", "null", "<na>"}:
        return NOT_AVAILABLE
    return html.escape(text)


def _display_player_from_key(rows: pd.DataFrame, player_key: str) -> str:
    names = rows.loc[rows["player_key"] == player_key, "player"].dropna().astype(str).str.strip()
    return names.iloc[0] if not names.empty else player_key


def _players_meta_by_key(players: pd.DataFrame) -> pd.DataFrame:
    if players.empty:
        return pd.DataFrame()
    name_col = "player" if "player" in players.columns else "name" if "name" in players.columns else None
    if not name_col:
        return pd.DataFrame()
    meta = players.copy()
    meta["player_key"] = meta.get("player_clean", meta[name_col]).map(normalize_player_key)
    meta = meta[meta["player_key"] != ""]
    return meta.drop_duplicates("player_key", keep="first")


def _render_overview_cards(season_df: pd.DataFrame, season_tactics: pd.DataFrame, season: int) -> None:
    comp_col = "grouped_competition_name" if "grouped_competition_name" in season_df.columns else "competition"
    maps_played = _unique_count(season_df, "map")
    if maps_played == 0:
        maps_played = _unique_count(season_tactics, "map")

    values = [
        ("Season", str(season), "Resolved season number", "good"),
        ("Date Range", _date_range(season_df), "Official match rows only", "mid"),
        ("Matches Played", str(_match_count(season_df)), "Unique match IDs", "good"),
        ("Unique Opponents", str(_unique_count(season_df, "opponent_team")), "Distinct opponent teams", "mid"),
        ("Competitions Entered", str(_unique_count(season_df, comp_col)), "Grouped competition names", "mid"),
        ("Maps Played", str(maps_played), "Distinct normalized maps", "mid"),
        ("Active Players Seen", str(season_df["player_key"].nunique() if "player_key" in season_df.columns else 0), "Medisports player identities", "good"),
    ]
    cols = st.columns(4, gap="small")
    for idx, (title, value, note, tone) in enumerate(values):
        with cols[idx % 4]:
            stat_card(title, value, note, tone)


def _render_roster_preview(season_df: pd.DataFrame, players: pd.DataFrame) -> None:
    section_header("Roster Preview", "Players active in the selected season, joined to players.csv when available.")
    if season_df.empty:
        st.info("No Medisports player rows are available for this season.")
        return

    meta = _players_meta_by_key(players)
    rows = []
    metric_col = "kpd" if "kpd" in season_df.columns else "kd" if "kd" in season_df.columns else None
    for player_key, p_df in season_df.groupby("player_key", dropna=False):
        if not player_key:
            continue
        display = _display_player_from_key(season_df, player_key)
        meta_row = meta[meta["player_key"] == player_key].iloc[0] if not meta.empty and (meta["player_key"] == player_key).any() else None
        photo_path = resolve_player_photo(display).get("path") or resolve_player_photo(player_key).get("path")
        photo_uri = image_data_uri_thumbnail(photo_path, max_width=74, max_height=74)
        rows.append(
            {
                "photo": f"<img src='{photo_uri}' class='player-card-photo'/>" if photo_uri else "<span class='muted'>No photo</span>",
                "player": html.escape(display),
                "matches": _match_count(p_df),
                "avg_grevscore": _fmt_float(pd.to_numeric(p_df.get("grevscore"), errors="coerce").mean() if "grevscore" in p_df.columns else pd.NA),
                "kd_label": "KPD" if metric_col == "kpd" else "K/D" if metric_col else "K/D",
                "kd": _fmt_float(pd.to_numeric(p_df.get(metric_col), errors="coerce").mean() if metric_col else pd.NA),
                "role": _safe(meta_row.get("role") if meta_row is not None else ""),
                "country": _safe(nationality_label(meta_row.get("nationality") or meta_row.get("country")) if meta_row is not None else ""),
                "map": _safe(meta_row.get("map") if meta_row is not None else ""),
            }
        )

    rows = sorted(rows, key=lambda item: (item["matches"], item["avg_grevscore"]), reverse=True)
    cards = []
    for item in rows:
        cards.append(
            "<div class='panel panel-tight'>"
            f"<div style='display:flex;gap:.75rem;align-items:center;'>{item['photo']}"
            f"<div><div class='metric-title'>{item['player']}</div>"
            f"<div class='muted'>Role: {item['role']} • Country: {item['country']} • Favourite map: {item['map']}</div></div></div>"
            f"<div class='player-viewer-top-metrics' style='margin-top:.7rem;'>"
            f"<span class='chip'>Matches: {item['matches']}</span>"
            f"<span class='chip chip-good'>Avg GrevScore: {item['avg_grevscore']}</span>"
            f"<span class='chip chip-mid'>{item['kd_label']}: {item['kd']}</span>"
            "</div></div>"
        )
    st.markdown("<div class='card-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def _render_competition_preview(season_df: pd.DataFrame) -> None:
    section_header("Competition Preview", "Grouped competition rollup with raw competition names preserved.")
    if season_df.empty:
        st.info("No competition rows are available for this season.")
        return
    group_col = "grouped_competition_name" if "grouped_competition_name" in season_df.columns else "competition"
    raw_col = "raw_competition_name" if "raw_competition_name" in season_df.columns else "competition"
    rows = []
    for group_name, comp_df in season_df.groupby(group_col, dropna=False):
        map_counts = comp_df.get("map", pd.Series(dtype=str)).dropna().astype(str).str.strip().value_counts()
        rows.append(
            {
                "Grouped Competition": _safe(group_name),
                "Raw Competitions": ", ".join(sorted(comp_df.get(raw_col, pd.Series(dtype=str)).dropna().astype(str).str.strip().unique())) or NOT_AVAILABLE,
                "Matches Played": _match_count(comp_df),
                "Opponents Faced": _unique_count(comp_df, "opponent_team"),
                "Map Spread": ", ".join(f"{m} ({c})" for m, c in map_counts.items()) or NOT_AVAILABLE,
            }
        )
    st.dataframe(pd.DataFrame(rows).sort_values("Matches Played", ascending=False), use_container_width=True, hide_index=True)


def _render_map_preview(season_df: pd.DataFrame) -> None:
    section_header("Map Preview", "Per-map match volume, round totals when available, and strongest players by GrevScore.")
    if season_df.empty or "map" not in season_df.columns:
        st.info("No map rows are available for this season.")
        return
    rows = []
    for map_name, map_df in season_df.groupby("map", dropna=False):
        if not str(map_name or "").strip():
            continue
        rounds_value = NOT_AVAILABLE
        if {"match_id", "rounds_played"}.issubset(map_df.columns):
            per_match_rounds = pd.to_numeric(map_df["rounds_played"], errors="coerce").groupby(map_df["match_id"]).max().dropna()
            if not per_match_rounds.empty:
                rounds_value = str(int(per_match_rounds.sum()))
        player_scores = []
        if "grevscore" in map_df.columns:
            for player_key, score in pd.to_numeric(map_df["grevscore"], errors="coerce").groupby(map_df["player_key"]).mean().dropna().sort_values(ascending=False).head(3).items():
                player_scores.append(f"{_safe(_display_player_from_key(map_df, player_key))} ({score:.2f})")
        rows.append(
            {
                "Map": _safe(map_name),
                "Matches": _match_count(map_df),
                "Rounds": rounds_value,
                "Average GrevScore": _fmt_float(pd.to_numeric(map_df.get("grevscore"), errors="coerce").mean() if "grevscore" in map_df.columns else pd.NA),
                "Best Performing Players": ", ".join(player_scores) or NOT_AVAILABLE,
            }
        )
    st.dataframe(pd.DataFrame(rows).sort_values("Matches", ascending=False), use_container_width=True, hide_index=True)


def _render_timeline_preview(timeline: pd.DataFrame, season: int) -> None:
    section_header("Timeline Preview", "Structured season events from medisports_timeline.csv; scrim-labelled rows are excluded.")
    if timeline.empty or "season" not in timeline.columns:
        st.info("No timeline data is available for this season.")
        return
    filtered = timeline[pd.to_numeric(timeline["season"], errors="coerce") == int(season)].copy()
    if filtered.empty:
        st.info("No timeline events are linked to this season.")
        return
    text_cols = [col for col in ["event_type", "category", "title", "details", "notes"] if col in filtered.columns]
    if text_cols:
        scrim_mask = filtered[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.contains(r"\bscrim\b", case=False, regex=True, na=False)
        filtered = filtered[~scrim_mask]
    if filtered.empty:
        st.info("Timeline rows for this season are scrim-only, so they are hidden from this official preview.")
        return
    show_cols = [col for col in ["date", "public_visibility", "event_type", "category", "title", "competition", "placement", "opponent_or_org", "player_name"] if col in filtered.columns]
    display = filtered[show_cols].copy()
    if "date" in display.columns:
        display["date"] = pd.to_datetime(display["date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna(NOT_AVAILABLE)
    if "public_visibility" in display.columns:
        display["public_visibility"] = display["public_visibility"].fillna("internal").astype(str).str.strip().replace("", "internal").str.title()
    st.dataframe(display, use_container_width=True, hide_index=True)


def render(data: dict):
    full_matches = data.get("player_matches_full", data.get("player_matches", pd.DataFrame())).copy()
    tactics = data.get("tactics", pd.DataFrame()).copy()
    players = data.get("players", pd.DataFrame()).copy()
    timeline = data.get("medisports_timeline", pd.DataFrame()).copy()

    section_header("Season Preview", "Official Medisports season-by-season preview using loaded CSV data only.")

    roster_matches = get_medisports_roster_df(full_matches, player_col="player")
    if roster_matches.empty:
        st.warning("No Medisports player rows are available in the official match data.")
        return
    roster_matches["player_key"] = roster_matches["player"].map(normalize_player_key)
    roster_matches = roster_matches[roster_matches["player_key"] != ""]

    seasons = _season_options(roster_matches)
    if not seasons:
        st.warning("No resolved season values are available in the official player match data.")
        return

    latest = seasons[-1]
    if st.session_state.get("season_preview_selected") not in seasons:
        st.session_state["season_preview_selected"] = latest
    selected = st.selectbox(
        "Season",
        options=seasons,
        index=seasons.index(st.session_state["season_preview_selected"]),
        key="season_preview_selected",
        format_func=lambda value: f"Season {value}",
    )

    season_df = _filter_season(roster_matches, selected)
    season_tactics = _filter_season(tactics, selected)

    _render_overview_cards(season_df, season_tactics, selected)
    _render_roster_preview(season_df, players)
    _render_competition_preview(season_df)
    _render_map_preview(season_df)
    _render_timeline_preview(timeline, selected)
