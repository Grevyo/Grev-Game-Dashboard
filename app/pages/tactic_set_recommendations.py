import numpy as np
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

from app.page_layout import is_mobile_view
from app.tactics import tactic_category


TIER_WEIGHTS = {"S": 1.35, "A": 1.15, "B": 1.0, "C": 0.72}
STATUS_ORDER = [
    "Locked In",
    "Strong Pick",
    "Viable",
    "Situational",
    "Test More",
    "Backup",
    "Exclude For Now",
]
STATUS_TONE = {
    "Locked In": "good",
    "Strong Pick": "good",
    "Viable": "mid",
    "Situational": "mid",
    "Test More": "poor",
    "Backup": "poor",
    "Exclude For Now": "bad",
}


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _fmt_signed(value: float) -> str:
    return f"{float(value):+.1f}pp"


def _safe_tier_col(df: pd.DataFrame) -> str | None:
    for col in ["tier", "opponent_tier", "Unnamed: 13", ""]:
        if col in df.columns:
            return col
    return None


def _route_role(name: str) -> str:
    n = str(name).upper()
    if "PISTOL" in n or "(P)" in n or n.startswith("P"):
        return "Pistol"
    if "ECO" in n or "(E)" in n or n.startswith("E"):
        if "A" in n:
            return "Eco A"
        if "B" in n:
            return "Eco B"
        return "Eco"
    if "IVY" in n:
        return "Ivy Lane"
    if "MID" in n:
        return "Mid Lane"
    if "A" in n and "B" in n:
        return "Split/Hybrid"
    if "A" in n:
        return "Standard A"
    if "B" in n:
        return "Standard B"
    return "Standard"


def _role_priority(role: str) -> int:
    order = {
        "Pistol": 0,
        "Eco A": 1,
        "Eco B": 2,
        "Eco": 3,
        "Standard A": 4,
        "Standard B": 5,
        "Mid Lane": 6,
        "Ivy Lane": 7,
        "Split/Hybrid": 8,
        "Standard": 9,
    }
    return order.get(role, 50)


def _status_logic(row: pd.Series) -> tuple[str, str]:
    delta = float(row["delta_vs_baseline"])
    rounds = float(row["rounds"])
    recent_delta = float(row["recent_delta"])
    confidence = float(row["confidence"])
    s_wr = float(row.get("S", np.nan))
    weak_tier_inflation = row["win_rate"] - row["weighted_wr"]

    if rounds >= 16 and delta >= 8 and confidence >= 78 and recent_delta >= -1:
        return "Locked In", "Strong sample, positive edge vs baseline, and stable recent output in this exact map+side context."
    if rounds >= 11 and delta >= 4 and confidence >= 66:
        return "Strong Pick", "Consistently ahead of baseline with enough rounds to trust as an active set piece."
    if rounds >= 9 and delta >= 1 and confidence >= 56:
        return "Viable", "Playable option with credible return; include when matching prep priorities and opponent reads."
    if rounds < 8 and delta >= 2:
        return "Test More", "Promising signal but under-tested; schedule controlled reps before core inclusion."
    if rounds >= 8 and delta >= -1.5 and recent_delta < -5:
        return "Situational", "Historically useful but short-term form has cooled; keep for specific scenarios only."
    if weak_tier_inflation > 4.5 and (np.isnan(s_wr) or s_wr < row["win_rate"] - 10):
        return "Backup", "Output is inflated by lower-tier opposition; keep as reserve until stronger-tier proof improves."
    return "Exclude For Now", "Below baseline or unreliable evidence profile for this map+side; avoid in default call sheet."


def _build_views(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_cols = ["map", "side", "tactic_name", "category", "tactic_type", "role"]

    tactical = (
        base.groupby(group_cols, dropna=False)
        .agg(
            wins=("wins", "sum"),
            losses=("losses", "sum"),
            rounds=("total_rounds", "sum"),
            last_used=("match_ts", "max"),
        )
        .reset_index()
    )
    tactical["win_rate"] = (tactical["wins"] / (tactical["wins"] + tactical["losses"]).clip(lower=1) * 100).fillna(0)

    recent_cut = base["match_ts"].max() - pd.Timedelta(days=21)
    recent = (
        base[base["match_ts"] >= recent_cut]
        .groupby(group_cols, dropna=False)
        .agg(rwins=("wins", "sum"), rlosses=("losses", "sum"))
        .reset_index()
    )
    recent["recent_wr"] = (recent["rwins"] / (recent["rwins"] + recent["rlosses"]).clip(lower=1) * 100).fillna(0)

    tier = (
        base.groupby(group_cols + ["tier"], dropna=False)
        .agg(twins=("wins", "sum"), tlosses=("losses", "sum"))
        .reset_index()
    )
    tier["tier_wr"] = (tier["twins"] / (tier["twins"] + tier["tlosses"]).clip(lower=1) * 100).fillna(0)
    tier_pivot = tier.pivot_table(index=group_cols, columns="tier", values="tier_wr", aggfunc="mean").reset_index()
    for t in ["S", "A", "B", "C"]:
        if t not in tier_pivot.columns:
            tier_pivot[t] = np.nan

    tactical = tactical.merge(recent[group_cols + ["recent_wr"]], on=group_cols, how="left").merge(
        tier_pivot[group_cols + ["S", "A", "B", "C"]], on=group_cols, how="left"
    )

    weighted_num = sum(tactical[t].fillna(tactical["win_rate"]) * w for t, w in TIER_WEIGHTS.items())
    tactical["weighted_wr"] = weighted_num / sum(TIER_WEIGHTS.values())

    baseline = (
        base.groupby(["map", "side"], dropna=False)
        .agg(base_wins=("wins", "sum"), base_losses=("losses", "sum"), base_rounds=("total_rounds", "sum"))
        .reset_index()
    )
    baseline["baseline_wr"] = (baseline["base_wins"] / (baseline["base_wins"] + baseline["base_losses"]).clip(lower=1) * 100).fillna(0)

    tactical = tactical.merge(baseline[["map", "side", "baseline_wr", "base_rounds"]], on=["map", "side"], how="left")
    tactical["recent_wr"] = tactical["recent_wr"].fillna(tactical["win_rate"])
    tactical["recent_delta"] = tactical["recent_wr"] - tactical["win_rate"]
    tactical["delta_vs_baseline"] = tactical["win_rate"] - tactical["baseline_wr"]
    tactical["sample_strength"] = np.clip(np.sqrt(tactical["rounds"].clip(lower=1)) * 20, 15, 100)
    tactical["confidence"] = (
        tactical["sample_strength"] * 0.55
        + np.clip(tactical["delta_vs_baseline"] + 10, 0, 25) * 1.35
        + np.clip(tactical["weighted_wr"] - 45, 0, 35) * 0.65
    ).clip(20, 99)
    tactical["trust_label"] = np.where(
        tactical["confidence"] >= 78,
        "Trusted",
        np.where(tactical["confidence"] >= 62, "Playable", "Fragile"),
    )
    tactical["last_used_label"] = tactical["last_used"].dt.strftime("%Y-%m-%d").fillna("N/A")
    tactical["status"], tactical["status_note"] = zip(*tactical.apply(_status_logic, axis=1))
    tactical["recommendation_score"] = (
        tactical["delta_vs_baseline"] * 3.0
        + tactical["weighted_wr"] * 0.6
        + tactical["confidence"] * 0.45
        + tactical["rounds"].clip(upper=20) * 0.85
    )
    return tactical, baseline


def _select_recommended_set(pool: pd.DataFrame, max_picks: int = 7) -> pd.DataFrame:
    if pool.empty:
        return pool

    candidates = pool.sort_values(["recommendation_score", "confidence", "rounds"], ascending=False).copy()
    selected_idx = []
    role_counts: dict[str, int] = {}

    required_roles = ["Pistol", "Eco A", "Eco B", "Standard A", "Standard B"]
    for role in required_roles:
        role_rows = candidates[candidates["role"] == role]
        if role_rows.empty:
            continue
        idx = int(role_rows.index[0])
        if idx not in selected_idx:
            selected_idx.append(idx)
            role_counts[role] = role_counts.get(role, 0) + 1

    lane_roles = ["Mid Lane", "Ivy Lane"]
    for lane in lane_roles:
        lane_rows = candidates[candidates["role"] == lane]
        if lane_rows.empty or len(selected_idx) >= max_picks:
            continue
        idx = int(lane_rows.index[0])
        if idx not in selected_idx:
            selected_idx.append(idx)
            role_counts[lane] = role_counts.get(lane, 0) + 1

    for idx, row in candidates.iterrows():
        if len(selected_idx) >= max_picks:
            break
        if int(idx) in selected_idx:
            continue
        role = str(row["role"])
        if role_counts.get(role, 0) >= 2:
            continue
        selected_idx.append(int(idx))
        role_counts[role] = role_counts.get(role, 0) + 1

    out = candidates.loc[selected_idx].copy()
    return out.sort_values(["role"], key=lambda s: s.map(_role_priority))


def _inject_page_css() -> None:
    st.markdown(
        """
        <style>
        .reco-hero-title{font-size:1.24rem;margin:0;color:#f5fbff;letter-spacing:.02em;}
        .reco-hero-sub{margin:.3rem 0 0;font-size:.82rem;color:#9fb0c4;max-width:980px;}
        .briefing-strip{padding:.72rem;margin-top:.65rem;}
        .brief-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.45rem;}
        .brief-cell{border:1px solid #2f4256;background:#101d2a;border-radius:6px;padding:.45rem .52rem;}
        .brief-label{font-size:.58rem;letter-spacing:.11em;text-transform:uppercase;color:#91a7bc;}
        .brief-value{margin-top:2px;font-size:.8rem;color:#edf4ff;font-weight:700;}
        .set-board{border:1px solid #3a4f64;background:linear-gradient(180deg,#132232,#0e1a27);border-radius:10px;padding:.68rem;}
        .reco-tile{border:1px solid #314659;background:linear-gradient(180deg,#152535,#0f1b29);border-radius:8px;padding:.56rem;min-height:200px;}
        .reco-name{margin:0;color:#f3f9ff;font-size:.86rem;line-height:1.2;font-weight:760;}
        .reco-role{font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;color:#9cb1c7;margin-top:2px;}
        .status-pill{display:inline-block;font-size:.56rem;letter-spacing:.11em;text-transform:uppercase;padding:2px 7px;border-radius:999px;border:1px solid #42596f;margin-top:6px;}
        .status-pill.good{color:#9FE870;border-color:#4a7242;background:#1a2b1b;}
        .status-pill.mid{color:#d3a85c;border-color:#78603b;background:#2a2418;}
        .status-pill.poor{color:#ff9f43;border-color:#865830;background:#2a1f14;}
        .status-pill.bad{color:#ff4d5e;border-color:#7a3540;background:#2a171d;}
        .mini-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.35rem;margin-top:8px;}
        .mini-cell{border:1px solid #2b3c4f;background:#0f1925;border-radius:5px;padding:.34rem;}
        .mini-l{font-size:.54rem;letter-spacing:.1em;text-transform:uppercase;color:#8ea4b8;}
        .mini-v{font-size:.72rem;color:#ebf4ff;font-weight:700;}
        .coverage-row{display:grid;grid-template-columns:minmax(140px,190px) 1fr auto;gap:10px;align-items:center;padding:.38rem 0;border-bottom:1px solid #223244;}
        .coverage-row:last-child{border-bottom:0;}
        .coverage-track{height:10px;border-radius:999px;background:#111c29;border:1px solid #2d4154;position:relative;overflow:hidden;}
        .coverage-fill{height:100%;background:linear-gradient(90deg,#76b95c,#9FE870);}        
        .decision-col h4{margin:0 0 8px 0;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:#9ab0c6;}
        .decision-item{border:1px solid #2a3d50;background:#101c2a;border-radius:6px;padding:.44rem .48rem;margin-bottom:7px;}
        .decision-item strong{display:block;color:#e9f2ff;font-size:.76rem;}
        .decision-item span{font-size:.65rem;color:#95a9be;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render(ctx):
    tdf = ctx["tactics"].copy()
    mobile_view = is_mobile_view()

    if tdf.empty:
        st.warning("No tactics data after current global filters.")
        return

    _inject_page_css()

    tdf["map"] = tdf.get("map", "Unknown").astype(str).str.strip().replace("", "Unknown")
    tdf["side"] = tdf.get("side", "Unknown").astype(str).str.strip().replace("", "Unknown")
    tdf["tactic_name"] = tdf.get("tactic_name", "Unknown Tactic").astype(str).str.strip().replace("", "Unknown Tactic")
    tdf["wins"] = pd.to_numeric(tdf.get("wins", 0), errors="coerce").fillna(0)
    tdf["losses"] = pd.to_numeric(tdf.get("losses", 0), errors="coerce").fillna(0)
    tdf["total_rounds"] = pd.to_numeric(tdf.get("total_rounds", 0), errors="coerce").fillna(0)
    tdf["category"] = tdf["tactic_name"].map(tactic_category)
    tdf["tactic_type"] = tdf["category"].replace({"Standard": "Standard", "Eco": "Eco", "Pistol": "Pistol"})
    tdf["role"] = tdf["tactic_name"].map(_route_role)

    tier_col = _safe_tier_col(tdf)
    tdf["tier"] = tdf[tier_col].astype(str).str.upper().str.strip() if tier_col else "C"
    tdf["tier"] = tdf["tier"].where(tdf["tier"].isin(["S", "A", "B", "C"]), "C")

    date_ser = tdf.get("date", pd.Series([None] * len(tdf)))
    time_ser = tdf.get("time", pd.Series([""] * len(tdf))).astype(str)
    tdf["match_ts"] = pd.to_datetime(date_ser.astype(str) + " " + time_ser, errors="coerce")
    tdf["match_ts"] = tdf["match_ts"].fillna(pd.Timestamp("1970-01-01"))

    map_options = sorted(tdf["map"].dropna().unique().tolist())
    side_options = sorted(tdf["side"].dropna().unique().tolist())
    active_map = st.session_state.get("tb_map")
    active_side = st.session_state.get("tb_side")
    map_name = active_map if active_map in map_options else map_options[0]
    side = active_side if active_side in side_options else side_options[0]

    scoped = tdf[(tdf["map"] == map_name) & (tdf["side"] == side)].copy()
    if scoped.empty:
        st.warning("No map+side tactics available for the active global context.")
        return

    tactical, baseline = _build_views(scoped)
    if tactical.empty:
        st.warning("No tactical profile could be built for the active map+side context.")
        return

    tactical = tactical.sort_values(["recommendation_score", "confidence", "rounds"], ascending=False).copy()
    rec_set = _select_recommended_set(tactical, max_picks=7)

    st.markdown(
        f"""
        <div class='hero-band'>
            <div class='section-title'>Coach Selection Layer</div>
            <h1 class='reco-hero-title'>Tactical Set Recommendation</h1>
            <p class='reco-hero-sub'>
                Final map-side decision dashboard: lock core calls, expose borderline options, and validate trust before committing to the run sheet.
            </p>
            <div style='margin-top:6px;'>
                <span class='chip chip-good'>{map_name}</span>
                <span class='chip chip-mid'>{side}</span>
                <span class='chip'>{int(scoped['total_rounds'].sum())} context rounds</span>
                <span class='chip chip-poor'>{tactical['tactic_name'].nunique()} tactics in pool</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    global_filters = ctx.get("filters", {})
    comp = global_filters.get("competition") or ["All Competitions"]
    season = global_filters.get("season") or ["All Seasons"]
    newest = scoped["match_ts"].max().strftime("%Y-%m-%d")
    st.markdown(
        f"""
        <div class='panel briefing-strip'>
          <div class='section-title'>Decision Context Strip</div>
          <div class='brief-grid'>
            <div class='brief-cell'><div class='brief-label'>Active Map</div><div class='brief-value'>{map_name}</div></div>
            <div class='brief-cell'><div class='brief-label'>Active Side</div><div class='brief-value'>{side}</div></div>
            <div class='brief-cell'><div class='brief-label'>Competition Context</div><div class='brief-value'>{", ".join(map(str, comp[:2]))}{"…" if len(comp) > 2 else ""}</div></div>
            <div class='brief-cell'><div class='brief-label'>Season / Last Data</div><div class='brief-value'>{season[0]} • {newest}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='set-board'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Recommended Set (6–7 Tactical Calls)</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='section-subtitle'>Primary answer for <strong>{map_name} • {side}</strong>. Selections are never transferred across other map-side contexts.</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3 if not mobile_view else 1, gap="small")
    for i, (_, row) in enumerate(rec_set.iterrows()):
        tone = STATUS_TONE.get(str(row["status"]), "mid")
        col = cols[i % len(cols)]
        with col:
            st.markdown(
                f"""
                <div class='reco-tile'>
                  <h4 class='reco-name'>{row['tactic_name']}</h4>
                  <div class='reco-role'>{row['role']} • {row['tactic_type']}</div>
                  <span class='status-pill {tone}'>{row['status']}</span>
                  <div class='mini-grid'>
                    <div class='mini-cell'><div class='mini-l'>Win Rate</div><div class='mini-v'>{_fmt_pct(row['win_rate'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Δ Baseline</div><div class='mini-v'>{_fmt_signed(row['delta_vs_baseline'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Rounds</div><div class='mini-v'>{int(row['rounds'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Recent</div><div class='mini-v'>{_fmt_pct(row['recent_wr'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Confidence</div><div class='mini-v'>{int(row['confidence'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Last Used</div><div class='mini-v'>{row['last_used_label']}</div></div>
                  </div>
                  <div class='muted' style='margin-top:8px;'>{row['status_note']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

    coverage_roles = ["Pistol", "Eco A", "Eco B", "Standard A", "Standard B", "Mid Lane", "Ivy Lane"]
    coverage_df = pd.DataFrame({"role": coverage_roles})
    counts = rec_set.groupby("role")["tactic_name"].count().to_dict()
    coverage_df["count"] = coverage_df["role"].map(counts).fillna(0).astype(int)
    coverage_df["target"] = coverage_df["role"].apply(lambda r: 1 if r in coverage_roles[:5] else 0)
    coverage_df["complete"] = coverage_df["count"] >= coverage_df["target"]

    st.markdown("<div class='panel'><div class='section-title'>Coverage & Completeness Board</div>", unsafe_allow_html=True)
    for _, row in coverage_df.iterrows():
        fill = min(100, row["count"] * 100)
        badge = "Covered" if row["count"] > 0 else "Missing"
        st.markdown(
            f"""
            <div class='coverage-row'>
              <div class='brief-label'>{row['role']}</div>
              <div class='coverage-track'><div class='coverage-fill' style='width:{fill}%;'></div></div>
              <div><span class='chip {'chip-good' if badge == 'Covered' else 'chip-bad'}'>{badge}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    included = tactical[tactical["tactic_name"].isin(rec_set["tactic_name"])].copy()
    borderline = tactical[tactical["status"].isin(["Viable", "Situational", "Test More"]) & ~tactical["tactic_name"].isin(rec_set["tactic_name"])].head(8)
    excluded = tactical[tactical["status"].isin(["Backup", "Exclude For Now"])].head(8)

    d1, d2, d3 = st.columns(3, gap="small")
    for col, title, frame in [
        (d1, "Included in Recommended Set", included),
        (d2, "Borderline / Rotational", borderline),
        (d3, "Excluded For Now", excluded),
    ]:
        with col:
            st.markdown(f"<div class='panel decision-col'><h4>{title}</h4>", unsafe_allow_html=True)
            if frame.empty:
                st.markdown("<div class='muted'>No tactics in this bucket for the active context.</div>", unsafe_allow_html=True)
            else:
                for _, r in frame.iterrows():
                    st.markdown(
                        f"<div class='decision-item'><strong>{r['tactic_name']}</strong>"
                        f"<span>{r['role']} • {_fmt_pct(r['win_rate'])} • {_fmt_signed(r['delta_vs_baseline'])} • conf {int(r['confidence'])}</span></div>",
                        unsafe_allow_html=True,
                    )
            st.markdown("</div>", unsafe_allow_html=True)

    if PLOTLY_AVAILABLE:
        v1, v2 = st.columns([1.1, 1], gap="small")
        with v1:
            st.markdown("<div class='analytics-frame'><div class='section-title'>Recommendation Score vs Confidence</div></div>", unsafe_allow_html=True)
            scatter = px.scatter(
                tactical,
                x="recommendation_score",
                y="confidence",
                size="rounds",
                color="status",
                hover_name="tactic_name",
                hover_data={"delta_vs_baseline": ":.1f", "recent_wr": ":.1f", "S": ":.1f", "A": ":.1f", "B": ":.1f", "C": ":.1f"},
                color_discrete_map={
                    "Locked In": "#9FE870",
                    "Strong Pick": "#70d384",
                    "Viable": "#d3a85c",
                    "Situational": "#c79555",
                    "Test More": "#ff9f43",
                    "Backup": "#ff7a4d",
                    "Exclude For Now": "#ff4d5e",
                },
            )
            scatter.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=10, b=8), height=360 if not mobile_view else 320)
            st.plotly_chart(scatter, use_container_width=True)

        with v2:
            st.markdown("<div class='analytics-frame'><div class='section-title'>Role Coverage Distribution</div></div>", unsafe_allow_html=True)
            role_counts = rec_set.groupby("role")["tactic_name"].count().reset_index(name="count")
            role_bar = px.bar(role_counts, x="role", y="count", color="count", color_continuous_scale=["#1f3346", "#9FE870"])
            role_bar.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=10, b=8), height=360 if not mobile_view else 320)
            st.plotly_chart(role_bar, use_container_width=True)

    shortlist = tactical.copy()
    shortlist["Included?"] = shortlist["tactic_name"].isin(rec_set["tactic_name"]).map({True: "Yes", False: "No"})
    shortlist = shortlist[
        [
            "tactic_name",
            "tactic_type",
            "map",
            "side",
            "rounds",
            "win_rate",
            "delta_vs_baseline",
            "recent_wr",
            "last_used_label",
            "S",
            "A",
            "B",
            "C",
            "confidence",
            "status",
            "role",
            "Included?",
        ]
    ].rename(
        columns={
            "tactic_name": "Tactic",
            "tactic_type": "Type",
            "map": "Map",
            "side": "Side",
            "rounds": "Rounds",
            "win_rate": "Win Rate",
            "delta_vs_baseline": "Delta vs Baseline",
            "recent_wr": "Recent WR",
            "last_used_label": "Last Used",
            "confidence": "Confidence",
            "status": "Recommendation Status",
            "role": "Set Role",
        }
    )

    st.markdown("<div class='panel'><div class='section-title'>Premium Recommendation Shortlist</div>", unsafe_allow_html=True)
    st.dataframe(
        shortlist,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Win Rate": st.column_config.NumberColumn(format="%.1f%%"),
            "Delta vs Baseline": st.column_config.NumberColumn(format="%+.1f pp"),
            "Recent WR": st.column_config.NumberColumn(format="%.1f%%"),
            "S": st.column_config.NumberColumn(format="%.1f%%"),
            "A": st.column_config.NumberColumn(format="%.1f%%"),
            "B": st.column_config.NumberColumn(format="%.1f%%"),
            "C": st.column_config.NumberColumn(format="%.1f%%"),
            "Confidence": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel'><div class='section-title'>Deep-Dive Decision Analysis</div>", unsafe_allow_html=True)
    focus_name = st.selectbox("Inspect tactic", options=tactical["tactic_name"].tolist(), index=0)
    focus = tactical[tactical["tactic_name"] == focus_name].iloc[0]

    f1, f2, f3 = st.columns(3, gap="small")
    with f1:
        st.markdown(f"<div class='stat-item'><div class='label'>Recommendation Status</div><div class='metric-value' style='font-size:1.1rem'>{focus['status']}</div><div class='muted'>{focus['status_note']}</div></div>", unsafe_allow_html=True)
    with f2:
        tier_note = (
            f"S-tier {_fmt_pct(focus['S']) if pd.notna(focus['S']) else 'N/A'}, "
            f"A-tier {_fmt_pct(focus['A']) if pd.notna(focus['A']) else 'N/A'}, "
            f"B-tier {_fmt_pct(focus['B']) if pd.notna(focus['B']) else 'N/A'}, "
            f"C-tier {_fmt_pct(focus['C']) if pd.notna(focus['C']) else 'N/A'}."
        )
        st.markdown(
            f"<div class='stat-item'><div class='label'>Tier-Split Evidence</div><div class='metric-value' style='font-size:1.1rem'>{_fmt_pct(focus['weighted_wr'])}</div><div class='muted'>{tier_note}</div></div>",
            unsafe_allow_html=True,
        )
    with f3:
        overlap = rec_set[rec_set["role"] == focus["role"]]["tactic_name"].tolist()
        overlap_note = "No role overlap in set." if len(overlap) <= 1 else f"Role overlap with: {', '.join([n for n in overlap if n != focus_name][:2])}."
        st.markdown(
            f"<div class='stat-item'><div class='label'>Role Fit & Overlap</div><div class='metric-value' style='font-size:1.1rem'>{focus['role']}</div><div class='muted'>{overlap_note}</div></div>",
            unsafe_allow_html=True,
        )

    trust_comment = (
        "Trusted due to strong sample and stable edge."
        if focus["trust_label"] == "Trusted"
        else "Promising but not fully proven; treat as controlled option."
        if focus["trust_label"] == "Playable"
        else "High uncertainty profile; avoid core reliance without more evidence."
    )
    st.markdown(
        f"<div class='muted' style='margin-top:10px;'>"
        f"Decision context: <strong>{map_name} • {side}</strong>. "
        f"Baseline {_fmt_pct(float(baseline['baseline_wr'].iloc[0]))}; this tactic posts {_fmt_pct(focus['win_rate'])} ({_fmt_signed(focus['delta_vs_baseline'])}). "
        f"Recent form {_fmt_pct(focus['recent_wr'])}, confidence {int(focus['confidence'])}/100, last used {focus['last_used_label']}. {trust_comment}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
