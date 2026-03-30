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
from app.filters import filter_panel_toggle
from app.tactics import tactic_bucket, tactic_summary


def render(ctx):
    tdf = ctx["tactics"]
    style_refresh_note()
    section_header("Tactics Breakdown (Map + Side Strict)", "Context-locked route performance and tactical quality")
    if tdf.empty:
        st.warning("No tactics data after filters.")
        return

    summary = tactic_summary(tdf)
    if summary.empty:
        st.warning("Unable to derive tactic summaries.")
        return

    map_options = sorted(summary["map"].dropna().unique().tolist())
    side_options = sorted(summary["side"].dropna().unique().tolist())

    if st.session_state.get("tactics_breakdown_map") not in map_options:
        st.session_state["tactics_breakdown_map"] = map_options[0]
    if st.session_state.get("tactics_breakdown_side") not in side_options:
        st.session_state["tactics_breakdown_side"] = side_options[0]

    if filter_panel_toggle("tactics_breakdown"):
        f1, f2 = st.columns(2, gap="small")
        with f1:
            st.selectbox("Map", map_options, key="tactics_breakdown_map")
        with f2:
            st.selectbox("Side", side_options, key="tactics_breakdown_side")

    map_name = st.session_state.get("tactics_breakdown_map", map_options[0])
    side = st.session_state.get("tactics_breakdown_side", side_options[0])
    view = summary[(summary["map"] == map_name) & (summary["side"] == side)].copy()
    view["bucket"] = view.apply(tactic_bucket, axis=1)

    data_section_shell("Context-locked tactic buckets", f"Showing exact context: {map_name} + {side}", tone="mid")
    st.dataframe(view.sort_values("score", ascending=False), use_container_width=True, hide_index=True)

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.bar(view, x="win_rate", y="tactic_name", color="bucket", orientation="h", title="Tactic quality buckets")
        st.plotly_chart(fig, use_container_width=True)

    low = view[view["uses"] < 5]
    if not low.empty:
        insight_card("Low sample warning", f"{len(low)} tactics have fewer than 5 rounds of sample in this map+side context.", "warn")
