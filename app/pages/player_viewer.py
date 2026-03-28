import streamlit as st

try:
    import plotly.express as px

    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    PLOTLY_AVAILABLE = False

from app.components import section_header, stat_card
from app.data_loader import is_medisports_team
from app.transforms import best_contexts


def _is_medisports_row(row) -> bool:
    team_ok = is_medisports_team(row.get("my_team", ""))
    player_tag = str(row.get("player", "")).strip().lower().startswith("ⓜ")
    return team_ok or player_tag


def _medisports_roster(df):
    if df.empty or "player" not in df.columns:
        return []
    mask = df.apply(_is_medisports_row, axis=1)
    roster = sorted(df[mask]["player"].dropna().unique().tolist())
    return roster


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
    df = ctx["player_matches"]
    achievements = ctx["achievements"]
    players = ctx["players"]
    team_name = ctx.get("team_name", "Medisports")

    if df.empty:
        st.warning("No player data found for current filters.")
        return

    medisports_roster = _medisports_roster(df)
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

    st.markdown(
        f"""
        <div class='hero-band'>
          <div style='display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;'>
            <div style='flex:1;min-width:280px;'>
              <div class='section-title' style='margin-top:0'>{player}</div>
              <div class='section-subtitle'>{country + ' • ' if country else ''}{role if role else 'Core Roster'} • {team_name}</div>
              <span class='chip'>Role: {role if role else 'N/A'}</span>
              <span class='chip'>Country: {country if country else 'N/A'}</span>
              <span class='chip chip-good'>Best Map: {best_map_label}</span>
              <span class='chip chip-mid'>Best Side: {best_side_label}</span>
              <div class='muted' style='margin-top:8px;'>Current form summary: {player} is {trend.lower()} with a {p['grevscore'].mean():.1f} GrevScore baseline in this scope.</div>
            </div>
            <div style='min-width:340px;flex:1;'>
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

    section_header("Achievements Ribbon", "Compact accolade strip")
    ach = achievements[achievements.get("player_clean", achievements.get("player", "")).astype(str).str.contains(str(player), case=False, regex=False)]
    if ach.empty:
        st.caption("No achievements linked for selected player.")
    else:
        cols = st.columns(min(4, max(1, len(ach))), gap="small")
        for idx, (_, a) in enumerate(ach.head(8).iterrows()):
            with cols[idx % len(cols)]:
                st.markdown(
                    f"<div class='panel panel-tight accent-mid'><strong>{a.get('achievement_name','Achievement')}</strong><br>"
                    f"<span class='muted'>{a.get('position','')} • {a.get('season_name','-')}</span></div>",
                    unsafe_allow_html=True,
                )

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
    with c2:
        st.markdown("#### By Side")
        st.dataframe(best_contexts(p, "side").head(8), use_container_width=True, hide_index=True)
    with c3:
        st.markdown("#### By Competition")
        st.dataframe(
            best_contexts(p, "competition_group" if "competition_group" in p.columns else "competition").head(8),
            use_container_width=True,
            hide_index=True,
        )
