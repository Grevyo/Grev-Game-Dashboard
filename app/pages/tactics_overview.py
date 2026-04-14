from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app.datetime_utils import build_match_timestamp, normalize_time_series
from app.map_utils import normalize_map_series


def _inject_page_css() -> None:
    st.markdown(
        """
        <style>
        .tov-hero-title{font-size:1.25rem;margin:0;color:#f5fbff;letter-spacing:.02em;}
        .tov-hero-subtitle{margin:.35rem 0 0;font-size:.82rem;color:#9fb0c4;max-width:980px;line-height:1.45;}
        .tov-control{padding:.75rem;margin-top:.65rem;}
        .tov-board{border:1px solid #2d3e51;background:linear-gradient(180deg,#122031,#0d1825);border-radius:10px;padding:.72rem;}
        .tov-board h4{margin:0 0 .4rem 0;font-size:.84rem;letter-spacing:.07em;text-transform:uppercase;color:#d7e6f8;}
        .tov-side-head{font-size:.73rem;color:#afc0d4;letter-spacing:.08em;text-transform:uppercase;margin:.35rem 0;}
        .tov-tier-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;}
        .tov-chip{display:inline-flex;align-items:center;border:1px solid #3b5067;border-radius:999px;padding:3px 9px;font-size:.62rem;background:#111e2d;color:#e1edfa;}
        .tov-chip.core{border-color:#5f8751;color:#9FE870;background:#152419;}
        .tov-chip.secondary{border-color:#7a6441;color:#d3a85c;background:#221d15;}
        .tov-chip.fringe{border-color:#7f5532;color:#ffb26a;background:#241a12;}
        .tov-map-shell{border:1px solid #2f4155;border-radius:10px;background:linear-gradient(180deg,#101a27,#0c1521);padding:.72rem;margin-top:.75rem;}
        .tov-map-head{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:.5rem;}
        .tov-map-title{margin:0;font-size:1rem;color:#edf5ff;letter-spacing:.02em;}
        .tov-match-meta{font-size:.66rem;color:#9db0c5;}
        .tov-tactic-col{border:1px solid #31465d;border-radius:7px;background:#111b28;padding:.55rem;}
        .tov-tactic-col h5{margin:0 0 .35rem 0;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:#cdddf0;}
        .tov-inline-meta{font-size:.66rem;color:#9eb1c7;line-height:1.45;}
        .tov-empty{font-size:.7rem;color:#8da2b9;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _prepare_tactics(tdf: pd.DataFrame) -> pd.DataFrame:
    scoped = tdf.copy()
    scoped["map"] = normalize_map_series(scoped.get("map", pd.Series(index=scoped.index, dtype=object)), unknown_label="Unknown")
    scoped["side"] = scoped.get("side", "Unknown").astype(str).str.strip().replace("", "Unknown")
    scoped["tactic_name"] = scoped.get("tactic_name", "Unknown Tactic").astype(str).str.strip().replace("", "Unknown Tactic")
    scoped["competition"] = scoped.get("competition", "Unknown").astype(str).str.strip().replace("", "Unknown")
    scoped["opponent_team"] = scoped.get("opponent_team", "Unknown").astype(str).str.strip().replace("", "Unknown")
    scoped["wins"] = pd.to_numeric(scoped.get("wins", 0), errors="coerce").fillna(0)
    scoped["losses"] = pd.to_numeric(scoped.get("losses", 0), errors="coerce").fillna(0)
    scoped["total_rounds"] = pd.to_numeric(scoped.get("total_rounds", 0), errors="coerce").fillna(0)

    date_series = scoped.get("date", pd.Series([None] * len(scoped), index=scoped.index))
    time_series = normalize_time_series(scoped.get("time", pd.Series([None] * len(scoped), index=scoped.index)))
    scoped["time"] = time_series
    scoped["match_ts"] = build_match_timestamp(date_series, time_series)
    scoped["match_ts"] = scoped["match_ts"].fillna(build_match_timestamp(date_series))

    scoped["match_id"] = scoped.get("match_id", "missing").astype(str)
    scoped["map_match_key"] = scoped["match_id"] + "||" + scoped["map"]
    return scoped


def _recent_match_rows(map_df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        map_df.groupby("map_match_key", dropna=False)
        .agg(
            match_ts=("match_ts", "max"),
            date=("date", "max"),
            time=("time", "max"),
            match_id=("match_id", "max"),
            map=("map", "max"),
            opponent_team=("opponent_team", "max"),
            competition=("competition", "max"),
            wins=("wins", "sum"),
            losses=("losses", "sum"),
            total_rounds=("total_rounds", "sum"),
        )
        .reset_index()
        .sort_values("match_ts", ascending=False)
    )
    return grouped.head(25).copy()


def _infer_rotation_labels(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        frame["set_band"] = []
        return frame

    enriched = frame.copy()
    enriched["last_used"] = pd.to_datetime(enriched["last_used"], errors="coerce")
    context_totals = enriched.groupby(["map", "side"], dropna=False)["match_count"].transform("sum").replace(0, 1)
    enriched["usage_share"] = enriched["match_count"] / context_totals

    newest = enriched["last_used"].max()
    days_ago = (newest - enriched["last_used"]).dt.total_seconds().div(86400).fillna(99)
    recency_bonus = pd.Series(0.0, index=enriched.index)
    recency_bonus = recency_bonus.mask(days_ago <= 1.0, 2.0)
    recency_bonus = recency_bonus.mask((days_ago > 1.0) & (days_ago <= 2.0), 1.0)

    enriched["rotation_score"] = enriched["match_count"] * 3 + enriched["recent_rounds"] / 4 + recency_bonus

    core_mask = (enriched["match_count"] >= 3) | (enriched["usage_share"] >= 0.35)
    secondary_mask = (~core_mask) & ((enriched["match_count"] >= 2) | (enriched["usage_share"] >= 0.15))
    enriched["set_band"] = "One-Off Recent Tests"
    enriched.loc[secondary_mask, "set_band"] = "Secondary Recent Use"
    enriched.loc[core_mask, "set_band"] = "Core Recent Set"

    return enriched


def _chip_list(names: list[str], chip_class: str = "") -> str:
    if not names:
        return "<span class='tov-empty'>No tactics logged.</span>"
    class_suffix = f" {chip_class}" if chip_class else ""
    return "".join(f"<span class='tov-chip{class_suffix}'>{html.escape(name)}</span>" for name in names)


def _render_current_set_board(recent_usage: pd.DataFrame, core_only: bool) -> None:
    st.markdown("<div class='section-title'>Current Set Overview</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>"
        "Live rotation read inferred from recent real usage. Grouped by map + side and split into core, secondary, and one-off tests."
        "</div>",
        unsafe_allow_html=True,
    )

    if recent_usage.empty:
        st.info("No tactics were used in the selected recent window.")
        return

    board = _infer_rotation_labels(recent_usage)
    if core_only:
        board = board[board["set_band"] == "Core Recent Set"].copy()
        if board.empty:
            st.info("No core tactics found in this window. Disable core-only to view all recent usage.")
            return

    contexts = board[["map", "side"]].drop_duplicates().sort_values(["map", "side"])
    for _, context in contexts.iterrows():
        map_name = context["map"]
        side = context["side"]
        scoped = board[(board["map"] == map_name) & (board["side"] == side)].copy()
        scoped = scoped.sort_values(["set_band", "rotation_score", "last_used"], ascending=[True, False, False])

        st.markdown("<div class='tov-board'>", unsafe_allow_html=True)
        st.markdown(f"<h4>{html.escape(map_name)} • {html.escape(side)}</h4>", unsafe_allow_html=True)

        for band, css_class in [
            ("Core Recent Set", "core"),
            ("Secondary Recent Use", "secondary"),
            ("One-Off Recent Tests", "fringe"),
        ]:
            rows = scoped[scoped["set_band"] == band]
            if rows.empty:
                continue
            names = rows["tactic_name"].tolist()
            st.markdown(f"<div class='tov-side-head'>{band}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='tov-tier-row'>{_chip_list(names, css_class)}</div>", unsafe_allow_html=True)

        detail = scoped[["tactic_name", "match_count", "recent_rounds", "recent_wr", "last_used"]].copy()
        detail["recent_wr"] = detail["recent_wr"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "N/A")
        detail["last_used"] = pd.to_datetime(detail["last_used"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
        detail.columns = ["Tactic", "Matches", "Rounds", "Recent WR", "Most Recent"]
        st.dataframe(detail, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_recent_usage_by_map(scoped: pd.DataFrame) -> None:
    st.markdown("<div class='section-title'>Recent Usage by Map</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>"
        "Each map shows its last 25 matches (most recent first) and all tactics used in each match, split by side."
        "</div>",
        unsafe_allow_html=True,
    )

    if scoped.empty:
        st.info("No map usage data in the current filter context.")
        return

    for map_name in sorted(scoped["map"].dropna().unique().tolist()):
        map_df = scoped[scoped["map"] == map_name].copy()
        recent_matches = _recent_match_rows(map_df)

        st.markdown("<div class='tov-map-shell'>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='tov-map-head'><h3 class='tov-map-title'>{html.escape(map_name)}</h3>"
            f"<div class='tov-match-meta'>{len(recent_matches)} / 25 most recent matches shown</div></div>",
            unsafe_allow_html=True,
        )

        for _, match in recent_matches.iterrows():
            match_key = match["map_match_key"]
            match_rows = map_df[map_df["map_match_key"] == match_key].copy()
            timestamp = pd.to_datetime(match["match_ts"], errors="coerce")
            ts_label = timestamp.strftime("%Y-%m-%d %H:%M") if pd.notna(timestamp) else "Unknown time"
            rounds = int(match["total_rounds"]) if pd.notna(match["total_rounds"]) else 0
            wins = int(match["wins"]) if pd.notna(match["wins"]) else 0
            losses = int(match["losses"]) if pd.notna(match["losses"]) else 0
            wr = (wins / rounds * 100.0) if rounds > 0 else float("nan")
            wr_label = f"{wr:.1f}%" if pd.notna(wr) else "N/A"

            title = f"{ts_label} • vs {match['opponent_team']} • {match['competition']} • {wins}-{losses} ({wr_label})"
            with st.expander(title, expanded=False):
                st.markdown(
                    f"<div class='tov-inline-meta'><strong>Match ID:</strong> {html.escape(str(match['match_id']))} &nbsp;|&nbsp; "
                    f"<strong>Total Tactical Rounds:</strong> {rounds}</div>",
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2, gap="small")
                for col, side in [(c1, "Red"), (c2, "Blue")]:
                    side_rows = match_rows[match_rows["side"] == side].copy()
                    if side_rows.empty:
                        side_rows = match_rows[match_rows["side"].str.lower() == side.lower()].copy()
                    names = side_rows.sort_values("total_rounds", ascending=False)["tactic_name"].dropna().astype(str).tolist()
                    with col:
                        st.markdown("<div class='tov-tactic-col'>", unsafe_allow_html=True)
                        st.markdown(f"<h5>{side} Side Tactics</h5>", unsafe_allow_html=True)
                        st.markdown(f"<div class='tov-tier-row'>{_chip_list(names)}</div>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                other_sides = sorted({str(s) for s in match_rows["side"].dropna().unique().tolist()} - {"Red", "Blue"})
                if other_sides:
                    st.markdown(f"<div class='tov-inline-meta' style='margin-top:.5rem;'><strong>Other side labels seen:</strong> {', '.join(other_sides)}</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


def render(ctx):
    tdf = ctx["tactics"].copy()
    if tdf.empty:
        st.warning("No tactics data after current filters.")
        return

    _inject_page_css()
    scoped = _prepare_tactics(tdf)

    st.markdown(
        """
        <div class='hero-band'>
            <div class='section-title'>Tactical Command Summary</div>
            <h1 class='tov-hero-title'>Tactics Overview</h1>
            <p class='tov-hero-subtitle'>
                Map-by-map recent tactical history with a live read on your currently active map+side tactical set.
                Built to show what is actually in rotation right now, based on recent real usage.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='panel tov-control'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.2, 1.0, 1.0, 1.2], gap="small")
    all_maps = sorted(scoped["map"].dropna().unique().tolist())
    all_sides = sorted(scoped["side"].dropna().unique().tolist())
    with c1:
        selected_maps = st.multiselect("Map", options=all_maps, default=all_maps)
    with c2:
        selected_sides = st.multiselect("Side", options=all_sides, default=all_sides)
    with c3:
        recent_days = st.slider("Current-set window (days)", min_value=1, max_value=14, value=3, step=1)
    with c4:
        core_only = st.toggle("Show only inferred core set", value=False)
    st.markdown("</div>", unsafe_allow_html=True)

    if selected_maps:
        scoped = scoped[scoped["map"].isin(selected_maps)].copy()
    if selected_sides:
        scoped = scoped[scoped["side"].isin(selected_sides)].copy()

    if scoped.empty:
        st.warning("No data after map/side filters.")
        return

    newest = scoped["match_ts"].max()
    cutoff = newest - pd.Timedelta(days=int(recent_days))
    recent = scoped[scoped["match_ts"] >= cutoff].copy()

    recent_usage = (
        recent.groupby(["map", "side", "tactic_name"], dropna=False)
        .agg(
            match_count=("map_match_key", "nunique"),
            recent_rounds=("total_rounds", "sum"),
            wins=("wins", "sum"),
            losses=("losses", "sum"),
            last_used=("match_ts", "max"),
        )
        .reset_index()
    )
    recent_usage["recent_wr"] = (recent_usage["wins"] / (recent_usage["wins"] + recent_usage["losses"]).replace(0, pd.NA) * 100).fillna(0)

    _render_current_set_board(recent_usage, core_only=core_only)
    _render_recent_usage_by_map(scoped)
