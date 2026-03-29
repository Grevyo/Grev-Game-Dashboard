import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

from app.components import section_header
from app.competition import get_active_competition_col, is_grouped_mode
from app.metrics import confidence_from_sample
from app.transforms import with_resolved_season


def render(ctx):
    tdf = with_resolved_season(ctx["tactics"], date_col="date")
    filters = ctx["filters"]
    col = get_active_competition_col(is_grouped_mode(filters.get("competition_mode")))

    st.title("Medisports vs Tournaments")
    if tdf.empty or col not in tdf.columns:
        st.warning("Tournament data unavailable for current mode.")
        return

    grp = (
        tdf.groupby(col, dropna=False)
        .agg(wins=("wins", "sum"), losses=("losses", "sum"), rounds=("total_rounds", "sum"), opponents=("opponent_team", "nunique"), maps=("map", "nunique"))
        .reset_index()
        .rename(columns={col: "competition"})
    )
    grp["win_rate"] = (grp["wins"] / (grp["wins"] + grp["losses"]).clip(lower=1) * 100).fillna(0)
    grp["round_diff"] = grp["wins"] - grp["losses"]
    grp["confidence"] = grp["rounds"].map(confidence_from_sample)

    section_header("Tournament Performance")
    st.dataframe(grp.sort_values("win_rate", ascending=False), use_container_width=True, hide_index=True)

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.scatter(grp, x="round_diff", y="win_rate", size="rounds", color="confidence", hover_name="competition", title="Over/Under-performance by competition")
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Best Events")
        st.dataframe(grp.nlargest(5, "win_rate"), use_container_width=True, hide_index=True)
    with c2:
        st.subheader("Worst Events")
        st.dataframe(grp.nsmallest(5, "win_rate"), use_container_width=True, hide_index=True)
