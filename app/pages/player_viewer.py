import streamlit as st

try:
    import plotly.express as px

    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    PLOTLY_AVAILABLE = False

from app.components import section_header, stat_card
from app.achievements import achievements_for_player
from app.competition import competition_cols_for_mode, get_competition_display_col
from app.data_loader import get_medisports_player_names, get_medisports_roster_df
from app.image_helpers import (
    find_competition_logo,
    find_map_image,
    find_team_logo,
    image_data_uri,
    resolve_player_photo,
)
from app.transforms import best_contexts


def _form_delta(p):
    if p.empty or "grevscore" not in p.columns:
        return 0.0
    tail = p.sort_values("date").tail(10)["grevscore"]
    if tail.empty:
        return 0.0
    half = max(1, len(tail) // 2)
    early = tail.head(half).mean()
    recent = tail.tail(half).mean()
    return float(recent - early)


def render(ctx):
    df = get_medisports_roster_df(ctx["player_matches"], player_col="player")
    achievements = ctx["achievements"]
    filters = ctx.get("filters", {})
    players = ctx["players"]
    team_name = ctx.get("team_name", "Medisports")

    if df.empty:
        st.warning("No player data found for current filters.")
        return

    medisports_roster = get_medisports_player_names(df, player_col="player")
    if not medisports_roster:
        st.warning("No Medisports players found in the filtered data yet. Try relaxing global filters.")
        return

    section_header("Player Stats Viewer", "Flagship profile layout for Medisports roster only")

    with st.container():
        st.markdown("<div class='toolbar-shell'>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2.3, 1.2, 1.2], gap="small")
        with c1:
            player = st.selectbox("Select Medisports player", medisports_roster)
        with c2:
            show_recent = st.toggle("Last 30-day focus", value=False)
        with c3:
            show_filters = st.toggle("Expand profile filters", value=False)
        if show_filters:
            f1, f2 = st.columns(2, gap="small")
            with f1:
                map_focus = st.multiselect("Map focus", sorted(df["map"].dropna().unique().tolist()) if "map" in df.columns else [])
            with f2:
                side_focus = st.multiselect("Side focus", sorted(df["side"].dropna().unique().tolist()) if "side" in df.columns else [])
        else:
            map_focus, side_focus = [], []
        st.markdown("</div>", unsafe_allow_html=True)

    mask = df["player"] == player
    if show_recent and "date" in df.columns:
        cutoff = df["date"].max() - __import__("pandas").Timedelta(days=30)
        mask &= df["date"] >= cutoff
    if map_focus and "map" in df.columns:
        mask &= df["map"].isin(map_focus)
    if side_focus and "side" in df.columns:
        mask &= df["side"].isin(side_focus)

    p = df[mask].sort_values("date")
    if p.empty:
        st.warning("Selected player has no rows in current profile scope.")
        return

    meta = players[players.get("player_clean", players.get("name", "")).astype(str).str.contains(str(player), case=False, regex=False)]
    country = str(meta.iloc[0].get("country", "")).strip() if not meta.empty else ""
    role = str(meta.iloc[0].get("role", "")).strip() if not meta.empty else ""

    best_map = best_contexts(p, "map").head(1)
    best_side = best_contexts(p, "side").head(1)
    best_map_label = str(best_map.iloc[0]["map"]) if not best_map.empty else "N/A"
    best_side_label = str(best_side.iloc[0]["side"]) if not best_side.empty else "N/A"

    delta_10 = _form_delta(p)
    trend = "Heating Up" if delta_10 > 2 else "Cooling" if delta_10 < -2 else "Stable"
    streak = f"{int((p['grevscore'] >= p['grevscore'].mean()).tail(5).sum())}/5 solid"

    player_photo_match = resolve_player_photo(player)
    player_photo = image_data_uri(player_photo_match.get("path"))
    team_logo = image_data_uri(find_team_logo(team_name) or find_team_logo("Medisports"))
    hero_photo = (
        f"<div class='hero-player-photo-frame'><img class='hero-player-photo' src='{player_photo}' alt='Player photo'/></div>"
        if player_photo
        else f"<div class='hero-player-photo-frame'><div class='player-avatar fallback-avatar'>No Photo ({player_photo_match.get('reason', 'not found')})</div></div>"
    )
    hero_logo = f"<img class='hero-logo' src='{team_logo}' alt='Medisports logo'/>" if team_logo else ""

    st.markdown(
        f"""
        <div class='hero-band'>
          <div style='display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;'>
            <div style='flex:1;min-width:300px;display:flex;align-items:flex-start;gap:14px;'>
              {hero_photo}
              <div>
                <div class='section-title' style='margin-top:0'>{player}</div>
                <div class='section-subtitle'>{country + ' • ' if country else ''}{role if role else 'Core Roster'} • {team_name}</div>
                <span class='chip'>Role: {role if role else 'N/A'}</span>
                <span class='chip'>Country: {country if country else 'N/A'}</span>
                <span class='chip chip-good'>Best Map: {best_map_label}</span>
                <span class='chip chip-mid'>Best Side: {best_side_label}</span>
                <div class='muted' style='margin-top:8px;'>Current form summary: {player} is {trend.lower()} with a {p['grevscore'].mean():.1f} GrevScore baseline in this scope.</div>
              </div>
            </div>
            <div style='min-width:340px;flex:1;'>
              <div style='display:flex;justify-content:flex-end;margin-bottom:8px;'>{hero_logo}</div>
              <div class='subtle-grid'>
                <div class='panel panel-tight accent-mid'><div class='metric-title'>Team Rank</div><div class='metric-value'>{int((df.groupby('player')['grevscore'].mean().rank(ascending=False, method='min').get(player, 0)))}</div></div>
                <div class='panel panel-tight accent-good'><div class='metric-title'>Record</div><div class='metric-value'>{int((p['grevscore'] >= 60).sum())}-{int((p['grevscore'] < 60).sum())}</div></div>
                <div class='panel panel-tight accent-mid'><div class='metric-title'>Recent Streak</div><div class='metric-value'>{streak}</div></div>
                <div class='panel panel-tight accent-{'good' if delta_10 >= 0 else 'bad'}'><div class='metric-title'>Last 10 Δ</div><div class='metric-value'>{delta_10:+.1f}</div></div>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    section_header("Achievements Ribbon", "Compact accolade strip with local images")
    ach_items, ach_hidden = achievements_for_player(achievements, player, cap=6)
    if not ach_items:
        st.caption("No achievements linked for selected player.")
    else:
        cols = st.columns(min(3, max(1, len(ach_items))), gap="small")
        for idx, a in enumerate(ach_items):
            img_html = f"<img class='achievement-thumb' src='{a.get('image_uri')}' alt='Achievement image'/>" if a.get("image_uri") else ""
            with cols[idx % len(cols)]:
                st.markdown(
                    f"<div class='panel panel-tight accent-mid'>{img_html}<strong>{a.get('name','Achievement')}</strong><br>"
                    f"<span class='muted'>{a.get('position','')} • Season {a.get('season','-')} • Tier {a.get('tier','-')}</span></div>",
                    unsafe_allow_html=True,
                )
        if ach_hidden:
            st.markdown(f"<div class='muted'>+{ach_hidden} more achievements not shown in ribbon.</div>", unsafe_allow_html=True)

    section_header("Performance Core", "GrevScore feature and headline cards")
    left, right = st.columns([1.3, 1], gap="small")
    with left:
        stat_card("Signature GrevScore", f"{p['grevscore'].mean():.1f}", "Primary contribution signal", "good")
        if PLOTLY_AVAILABLE:
            fig = px.line(p, x="date", y="grevscore", title="GrevScore Trend", markers=True)
            fig.update_traces(line_color="#21c77a")
            fig.update_layout(margin=dict(l=10, r=10, t=44, b=10), height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    with right:
        g1, g2 = st.columns(2, gap="small")
        with g1:
            stat_card("Rating", f"{p['rating'].mean():.2f}", "Composite consistency")
            stat_card("K/D", f"{p['kpd'].mean():.2f}", "Elimination efficiency")
        with g2:
            stat_card("Impact", f"{p['impact'].mean():.1f}", "Round influence")
            stat_card("Headshot %", f"{p['hs_pct'].mean():.1f}%", "Precision profile")

    section_header("Core Stats Grid", "Balanced compact stat matrix")
    s1, s2, s3, s4 = st.columns(4, gap="small")
    with s1:
        stat_card("Matches", int(p["match_id"].nunique()), "In current profile scope")
    with s2:
        stat_card("Avg Accuracy", f"{p['accuracy_pct'].mean():.1f}%", "Shot reliability")
    with s3:
        stat_card("Avg KPR", f"{p['kpr'].mean():.2f}", "Kills per round")
    with s4:
        stat_card("MVPs", int(p.get("mvps", 0).sum()), "Total MVPs captured")

    section_header("Lower Analytics", "Map, side, and competition context")
    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        st.markdown("#### By Map")
        st.dataframe(best_contexts(p, "map").head(8), use_container_width=True, hide_index=True)
        if best_map_label != "N/A":
            map_uri = image_data_uri(find_map_image(best_map_label))
            if map_uri:
                st.markdown(f"<img class='map-thumb' src='{map_uri}' alt='Map image'/>", unsafe_allow_html=True)
    with c2:
        st.markdown("#### By Side")
        st.dataframe(best_contexts(p, "side").head(8), use_container_width=True, hide_index=True)
    with c3:
        st.markdown("#### By Competition")
        by_comp_key = get_competition_display_col(filters.get("competition_mode"))
        for fallback_col in competition_cols_for_mode(filters.get("competition_mode")):
            if fallback_col in p.columns:
                by_comp_key = fallback_col
                break
        by_comp = best_contexts(p, by_comp_key).head(8)
        st.dataframe(by_comp, use_container_width=True, hide_index=True)
        if not by_comp.empty:
            logo_cols = st.columns(min(3, len(by_comp)), gap="small")
            for idx, (_, comp_row) in enumerate(by_comp.head(3).iterrows()):
                top_comp = str(comp_row[by_comp_key])
                comp_uri = image_data_uri(find_competition_logo(top_comp))
                with logo_cols[idx % len(logo_cols)]:
                    if comp_uri:
                        st.markdown(f"<img class='competition-thumb' src='{comp_uri}' alt='Competition logo'/><div class='muted'>{top_comp}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='panel panel-tight'><div class='muted'>{top_comp}</div></div>", unsafe_allow_html=True)
