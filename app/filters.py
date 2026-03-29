import pandas as pd
import streamlit as st

from app.competition import get_active_competition_col, is_grouped_mode


def _sorted_values(df: pd.DataFrame, col: str) -> list:
    if df.empty or col not in df.columns:
        return []
    vals = [v for v in df[col].dropna().unique().tolist()]
    return sorted(vals)


def _int_sorted_values(df: pd.DataFrame, col: str) -> list[str]:
    values = _sorted_values(df, col)
    ints = []
    for value in values:
        try:
            ints.append(int(str(value)))
        except Exception:
            continue
    sorted_values = [str(v) for v in sorted(set(ints))]
    if col in df.columns and df[col].isna().any():
        sorted_values.append("Unspecified")
    return sorted_values


def get_current_season(df: pd.DataFrame, season_col: str = "season") -> str | None:
    if df.empty or season_col not in df.columns:
        return None
    seasons = pd.to_numeric(df[season_col], errors="coerce").dropna()
    if seasons.empty:
        return None
    return str(int(seasons.max()))


def build_global_filters(player_df: pd.DataFrame, tactics_df: pd.DataFrame):
    st.markdown("<div class='toolbar-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title' style='margin-bottom:4px;'>Context Controls</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Compact page-level filters replacing the old sidebar stack.</div>", unsafe_allow_html=True)

    context_col, map_col, recency_col = st.columns([2.5, 2.2, 1.3], gap="small")

    with context_col:
        c1, c2, c3 = st.columns([0.9, 1.3, 2.0], gap="small")
        with c1:
            theme = st.selectbox("Theme", ["Dark", "Light"], index=0)
        with c2:
            comp_mode = st.radio("Competition mode", ["Grouped competitions", "Individual competitions"], index=0, horizontal=True)
        with c3:
            season_options = _int_sorted_values(player_df, "season")
            current_season = get_current_season(player_df, "season")
            default_season = [current_season] if current_season and current_season in season_options else season_options
            season_vals = st.multiselect("Season", season_options, default=default_season)

    competitions_col = get_active_competition_col(is_grouped_mode(comp_mode))

    with map_col:
        f1, f2, f3 = st.columns(3, gap="small")
        with f1:
            competition_vals = st.multiselect(
                "Competition",
                _sorted_values(player_df, competitions_col),
                key=f"competition_filter_{'group' if comp_mode == 'Grouped competitions' else 'individual'}",
            )
        with f2:
            map_vals = st.multiselect("Map", _sorted_values(player_df, "map"))
        with f3:
            opp_vals = st.multiselect("Opponent", _sorted_values(player_df, "opponent_team"))

    with recency_col:
        r1, r2, r3 = st.columns(3, gap="small")
        with r1:
            side_vals = st.multiselect("Side", ["Red", "Blue"], default=[])
        with r2:
            last_days = st.selectbox("Last X days", [None, 5, 10, 20, 30], index=0)
        with r3:
            last_matches = st.selectbox("Last X matches", [None, 5, 10, 20, 30], index=0)

    st.markdown("</div>", unsafe_allow_html=True)

    return {
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


def apply_filters(df, filters):
    if df.empty:
        return df
    out = df.copy()

    if filters.get("season") and "season" in out.columns:
        selected_seasons = {str(v) for v in filters["season"]}
        valid = {s for s in selected_seasons if s != "Unspecified"}
        include_unspecified = "Unspecified" in selected_seasons
        season_mask = out["season"].astype(str).isin(valid)
        if include_unspecified:
            season_mask = season_mask | out["season"].isna()
        out = out[season_mask]

    comp_col = filters.get("competition_col") or get_active_competition_col(is_grouped_mode(filters.get("competition_mode")))
    if filters.get("competition") and comp_col in out.columns:
        out = out[out[comp_col].isin(filters["competition"])]

    if filters.get("map") and "map" in out.columns:
        out = out[out["map"].isin(filters["map"])]
    if filters.get("opponent") and "opponent_team" in out.columns:
        out = out[out["opponent_team"].isin(filters["opponent"])]
    if filters.get("side") and "side" in out.columns:
        out = out[out["side"].isin(filters["side"])]

    if filters.get("last_days") and "date" in out.columns:
        cutoff = out["date"].max() - pd.Timedelta(days=filters["last_days"])
        out = out[out["date"] >= cutoff]

    if filters.get("last_matches") and "date" in out.columns:
        group_col = "player" if "player" in out.columns else None
        if group_col:
            out = out.sort_values("date").groupby(group_col, group_keys=False).tail(filters["last_matches"])
        else:
            out = out.sort_values("date").tail(filters["last_matches"])

    return out


def _active_items(filters):
    active = []
    if filters.get("competition_mode"):
        active.append(("Competition Mode", filters["competition_mode"]))
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
