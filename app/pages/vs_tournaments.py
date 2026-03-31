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
from app.presentation_helpers import is_mobile_view


def render(ctx):
    tdf = ctx["tactics"]
    filters = ctx["filters"]
    mobile_view = is_mobile_view()
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
    st.markdown("<div class='table-frame'>", unsafe_allow_html=True)
    st.dataframe(grp.sort_values("win_rate", ascending=False), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.scatter(grp, x="round_diff", y="win_rate", size="rounds", color="confidence", hover_name="competition", title="Over/Under-performance by competition")
        fig.update_layout(
            height=320 if mobile_view else 420,
            margin=dict(l=12 if mobile_view else 14, r=12 if mobile_view else 14, t=62, b=28 if mobile_view else 40),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=1.0 if mobile_view else 1.02,
                xanchor="left",
                x=0,
                title_text="",
            ),
            hoverlabel=dict(namelength=-1),
        )
        fig.update_xaxes(automargin=True, tickfont=dict(size=10 if mobile_view else 11))
        fig.update_yaxes(automargin=True, ticksuffix="%", range=[0, 100], tickfont=dict(size=10 if mobile_view else 11))
        st.markdown("<div class='analytics-frame'>", unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        st.markdown("</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Best Events")
        st.markdown("<div class='table-frame'>", unsafe_allow_html=True)
        st.dataframe(grp.nlargest(5, "win_rate"), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.subheader("Worst Events")
        st.markdown("<div class='table-frame'>", unsafe_allow_html=True)
        st.dataframe(grp.nsmallest(5, "win_rate"), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
