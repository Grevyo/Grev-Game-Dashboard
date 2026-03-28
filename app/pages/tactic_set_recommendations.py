import streamlit as st

from app.components import insight_card, section_header, trend_chip
from app.tactics import recommend_set, tactic_summary


def _confidence_label(score: float) -> str:
    if score >= 72:
        return "High"
    if score >= 58:
        return "Medium"
    return "Low"


def render(ctx):
    tdf = ctx["tactics"]
    filters = ctx.get("filters", {})

    if tdf.empty:
        st.warning("No tactics data available for recommendations.")
        return

    summary = tactic_summary(tdf)
    if summary.empty:
        st.warning("No tactic summary could be generated.")
        return

    section_header("Tactical Set Recommendations", "Context-locked recommendation engine")

    st.markdown("<div class='toolbar-shell'>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5, gap="small")
    with c1:
        season_hint = (filters.get("season") or ["Current"])[0]
        st.caption(f"Season: {season_hint}")
    with c2:
        map_name = st.selectbox("Map", sorted(summary["map"].dropna().unique().tolist()))
    with c3:
        side = st.selectbox("Side", sorted(summary["side"].dropna().unique().tolist()))
    with c4:
        min_sample = st.slider("Min sample", 1, 20, 5)
    with c5:
        confidence_floor = st.slider("Confidence floor", 40, 85, 55)

    t1, t2 = st.columns(2, gap="small")
    with t1:
        include_tentative = st.toggle("Include tentative", value=True)
    with t2:
        strict_mode = st.toggle("Strict confidence", value=False)
    st.markdown("</div>", unsafe_allow_html=True)

    recs = recommend_set(summary, map_name, side)
    recs = recs[recs["uses"] >= min_sample]
    threshold = confidence_floor + (8 if strict_mode else 0)
    recs = recs[recs["score"] >= threshold]

    if recs.empty:
        st.info("No candidates for this context and confidence floor yet.")
        return

    section_header("Recommendation Summary Band")
    coverage = recs.groupby("category")["tactic_name"].count().to_dict()
    confidence_mix = recs["score"].map(_confidence_label).value_counts().to_dict()
    s1, s2, s3, s4 = st.columns(4, gap="small")
    with s1:
        insight_card("Recommended Tactics", f"{len(recs)} tactics cleared the current floor.", "good")
    with s2:
        insight_card("Category Coverage", ", ".join([f"{k}: {v}" for k, v in coverage.items()]), "info")
    with s3:
        insight_card("Confidence Mix", ", ".join([f"{k}: {v}" for k, v in confidence_mix.items()]), "warn")
    with s4:
        insight_card("Context", f"{map_name} • {side} • min sample {min_sample}", "info")

    section_header("Legend")
    st.markdown(
        "<div class='panel panel-tight'><span class='chip chip-good'>High</span><span class='chip chip-mid'>Medium</span><span class='chip chip-poor'>Low</span>"
        "<div class='muted'>Cards emphasize score, win rate, usage volume, and trend chips for quick scan.</div></div>",
        unsafe_allow_html=True,
    )

    section_header("Tactic Cards", "Primary recommendation surface")
    for _, r in recs.sort_values("score", ascending=False).iterrows():
        confidence = _confidence_label(float(r["score"]))
        tone = "good" if confidence == "High" else "mid" if confidence == "Medium" else "poor"
        st.markdown(
            f"""
            <div class='panel accent-{tone}' style='margin-bottom:10px;'>
              <div style='display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;'>
                <div>
                  <div class='section-title' style='margin:0;font-size:1rem;'>{r['tactic_name']}</div>
                  <div class='section-subtitle' style='margin:3px 0 0 0;'>{r['category']} • {r['bucket']}</div>
                </div>
                <div>{trend_chip(r['trend'])}<span class='chip chip-{tone}'>{confidence} confidence</span></div>
              </div>
              <div class='subtle-grid' style='margin-top:10px;'>
                <div class='stat-item'><div class='label'>Score</div><div class='value'>{r['score']:.1f}</div></div>
                <div class='stat-item'><div class='label'>Win Rate</div><div class='value'>{r['win_rate']:.1f}%</div></div>
                <div class='stat-item'><div class='label'>Uses</div><div class='value'>{int(r['uses'])}</div></div>
                <div class='stat-item'><div class='label'>Route Key</div><div class='value'>{r['route_key']}</div></div>
              </div>
              <div class='muted' style='margin-top:8px;'>{r['reason']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    pool = summary[(summary["map"] == map_name) & (summary["side"] == side)].sort_values("score", ascending=False)
    remaining = pool[~pool["tactic_name"].isin(recs["tactic_name"])]
    near_miss = remaining.head(4)
    drop_candidates = remaining[remaining["win_rate"] < 42].head(4)
    tentative = remaining[(remaining["uses"] < min_sample) & (remaining["win_rate"] >= 55)].head(4)

    if include_tentative and (not near_miss.empty or not tentative.empty or not drop_candidates.empty):
        section_header("Supporting Buckets", "Secondary compact sections")
        x1, x2, x3 = st.columns(3, gap="small")
        with x1:
            st.markdown("#### Near Misses")
            st.dataframe(near_miss[["tactic_name", "score", "win_rate", "uses"]], use_container_width=True, hide_index=True)
        with x2:
            st.markdown("#### Tentative Picks")
            st.dataframe(tentative[["tactic_name", "score", "win_rate", "uses"]], use_container_width=True, hide_index=True)
        with x3:
            st.markdown("#### Drop Candidates")
            st.dataframe(drop_candidates[["tactic_name", "score", "win_rate", "uses"]], use_container_width=True, hide_index=True)
