import streamlit as st

from app.components import data_section_shell, insight_card, section_header, style_refresh_note, trend_chip
from app.filters import filter_panel_toggle
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

    style_refresh_note()
    section_header("Tactical Set Recommendations", "Context-locked recommendation engine")

    map_options = sorted(summary["map"].dropna().unique().tolist())
    side_options = sorted(summary["side"].dropna().unique().tolist())
    defaults = {
        "tactic_reco_map": map_options[0],
        "tactic_reco_side": side_options[0],
        "tactic_reco_min_sample": 5,
        "tactic_reco_confidence_floor": 55,
        "tactic_reco_include_tentative": True,
        "tactic_reco_strict_mode": False,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default
    if st.session_state.get("tactic_reco_map") not in map_options:
        st.session_state["tactic_reco_map"] = map_options[0]
    if st.session_state.get("tactic_reco_side") not in side_options:
        st.session_state["tactic_reco_side"] = side_options[0]

    if filter_panel_toggle("tactic_recommendations"):
        st.markdown("<div class='toolbar-shell'>", unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5, gap="small")
        with c1:
            season_hint = (filters.get("season") or ["Current"])[0]
            st.caption(f"Season: {season_hint}")
        with c2:
            st.selectbox("Map", map_options, key="tactic_reco_map")
        with c3:
            st.selectbox("Side", side_options, key="tactic_reco_side")
        with c4:
            st.slider("Min sample", 1, 20, key="tactic_reco_min_sample")
        with c5:
            st.slider("Confidence floor", 40, 85, key="tactic_reco_confidence_floor")

        t1, t2 = st.columns(2, gap="small")
        with t1:
            st.toggle("Include tentative", key="tactic_reco_include_tentative")
        with t2:
            st.toggle("Strict confidence", key="tactic_reco_strict_mode")
        st.markdown("</div>", unsafe_allow_html=True)

    map_name = st.session_state.get("tactic_reco_map", map_options[0])
    side = st.session_state.get("tactic_reco_side", side_options[0])
    min_sample = int(st.session_state.get("tactic_reco_min_sample", 5))
    confidence_floor = int(st.session_state.get("tactic_reco_confidence_floor", 55))
    include_tentative = bool(st.session_state.get("tactic_reco_include_tentative", True))
    strict_mode = bool(st.session_state.get("tactic_reco_strict_mode", False))

    recs = recommend_set(summary, map_name, side)
    recs = recs[recs["uses"] >= min_sample]
    threshold = confidence_floor + (8 if strict_mode else 0)
    recs = recs[recs["score"] >= threshold]

    if recs.empty:
        st.info("No candidates for this context and confidence floor yet.")
        return

    data_section_shell("Recommendation Summary Band", "High-level recommendation mix for this context", tone="good")
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

    data_section_shell("Legend", "Score and confidence keys used across recommendations", tone="mid")
    st.markdown(
        "<div class='panel panel-tight'><span class='chip chip-good'>High</span><span class='chip chip-mid'>Medium</span><span class='chip chip-poor'>Low</span>"
        "<div class='muted'>Cards emphasize score, win rate, usage volume, and trend chips for quick scan.</div></div>",
        unsafe_allow_html=True,
    )

    data_section_shell("Tactic Cards", "Primary recommendation surface", tone="mid")
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
        data_section_shell("Supporting Buckets", "Secondary compact sections", tone="poor")
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
