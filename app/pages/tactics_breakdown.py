import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

from app.components import insight_card
from app.filters import filter_panel_toggle
from app.tactics import tactic_bucket, tactic_summary
from app.page_layout import is_mobile_view, section_header

def _format_last_used(value) -> str:
    if pd.isna(value):
        return "N/A"
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return "N/A"
    return ts.strftime("%Y-%m-%d")


def _reason_without_tactic_name(score: float, trend: str, sample: float) -> str:
    sample = int(sample or 0)
    if sample >= 10:
        sample_note = "Strong sample"
    elif sample >= 5:
        sample_note = "Usable sample"
    else:
        sample_note = "Low sample"

    if score >= 70:
        quality_note = "above-baseline conversion"
    elif score >= 55:
        quality_note = "stable conversion"
    elif score >= 40:
        quality_note = "mixed conversion"
    else:
        quality_note = "weak conversion"

    trend_note = {
        "Rising": "with improving results",
        "Flat": "with stable round volume",
        "Falling": "with recent decline",
    }.get(str(trend), "with limited trend clarity")

    return f"{sample_note} and {quality_note} {trend_note}."


def _build_display_view(summary: pd.DataFrame, tactics_df: pd.DataFrame, map_name: str, side: str) -> pd.DataFrame:
    view = summary[(summary["map"] == map_name) & (summary["side"] == side)].copy()

    last_used = (
        tactics_df.assign(date=pd.to_datetime(tactics_df.get("date"), errors="coerce"))
        .groupby(["map", "side", "tactic_name"], dropna=False)["date"]
        .max()
        .reset_index()
        .rename(columns={"date": "date_last_used"})
    )

    view = view.merge(last_used, on=["map", "side", "tactic_name"], how="left")
    view["date_last_used"] = view["date_last_used"].map(_format_last_used)
    view["reason"] = view.apply(
        lambda r: _reason_without_tactic_name(r["score"], r["trend"], r["uses"]), axis=1
    )
    view["bucket"] = view.apply(tactic_bucket, axis=1)

    return view[[
        "tactic_name",
        "category",
        "map",
        "side",
        "uses",
        "wins",
        "losses",
        "win_rate",
        "score",
        "trend",
        "bucket",
        "date_last_used",
        "reason",
    ]]


def render(ctx):
    tdf = ctx["tactics"]
    mobile_view = is_mobile_view()
    section_header("Tactics Breakdown", "Strict context matrix by map and side")
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
        st.markdown("<div class='toolbar-shell'>", unsafe_allow_html=True)
        f1, f2 = st.columns(2, gap="small")
        with f1:
            st.selectbox("Map", map_options, key="tactics_breakdown_map")
        with f2:
            st.selectbox("Side", side_options, key="tactics_breakdown_side")
        st.markdown("</div>", unsafe_allow_html=True)

    map_name = st.session_state.get("tactics_breakdown_map", map_options[0])
    side = st.session_state.get("tactics_breakdown_side", side_options[0])
    view = _build_display_view(summary, tdf, map_name, side)

    section_header("Context-locked tactic buckets", f"Showing exact context: {map_name} + {side}")
    st.markdown("<div class='table-frame'>", unsafe_allow_html=True)
    st.dataframe(view.sort_values("score", ascending=False), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.bar(view, x="win_rate", y="tactic_name", color="bucket", orientation="h", title="Tactic quality buckets")
        chart_height = 320 if mobile_view else 360
        if len(view) > 6:
            chart_height = min(560 if mobile_view else 680, chart_height + (24 if mobile_view else 34) * len(view))
        fig.update_layout(
            height=chart_height,
            margin=dict(l=12, r=12, t=56, b=16 if mobile_view else 20),
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
        fig.update_xaxes(automargin=True, ticksuffix="%", tickfont=dict(size=10 if mobile_view else 11))
        fig.update_yaxes(automargin=True, tickfont=dict(size=10 if mobile_view else 11))
        st.markdown("<div class='analytics-frame'>", unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        st.markdown("</div>", unsafe_allow_html=True)

    low = view[view["uses"] < 5]
    if not low.empty:
        insight_card("Low sample warning", f"{len(low)} tactics have fewer than 5 rounds of sample in this map+side context.", "warn")
