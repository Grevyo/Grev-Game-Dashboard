import streamlit as st
try:
    import plotly.express as px
except ModuleNotFoundError:
    px = None

from app.components import section_header, stat_card
from app.image_helpers import find_achievement_image, find_player_photo
from app.transforms import best_contexts


def render(ctx):
    df = ctx["player_matches"]
    achievements = ctx["achievements"]
    players = ctx["players"]

    st.title("Player Stats Viewer")
    if df.empty:
        st.warning("No player data found for current filters.")
        return

    player = st.selectbox("Select player", sorted(df["player"].dropna().unique().tolist()))
    p = df[df["player"] == player].sort_values("date")

    col1, col2 = st.columns([1, 3])
    with col1:
        ph = find_player_photo(player)
        if ph:
            st.image(ph, use_container_width=True)
    with col2:
        section_header(player, "Signature GrevScore + recent form story")
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
        st.dataframe(meta.head(1), use_container_width=True, hide_index=True)

    section_header("Achievements")
    ach = achievements[achievements.get("player_clean", achievements.get("player", "")).astype(str).str.contains(str(player), case=False, regex=False)]
    if ach.empty:
        st.caption("No achievements linked for selected player.")
    else:
        for _, a in ach.iterrows():
            cols = st.columns([1, 5])
            with cols[0]:
                img = find_achievement_image(a.get("achievement_link"))
                if img:
                    st.image(img, use_container_width=True)
            with cols[1]:
                st.markdown(f"**{a.get('achievement_name','Achievement')}** — {a.get('position','')} (Season {a.get('season_name','-')})")

    section_header("Performance Trends")
    if px is None:
        st.warning("Plotly is unavailable, so the performance trend chart cannot be displayed.")
    else:
        fig = px.line(p, x="date", y="grevscore", title="Match-by-match GrevScore", markers=True)
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
