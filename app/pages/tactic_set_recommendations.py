import streamlit as st

from app.components import insight_card, section_header
from app.tactics import recommend_set, tactic_summary


def render(ctx):
    tdf = ctx["tactics"]
    st.title("Tactical Set Recommendations")
    st.caption("Recommendations are strictly bound to one exact map + side context.")

    if tdf.empty:
        st.warning("No tactics data available for recommendations.")
        return

    summary = tactic_summary(tdf)
    if summary.empty:
        st.warning("No tactic summary could be generated.")
        return

    c1, c2 = st.columns(2)
    with c1:
        map_name = st.selectbox("Map context", sorted(summary["map"].dropna().unique().tolist()))
    with c2:
        side = st.selectbox("Side context", sorted(summary["side"].dropna().unique().tolist()))

    recs = recommend_set(summary, map_name, side)
    if recs.empty:
        st.info("No candidates for this context yet. Add more tactic logs.")
        return

    section_header("Recommended Set Summary")
    coverage = recs.groupby("category")["tactic_name"].count().to_dict()
    insight_card("Category coverage", ", ".join([f"{k}: {v}" for k, v in coverage.items()]))

    for _, r in recs.iterrows():
        with st.container(border=True):
            st.markdown(f"#### {r['tactic_name']}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Category", r["category"])
            c2.metric("Score", f"{r['score']:.1f}")
            c3.metric("Win Rate", f"{r['win_rate']:.1f}%")
            c4.metric("Uses", int(r["uses"]))
            st.caption(r["reason"])

    near_miss = summary[(summary["map"] == map_name) & (summary["side"] == side)].sort_values("score", ascending=False)
    near_miss = near_miss[~near_miss["tactic_name"].isin(recs["tactic_name"])].head(5)
    if not near_miss.empty:
        section_header("Near Misses")
        st.dataframe(near_miss[["tactic_name", "category", "score", "win_rate", "uses"]], use_container_width=True, hide_index=True)
