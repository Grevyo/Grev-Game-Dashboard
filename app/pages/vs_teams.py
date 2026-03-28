import streamlit as st
try:
    import plotly.express as px
except ModuleNotFoundError:
    px = None

from app.components import insight_card, section_header
from app.descriptions import matchup_insight
from app.metrics import confidence_from_sample


def render(ctx):
    tdf = ctx["tactics"]
    st.title("Medisports vs Teams")
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

    opp = st.selectbox("Drill into opponent", ["All"] + sorted(grp["opponent_team"].astype(str).unique().tolist()))
    view = grp if opp == "All" else grp[grp["opponent_team"] == opp]

    section_header("Matchup Overview")
    st.dataframe(view.sort_values("win_rate", ascending=False), use_container_width=True, hide_index=True)

    if px is None:
        st.warning("Plotly is unavailable, so the matchup chart cannot be displayed.")
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
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Strongest Matchups")
        st.dataframe(strong[["opponent_team", "win_rate", "rounds", "confidence"]], use_container_width=True, hide_index=True)
    with c2:
        st.subheader("Needs Fixing")
        st.dataframe(weak[["opponent_team", "win_rate", "rounds", "confidence"]], use_container_width=True, hide_index=True)
