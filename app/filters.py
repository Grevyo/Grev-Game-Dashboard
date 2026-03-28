import streamlit as st


def _sidebar_section(title: str):
    st.sidebar.markdown(f"<div class='sidebar-card'><div class='sidebar-head'>{title}</div></div>", unsafe_allow_html=True)


def build_global_filters(player_df, tactics_df):
    st.sidebar.markdown("## 🎛 Control Panel")

    _sidebar_section("Theme")
    theme = st.sidebar.selectbox("Theme", ["Dark", "Light"], index=0)

    _sidebar_section("Global Filters")
    comp_mode = st.sidebar.radio("Competition display", ["Grouped competitions", "Individual competitions"], index=0, horizontal=True)

    seasons = sorted([s for s in player_df.get("season", []).dropna().unique().tolist()]) if not player_df.empty and "season" in player_df.columns else []
    competitions_col = "competition_group" if comp_mode == "Grouped competitions" else "competition"

    filters = {
        "theme": theme,
        "season": st.sidebar.multiselect("Season", seasons, default=seasons),
        "competition_mode": comp_mode,
        "competition_col": competitions_col,
        "competition": st.sidebar.multiselect(
            "Competition",
            sorted(player_df.get(competitions_col, []).dropna().unique().tolist()) if not player_df.empty and competitions_col in player_df.columns else [],
        ),
        "map": st.sidebar.multiselect("Map", sorted(player_df.get("map", []).dropna().unique().tolist()) if not player_df.empty and "map" in player_df.columns else []),
        "opponent": st.sidebar.multiselect(
            "Opponent", sorted(player_df.get("opponent_team", []).dropna().unique().tolist()) if not player_df.empty and "opponent_team" in player_df.columns else []
        ),
        "side": st.sidebar.multiselect("Side", ["Red", "Blue"], default=[]),
        "last_days": st.sidebar.selectbox("Last X days", [None, 5, 10, 20, 30], index=0),
        "last_matches": st.sidebar.selectbox("Last X matches", [None, 5, 10, 20, 30], index=0),
    }

    _sidebar_section("Page Navigation")
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


def filter_summary(filters):
    active = []
    for key in ["season", "competition", "map", "opponent", "side", "last_days", "last_matches"]:
        value = filters.get(key)
        if value:
            active.append((key.replace("_", " ").title(), value if not isinstance(value, list) else f"{len(value)} selected"))

    if not active:
        st.sidebar.markdown("<div class='sidebar-card'><div class='sidebar-head'>Active Filters</div><span class='muted'>None active</span></div>", unsafe_allow_html=True)
        return "No global filters active"

    st.sidebar.markdown("<div class='sidebar-card'><div class='sidebar-head'>Active Filters</div></div>", unsafe_allow_html=True)
    for label, value in active[:8]:
        st.sidebar.markdown(f"<span class='chip'>{label}: {value}</span>", unsafe_allow_html=True)
    return " • ".join([f"{k}: {v}" for k, v in active])
