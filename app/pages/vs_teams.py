import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

from app.components import data_section_shell, insight_card, section_header, style_refresh_note
from app.descriptions import matchup_insight
from app.filters import filter_panel_toggle
from app.metrics import confidence_from_sample


def render(ctx):
    tdf = ctx["tactics"]
    style_refresh_note()
    section_header("Medisports vs Teams", "Opponent scouting and matchup health")
    if tdf.empty:
        st.warning("No tactics/opponent data after filters.")
        return

    grp = (
        tdf.groupby("opponent_team", dropna=False)
        .agg(wins=("wins", "sum"), losses=("losses", "sum"), rounds=("total_rounds", "sum"))
        .reset_index()
    )
    grp["win_rate"] = (grp["wins"] / (grp["wins"] + grp["losses"]).clip(lower=1) * 100).fillna(0)
    grp["confidence"] = grp["rounds"].map(confidence_from_sample)

    opponent_options = ["All"] + sorted(grp["opponent_team"].astype(str).unique().tolist())
    if st.session_state.get("vs_teams_opponent") not in opponent_options:
        st.session_state["vs_teams_opponent"] = "All"

    if filter_panel_toggle("vs_teams"):
        st.selectbox("Drill into opponent", opponent_options, key="vs_teams_opponent")

    opp = st.session_state.get("vs_teams_opponent", "All")
    view = grp if opp == "All" else grp[grp["opponent_team"] == opp]

    data_section_shell("Matchup Overview", "Win profile by opponent with confidence context", tone="mid")
    st.dataframe(view.sort_values("win_rate", ascending=False), use_container_width=True, hide_index=True)

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.bar(view.sort_values("win_rate"), x="win_rate", y="opponent_team", orientation="h", color="confidence", title="Win rate by opponent")
        st.plotly_chart(fig, use_container_width=True)

    if opp != "All" and not view.empty:
        r = view.iloc[0]
        insight_card("Matchup Insight", matchup_insight(opp, r["wins"], r["losses"], r["win_rate"], r["rounds"]), "info")
        if r["rounds"] < 20:
            insight_card("Low sample warning", "Interpret this matchup with caution due to low round volume.", "warn")

    weak = grp.nsmallest(3, "win_rate")
    strong = grp.nlargest(3, "win_rate")
    c1, c2 = st.columns(2, gap="small")
    with c1:
        data_section_shell("Strongest Matchups", "Highest win-rate opponents in scope", tone="good")
        st.dataframe(strong[["opponent_team", "win_rate", "rounds", "confidence"]], use_container_width=True, hide_index=True)
    with c2:
        data_section_shell("Needs Fixing", "Lowest win-rate opponents in scope", tone="poor")
        st.dataframe(weak[["opponent_team", "win_rate", "rounds", "confidence"]], use_container_width=True, hide_index=True)
