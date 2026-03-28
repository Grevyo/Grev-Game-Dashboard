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


def _medisports_roster(df):
    if df.empty or "my_team" not in df.columns or "player" not in df.columns:
        return []
    roster = sorted(df[df["my_team"].astype(str).map(is_medisports_team)]["player"].dropna().unique().tolist())
    return roster


def render(ctx):
    df = ctx["player_matches"]
    achievements = ctx["achievements"]
    players = ctx["players"]

    st.title("Player Stats Viewer")
    if df.empty:
        st.warning("No player data found for current filters.")
        return

    medisports_roster = _medisports_roster(df)
    if not medisports_roster:
        st.warning("No Medisports players found in the filtered data yet. Try relaxing global filters.")
        return

    player = st.selectbox("Select Medisports player", medisports_roster)
    p = df[df["player"] == player].sort_values("date")

    section_header(player, "Medisports-only performance profile")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        stat_card("GrevScore", f"{p['grevscore'].mean():.1f}")
    with m2:
        stat_card("Rating", f"{p['rating'].mean():.2f}")
    with m3:
        stat_card("Impact", f"{p['impact'].mean():.1f}")
    with m4:
        stat_card("K/D", f"{p['kpd'].mean():.2f}")

    meta = players[players.get("player_clean", players.get("name", "")).astype(str).str.contains(str(player), case=False, regex=False)]
    if not meta.empty:
        m = meta.head(1)
        line = " • ".join(
            [
                str(m.iloc[0].get("country", "")).strip(),
                str(m.iloc[0].get("role", "")).strip(),
            ]
        ).strip(" •")
        if line:
            st.caption(line)

    section_header("Achievements")
    ach = achievements[achievements.get("player_clean", achievements.get("player", "")).astype(str).str.contains(str(player), case=False, regex=False)]
    if ach.empty:
        st.caption("No achievements linked for selected player.")
    else:
        for _, a in ach.iterrows():
            st.markdown(
                f"<div class='panel panel-tight'><strong>{a.get('achievement_name','Achievement')}</strong><br>"
                f"<span class='muted'>{a.get('position','')} • Season {a.get('season_name','-')}</span></div>",
                unsafe_allow_html=True,
            )

    section_header("Performance Trends")
    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.line(p, x="date", y="grevscore", title="Match-by-match GrevScore", markers=True)
        fig.update_traces(line_color="#21c77a")
        fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("By Map")
        st.dataframe(best_contexts(p, "map").head(8), use_container_width=True, hide_index=True)
    with c2:
        if "side" in p.columns:
            st.subheader("By Side")
            st.dataframe(best_contexts(p, "side"), use_container_width=True, hide_index=True)
    with c3:
        st.subheader("By Competition")
        st.dataframe(best_contexts(p, "competition_group" if "competition_group" in p.columns else "competition").head(8), use_container_width=True, hide_index=True)
