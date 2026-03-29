import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

from app.components import insight_card, section_header
from app.tactics import tactic_bucket, tactic_summary


def render(ctx):
    tdf = ctx["tactics"]
    st.title("Tactics Breakdown (Map + Side Strict)")
    if tdf.empty:
        st.warning("No tactics data after filters.")
        return

    summary = tactic_summary(tdf)
    if summary.empty:
        st.warning("Unable to derive tactic summaries.")
        return

    map_name = st.selectbox("Map", sorted(summary["map"].dropna().unique().tolist()))
    side = st.selectbox("Side", sorted(summary["side"].dropna().unique().tolist()))
    view = summary[(summary["map"] == map_name) & (summary["side"] == side)].copy()
    view["bucket"] = view.apply(tactic_bucket, axis=1)

    section_header("Context-locked tactic buckets", f"Showing exact context: {map_name} + {side}")
    st.dataframe(view.sort_values("score", ascending=False), use_container_width=True, hide_index=True)

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.bar(view, x="win_rate", y="tactic_name", color="bucket", orientation="h", title="Tactic quality buckets")
        st.plotly_chart(fig, use_container_width=True)

    low = view[view["uses"] < 5]
    if not low.empty:
        insight_card("Low sample warning", f"{len(low)} tactics have fewer than 5 rounds of sample in this map+side context.", "warn")
