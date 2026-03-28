import streamlit as st


def _sidebar_section(title: str):
    st.sidebar.markdown(f"<div class='sidebar-card'><div class='sidebar-head'>{title}</div></div>", unsafe_allow_html=True)


def build_global_filters(player_df, tactics_df):
    st.sidebar.markdown("## Control Center")

    _sidebar_section("Theme")
    theme = st.sidebar.selectbox("Theme", ["Dark", "Light"], index=0)

    _sidebar_section("Global Context")
    comp_mode = st.sidebar.radio("Competition display", ["Grouped competitions", "Individual competitions"], index=0)

    seasons = sorted([s for s in player_df.get("season", []).dropna().unique().tolist()]) if not player_df.empty and "season" in player_df.columns else []
    competitions_col = "competition_group" if comp_mode == "Grouped competitions" else "competition"

    with st.sidebar.expander("Scope Filters", expanded=True):
        season_vals = st.multiselect("Season", seasons, default=seasons)
        competition_vals = st.multiselect(
            "Competition",
            sorted(player_df.get(competitions_col, []).dropna().unique().tolist()) if not player_df.empty and competitions_col in player_df.columns else [],
        )
        map_vals = st.multiselect("Map", sorted(player_df.get("map", []).dropna().unique().tolist()) if not player_df.empty and "map" in player_df.columns else [])
        side_vals = st.multiselect("Side", ["Red", "Blue"], default=[])

    with st.sidebar.expander("Opponent + Recent Window", expanded=False):
        opp_vals = st.multiselect(
            "Opponent", sorted(player_df.get("opponent_team", []).dropna().unique().tolist()) if not player_df.empty and "opponent_team" in player_df.columns else []
        )
        last_days = st.selectbox("Last X days", [None, 5, 10, 20, 30], index=0)
        last_matches = st.selectbox("Last X matches", [None, 5, 10, 20, 30], index=0)

    filters = {
        "theme": theme,
        "season": season_vals,
        "competition_mode": comp_mode,
        "competition_col": competitions_col,
        "competition": competition_vals,
        "map": map_vals,
        "opponent": opp_vals,
        "side": side_vals,
        "last_days": last_days,
        "last_matches": last_matches,
    }
    return filters


def apply_filters(df, filters):
    if df.empty:
        return df
    out = df.copy()
    if filters.get("season") and "season" in out.columns:
        out = out[out["season"].isin(filters["season"])]
    comp_col = filters.get("competition_col", "competition")
    if filters.get("competition") and comp_col in out.columns:
        out = out[out[comp_col].isin(filters["competition"])]
    if filters.get("map") and "map" in out.columns:
        out = out[out["map"].isin(filters["map"])]
    if filters.get("opponent") and "opponent_team" in out.columns:
        out = out[out["opponent_team"].isin(filters["opponent"])]
    if filters.get("side") and "side" in out.columns:
        out = out[out["side"].isin(filters["side"])]
    if filters.get("last_days") and "date" in out.columns:
        cutoff = out["date"].max() - __import__("pandas").Timedelta(days=filters["last_days"])
        out = out[out["date"] >= cutoff]
    if filters.get("last_matches") and "date" in out.columns and "player" in out.columns:
        out = out.sort_values("date").groupby("player", group_keys=False).tail(filters["last_matches"])
    return out


def _active_items(filters):
    active = []
    for key in ["season", "competition", "map", "opponent", "side", "last_days", "last_matches"]:
        value = filters.get(key)
        if value:
            display = value if not isinstance(value, list) else ", ".join(map(str, value[:2])) + ("…" if len(value) > 2 else "")
            active.append((key.replace("_", " ").title(), display))
    return active


def filter_summary(filters):
    active = _active_items(filters)
    if not active:
        st.markdown("<div class='context-ribbon'><span class='muted'>No active context filters.</span></div>", unsafe_allow_html=True)
        return "No global filters active"

    chips = "".join([f"<span class='chip'>{k}: {v}</span>" for k, v in active[:10]])
    st.markdown(f"<div class='context-ribbon'><strong style='font-size:12px;'>Active Context</strong><div style='margin-top:6px'>{chips}</div></div>", unsafe_allow_html=True)
    return " • ".join([f"{k}: {v}" for k, v in active])
