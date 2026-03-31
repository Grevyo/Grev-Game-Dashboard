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


TIER_WEIGHTS = {"S": 1.35, "A": 1.15, "B": 1.0, "C": 0.75}
STATUS_COLORS = {
    "Strong Keep": "good",
    "Keep": "good",
    "Refine": "mid",
    "Test More": "poor",
    "Situational": "mid",
    "Risky": "poor",
    "Drop": "bad",
}
TIER_COLOR_CLASS = {"S": "grev-tier-s", "A": "grev-tier-a", "B": "grev-tier-b", "C": "grev-tier-c"}
STATUS_PRIORITY = ["Strong Keep", "Keep", "Refine", "Test More", "Situational", "Risky", "Drop"]


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _fmt_signed(value: float) -> str:
    return f"{float(value):+.1f}pp"


def _safe_tier_col(df: pd.DataFrame) -> str | None:
    preferred_cols = ["tier", "opponent_tier", "unnamed:_13", "unnamed: 13", "unnamed_13", "Unnamed: 13", ""]
    normalized_map = {str(col).strip().lower(): col for col in df.columns}
    for key in preferred_cols:
        col = normalized_map.get(str(key).strip().lower())
        if col is not None:
            return col
    return None


def _normalize_tier_values(series: pd.Series) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip().str.upper()
    extracted = cleaned.str.extract(r"\b([SABC])(?:-?TIER)?\b", expand=False)
    fallback = cleaned.str.extract(r"([SABC])", expand=False)
    normalized = extracted.fillna(fallback)
    return normalized.where(normalized.isin(["S", "A", "B", "C"]), pd.NA)


def _route_bucket(name: str) -> str:
    n = str(name).upper()
    if "PISTOL" in n or "(P)" in n or n.startswith("P"):
        return "Pistol"
    if "ECO" in n or "(E)" in n or n.startswith("E"):
        if "A" in n:
            return "Eco A"
        if "B" in n:
            return "Eco B"
        return "Eco"
    if "MID" in n:
        return "Mid"
    if "IVY" in n:
        return "Ivy"
    if "A" in n:
        return "Standard A"
    if "B" in n:
        return "Standard B"
    return "Standard"


def _status_logic(row: pd.Series) -> tuple[str, str]:
    delta = row["delta_vs_baseline"]
    recent_delta = row["recent_delta"]
    rounds = row["rounds"]
    weighted = row["weighted_wr"]

    if rounds >= 14 and delta >= 9 and recent_delta >= 0 and weighted >= row["win_rate"] - 2:
        return "Strong Keep", "Reliable edge over baseline with stable recent confirmation in this map+side context."
    if rounds >= 10 and delta >= 5:
        return "Keep", "Beating context baseline on meaningful sample; maintain in active prep set."
    if rounds >= 8 and delta >= 0 and recent_delta < -6:
        return "Refine", "Long-run edge exists but recent form is dropping; adjust utility pathing and timings."
    if rounds < 8 and delta >= 2:
        return "Test More", "Promising output but sample is too thin for confident locking."
    if rounds >= 8 and delta < -8:
        return "Drop", "Consistently below map+side baseline; remove from default pool unless specific read appears."
    if rounds >= 8 and delta < -3:
        return "Risky", "Under baseline with enough usage to create downside pressure in this context."
    return "Situational", "Context-dependent outcome profile; keep as conditional call rather than default."


def _compose_reason(row: pd.Series) -> str:
    delta = float(row["delta_vs_baseline"])
    rounds = int(row["rounds"])
    recent_delta = float(row["recent_delta"])
    weighted = float(row["weighted_wr"])
    win_rate = float(row["win_rate"])
    days_since = int(row["days_since_used"])
    status = str(row["status"])

    if status == "Strong Keep":
        return "Above map-side baseline on strong sample with stable recent confirmation."
    if status == "Keep":
        if weighted >= win_rate:
            return "Reliable edge and tier-weighted quality support keeping it in the core set."
        return "Above baseline with proven sample; remains a dependable primary option."
    if status == "Refine":
        return "Long-run return is positive, but recent results softened and need tactical refinement."
    if status == "Test More":
        return "Early return is promising, but low sample still limits confidence."
    if status == "Risky":
        if rounds >= 12:
            return "Usage is meaningful, yet performance sits below baseline and increases downside risk."
        return "Below-baseline trend with unstable outcomes; use only as conditional counter-look."
    if status == "Drop":
        return "Sustained underperformance versus baseline with enough evidence to de-prioritize."
    if recent_delta >= 4:
        return "Recent form is improving, but role remains situational versus core calls."
    if days_since > 21:
        return "Not used recently and evidence is mixed; retain only for niche game-state reads."
    return "Stable mid-band option for selective situations, but not a default call."


def _wr_tier_box(tier: str, value: float | None) -> str:
    display = _fmt_pct(value) if pd.notna(value) else "N/A"
    tier_key = str(tier).strip().upper()
    tier_class = TIER_COLOR_CLASS.get(tier_key, "grev-tier-c")
    return (
        f"<div class='grev-tier-box {tier_class} wr-tier-box'>"
        f"<span class='tier-name'>vs {tier_key}</span>"
        f"<span class='tier-score'>{display}</span>"
        "</div>"
    )


def _build_tactic_views(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_cols = ["map", "side", "tactic_name", "category", "tactic_type"]
    tactical = (
        base.groupby(group_cols, dropna=False)
        .agg(
            wins=("wins", "sum"),
            losses=("losses", "sum"),
            rounds=("total_rounds", "sum"),
            last_used=("match_ts", "max"),
            first_used=("match_ts", "min"),
        )
        .reset_index()
    )
    tactical["win_rate"] = (tactical["wins"] / (tactical["wins"] + tactical["losses"]).clip(lower=1) * 100).fillna(0)

    recent_cut = base["match_ts"].max() - pd.Timedelta(days=14)
    recent = (
        base[base["match_ts"] >= recent_cut]
        .groupby(group_cols, dropna=False)
        .agg(rwins=("wins", "sum"), rlosses=("losses", "sum"), rrounds=("total_rounds", "sum"))
        .reset_index()
    )
    recent["recent_wr"] = (recent["rwins"] / (recent["rwins"] + recent["rlosses"]).clip(lower=1) * 100).fillna(0)

    tier_view = (
        base.groupby(group_cols + ["tier"], dropna=False)
        .agg(twins=("wins", "sum"), tlosses=("losses", "sum"))
        .reset_index()
    )
    tier_view["tier_wr"] = (tier_view["twins"] / (tier_view["twins"] + tier_view["tlosses"]).clip(lower=1) * 100).fillna(0)

    tier_pivot = tier_view.pivot_table(index=group_cols, columns="tier", values="tier_wr", aggfunc="mean").reset_index()
    for t in ["S", "A", "B", "C"]:
        if t not in tier_pivot.columns:
            tier_pivot[t] = np.nan

    tactical = tactical.merge(recent[group_cols + ["recent_wr", "rrounds"]], on=group_cols, how="left").merge(
        tier_pivot[group_cols + ["S", "A", "B", "C"]], on=group_cols, how="left"
    )

    weighted_num = sum(tactical[t].fillna(tactical["win_rate"]) * w for t, w in TIER_WEIGHTS.items())
    weighted_den = sum(TIER_WEIGHTS.values())
    tactical["weighted_wr"] = weighted_num / weighted_den

    baseline = (
        base.groupby(["map", "side"], dropna=False)
        .agg(base_wins=("wins", "sum"), base_losses=("losses", "sum"), base_rounds=("total_rounds", "sum"))
        .reset_index()
    )
    baseline["baseline_wr"] = (baseline["base_wins"] / (baseline["base_wins"] + baseline["base_losses"]).clip(lower=1) * 100).fillna(0)

    tactical = tactical.merge(baseline[["map", "side", "baseline_wr", "base_rounds"]], on=["map", "side"], how="left")
    tactical["delta_vs_baseline"] = tactical["win_rate"] - tactical["baseline_wr"]
    tactical["recent_wr"] = tactical["recent_wr"].fillna(tactical["win_rate"])
    tactical["recent_delta"] = tactical["recent_wr"] - tactical["win_rate"]
    tactical["volatility"] = tactical["recent_delta"].abs()
    tactical["last_used_label"] = tactical["last_used"].dt.strftime("%Y-%m-%d").fillna("N/A")
    tactical["days_since_used"] = (base["match_ts"].max() - tactical["last_used"]).dt.days.fillna(999)
    tactical["status"], tactical["analyst_note"] = zip(*tactical.apply(_status_logic, axis=1))
    tactical["coverage"] = tactical["tactic_name"].map(_route_bucket)

    return tactical, baseline


def _inject_page_css() -> None:
    st.markdown(
        """
        <style>
        .tactics-hero-title{font-size:1.22rem;margin:0;color:#f5fbff;letter-spacing:.02em;}
        .tactics-hero-subtitle{margin:.3rem 0 0;font-size:.82rem;color:#9fb0c4;max-width:920px;}
        .tactics-command{padding:.7rem;margin-top:.6rem;}
        .context-chip{display:inline-block;border:1px solid #3f556d;background:#112132;padding:4px 10px;border-radius:4px;font-size:.62rem;letter-spacing:.11em;text-transform:uppercase;color:#cfe1f5;margin-right:6px;}
        .context-chip strong{color:#9FE870;}
        .tactic-card{border:1px solid #2d3e51;background:linear-gradient(180deg,#122031,#0d1825);border-radius:8px;padding:.62rem;min-height:196px;}
        .tactic-card h4{margin:0;color:#f4f8ff;font-size:.87rem;line-height:1.25;}
        .status-pill{display:inline-block;font-size:.56rem;letter-spacing:.11em;text-transform:uppercase;padding:2px 7px;border-radius:999px;border:1px solid #42596f;margin-top:6px;}
        .status-pill.good{color:#9FE870;border-color:#4a7242;background:#1a2b1b;}
        .status-pill.mid{color:#d3a85c;border-color:#78603b;background:#2a2418;}
        .status-pill.poor{color:#ff9f43;border-color:#865830;background:#2a1f14;}
        .status-pill.bad{color:#ff4d5e;border-color:#7a3540;background:#2a171d;}
        .tactic-mini{font-size:.64rem;color:#94a6bb;margin-top:4px;}
        .recommend-slot{border:1px solid #34485f;border-radius:7px;background:#101c2a;padding:.55rem;}
        .tier-filter-wrap{display:flex;align-items:center;justify-content:flex-end;}
        .status-group{margin-top:12px;border:1px solid #2f4155;border-radius:10px;background:linear-gradient(180deg,#101a27,#0c1521);padding:.7rem;}
        .status-group-header{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;}
        .status-group h3{margin:0;font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:#d6e3f2;}
        .status-group-meta{font-size:.64rem;color:#95a8bc;}
        .tactic-card .grev-tier-row{margin-top:7px;grid-template-columns:repeat(4,minmax(0,1fr));}
        .wr-tier-box{min-height:54px;padding:6px 5px;}
        .tactic-reason{margin-top:8px;font-size:.68rem;color:#d2deea;line-height:1.35;}
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
    tdf["category"] = tdf["tactic_name"].map(tactic_category)
    tdf["tactic_type"] = tdf["category"].replace({"Standard": "Standard", "Eco": "Eco", "Pistol": "Pistol"})
    tdf["wins"] = pd.to_numeric(tdf.get("wins", 0), errors="coerce").fillna(0)
    tdf["losses"] = pd.to_numeric(tdf.get("losses", 0), errors="coerce").fillna(0)
    tdf["total_rounds"] = pd.to_numeric(tdf.get("total_rounds", 0), errors="coerce").fillna(0)
    tdf["competition"] = tdf.get("competition", "Unknown").astype(str).str.strip().replace("", "Unknown")

    tier_col = _safe_tier_col(tdf)
    if tier_col:
        tdf["tier"] = _normalize_tier_values(tdf[tier_col]).fillna("C")
    else:
        tdf["tier"] = "C"

    date_ser = tdf.get("date", pd.Series([None] * len(tdf)))
    time_ser = tdf.get("time", pd.Series([""] * len(tdf))).astype(str)
    tdf["match_ts"] = pd.to_datetime(date_ser.astype(str) + " " + time_ser, errors="coerce")
    tdf["match_ts"] = tdf["match_ts"].fillna(pd.Timestamp("1970-01-01"))

    st.markdown(
        f"""
        <div class='hero-band'>
            <div class='section-title'>Tactical Intelligence Surface</div>
            <h1 class='tactics-hero-title'>Tactics Breakdown</h1>
            <p class='tactics-hero-subtitle'>
                Analyst command centre for map-side specific tactical decisions: what to keep, what to refine, what to stress-test, and what to drop.
            </p>
            <div style='margin-top:6px;'>
                <span class='chip chip-good'>{tdf['tactic_name'].nunique()} tactics tracked</span>
                <span class='chip chip-mid'>{tdf['map'].nunique()} maps</span>
                <span class='chip chip-poor'>{tdf['side'].nunique()} sides</span>
                <span class='chip'>{int(tdf['total_rounds'].sum())} rounds</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    global_filters = ctx.get("filters", {})
    active_maps = global_filters.get("map") or []
    active_sides = global_filters.get("side") or []
    active_competitions = global_filters.get("competition") or []
    map_context = ", ".join(active_maps[:2]) + (f", +{len(active_maps) - 2} more" if len(active_maps) > 2 else "") if active_maps else "All Maps"
    side_context = ", ".join(active_sides[:2]) + (f", +{len(active_sides) - 2} more" if len(active_sides) > 2 else "") if active_sides else "All Sides"
    comp_context = (
        ", ".join(active_competitions[:2]) + (f", +{len(active_competitions) - 2} more" if len(active_competitions) > 2 else "")
        if active_competitions
        else "All Competitions"
    )

    st.markdown("<div class='panel tactics-command'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.1, 1.0, 1.0, 1.2], gap="small")
    with c1:
        tactic_type = st.segmented_control("Tactic Type", options=["All", "Standard", "Eco", "Pistol"], default="All")
    with c2:
        days_window = st.select_slider("Recent Window", options=[7, 10, 14, 21, 30], value=14)
    with c3:
        max_scope = tdf.copy()
        if tactic_type != "All":
            max_scope = max_scope[max_scope["tactic_type"] == tactic_type].copy()
        newest_scope = max_scope["match_ts"].max()
        max_scope = max_scope[max_scope["match_ts"] >= (newest_scope - pd.Timedelta(days=int(days_window) * 8))].copy()
        grouped_rounds = (
            max_scope.groupby(["map", "side", "tactic_name", "category", "tactic_type"], dropna=False)["total_rounds"].sum()
            if not max_scope.empty
            else pd.Series(dtype=float)
        )
        data_max_rounds = int(grouped_rounds.max()) if not grouped_rounds.empty else 1
        sample_floor_cap = max(100, data_max_rounds)
        sample_floor_step = 1 if sample_floor_cap <= 100 else 5 if sample_floor_cap <= 300 else 10
        sample_floor = st.number_input(
            "Min Rounds",
            min_value=1,
            max_value=sample_floor_cap,
            value=min(3, sample_floor_cap),
            step=sample_floor_step,
            help=f"Current scoped data max: {data_max_rounds} rounds.",
        )
    with c4:
        selected_tiers = st.multiselect("Opponent Tier", options=["S", "A", "B", "C"], default=["S", "A", "B", "C"])
    st.markdown("</div>", unsafe_allow_html=True)

    scoped = tdf.copy()
    if tactic_type != "All":
        scoped = scoped[scoped["tactic_type"] == tactic_type].copy()
    if selected_tiers:
        scoped = scoped[scoped["tier"].isin(selected_tiers)].copy()

    if scoped.empty:
        st.warning("No tactics remain for the current global filter context.")
        return

    newest = scoped["match_ts"].max()
    scoped = scoped[scoped["match_ts"] >= (newest - pd.Timedelta(days=int(days_window) * 8))].copy()

    tactical, baseline = _build_tactic_views(scoped)
    tactical = tactical[tactical["rounds"] >= int(sample_floor)].copy()
    if tactical.empty:
        st.warning("No tactics meet the minimum sample threshold for this map + side.")
        return

    tactical["is_recent_5d"] = tactical["days_since_used"] <= 5
    viable_status = {"Strong Keep", "Keep", "Refine", "Situational"}

    st.markdown(
        f"<div style='margin:6px 0 8px 0;'><span class='context-chip'>ACTIVE MAP: <strong>{map_context}</strong></span>"
        f"<span class='context-chip'>ACTIVE SIDE: <strong>{side_context}</strong></span>"
        f"<span class='context-chip'>OPP TIERS: <strong>{', '.join(selected_tiers) if selected_tiers else 'None'}</strong></span>"
        f"<span class='context-chip'>BASELINE WR: <strong>{_fmt_pct(tactical['baseline_wr'].iloc[0])}</strong></span></div>",
        unsafe_allow_html=True,
    )

    best = tactical.sort_values(["win_rate", "rounds"], ascending=[False, False]).iloc[0]
    worst = tactical.sort_values(["win_rate", "rounds"], ascending=[True, False]).iloc[0]
    most_used = tactical.sort_values("rounds", ascending=False).iloc[0]
    recent_best = tactical.sort_values(["recent_wr", "rounds"], ascending=[False, False]).iloc[0]
    volatile = tactical.sort_values("volatility", ascending=False).iloc[0]

    k1, k2, k3, k4, k5, k6, k7 = st.columns(7, gap="small")
    for col, title, primary, secondary, accent in [
        (k1, "Best Performing", _fmt_pct(best["win_rate"]), str(best["tactic_name"]), "good"),
        (k2, "Worst Performing", _fmt_pct(worst["win_rate"]), str(worst["tactic_name"]), "bad"),
        (k3, "Most Used", f"{int(most_used['rounds'])}", str(most_used["tactic_name"]), "mid"),
        (k4, "Best Recent", _fmt_pct(recent_best["recent_wr"]), str(recent_best["tactic_name"]), "good"),
        (k5, "Most Volatile", _fmt_signed(volatile["recent_delta"]), str(volatile["tactic_name"]), "poor"),
        (k6, "Under-tested", f"{int((tactical['rounds'] < 8).sum())}", "< 8 rounds", "poor"),
        (k7, "Viable Tactics", f"{int(tactical['status'].isin(viable_status).sum())}", "Keep/Refine/Situational", "mid"),
    ]:
        with col:
            st.markdown(
                f"<div class='panel panel-tight stat-widget accent-{accent}'><div class='metric-title'>{title}</div>"
                f"<div class='metric-value'>{primary}</div><div class='muted'>{secondary}</div></div>",
                unsafe_allow_html=True,
            )

    if PLOTLY_AVAILABLE:
        left, right = st.columns([1.2, 1], gap="small")
        with left:
            st.markdown("<div class='analytics-frame'><div class='section-title'>Usage vs Performance</div></div>", unsafe_allow_html=True)
            scatter = px.scatter(
                tactical,
                x="rounds",
                y="win_rate",
                color="status",
                size="rounds",
                hover_name="tactic_name",
                hover_data={"delta_vs_baseline": ":.1f", "recent_wr": ":.1f", "baseline_wr": ":.1f"},
                color_discrete_map={
                    "Strong Keep": "#9FE870",
                    "Keep": "#66d48f",
                    "Refine": "#d3a85c",
                    "Test More": "#ff9f43",
                    "Situational": "#9fb4ca",
                    "Risky": "#ff7a4d",
                    "Drop": "#ff4d5e",
                },
            )
            scatter.add_hline(y=float(tactical["baseline_wr"].iloc[0]), line_dash="dot", line_color="#9fb4ca")
            scatter.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=10, b=8), height=390 if not mobile_view else 320)
            st.plotly_chart(scatter, use_container_width=True)

        with right:
            st.markdown("<div class='analytics-frame'><div class='section-title'>Recent vs Long-Run Delta</div></div>", unsafe_allow_html=True)
            compare = tactical.sort_values("recent_delta")
            bars = go.Figure()
            bars.add_bar(
                x=compare["recent_delta"],
                y=compare["tactic_name"],
                orientation="h",
                marker_color=np.where(compare["recent_delta"] >= 0, "#9FE870", "#ff9f43"),
            )
            bars.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=10, b=8), height=390 if not mobile_view else 320)
            st.plotly_chart(bars, use_container_width=True)
    else:
        st.warning("Plotly unavailable in this environment; interactive tactical visuals are disabled.")

    st.markdown("<div class='section-title' style='margin-top:8px;'>Tactic Status Board</div>", unsafe_allow_html=True)
    tactical["board_score"] = (
        tactical["delta_vs_baseline"] * 2.4
        + tactical["weighted_wr"] * 0.26
        + np.log1p(tactical["rounds"]) * 5.8
        - tactical["volatility"] * 0.85
        - np.where(tactical["days_since_used"] > 18, 2.6, 0)
    )
    tactical["reason"] = tactical.apply(_compose_reason, axis=1)
    group_cap = 3 if not mobile_view else 2
    remaining = []
    for status in STATUS_PRIORITY:
        block = tactical[tactical["status"] == status].sort_values(["board_score", "rounds"], ascending=[False, False]).reset_index(drop=True)
        if block.empty:
            continue
        accent = STATUS_COLORS.get(status, "mid")
        priority = block.head(group_cap).copy()
        overflow = block.iloc[group_cap:].copy()
        st.markdown(
            f"<div class='status-group'><div class='status-group-header'><h3>{status}</h3>"
            f"<div class='status-group-meta'>{len(block)} tactics • top {len(priority)} surfaced by relevance score</div></div></div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(3 if not mobile_view else 1, gap="small")
        for i, row in priority.iterrows():
            with cols[i % len(cols)]:
                st.markdown(
                    f"<div class='tactic-card'><h4>{row['tactic_name']}</h4>"
                    f"<div class='status-pill {accent}'>{row['status']}</div>"
                    f"<div class='tactic-mini'>{row['tactic_type']} • {row['coverage']}</div>"
                    f"<div class='tactic-mini'>WR {_fmt_pct(row['win_rate'])} | Δ {_fmt_signed(row['delta_vs_baseline'])}</div>"
                    f"<div class='tactic-mini'>Rounds {int(row['rounds'])} | Recent {_fmt_pct(row['recent_wr'])} ({_fmt_signed(row['recent_delta'])})</div>"
                    f"<div class='tactic-mini'>Last used {row['last_used_label']}</div>"
                    f"<div class='grev-tier-row'>{_wr_tier_box('S', row['S'])}{_wr_tier_box('A', row['A'])}{_wr_tier_box('B', row['B'])}{_wr_tier_box('C', row['C'])}</div>"
                    f"<div class='tactic-reason'>{row['reason']}</div></div>",
                    unsafe_allow_html=True,
                )
        if not overflow.empty:
            with st.expander(f"{status}: show {len(overflow)} additional lower-priority tactics"):
                reduced = overflow[["tactic_name", "rounds", "win_rate", "delta_vs_baseline", "recent_wr", "last_used_label", "reason"]].rename(
                    columns={
                        "tactic_name": "Tactic",
                        "rounds": "Rounds",
                        "win_rate": "Win Rate",
                        "delta_vs_baseline": "Δ vs Baseline",
                        "recent_wr": "Recent WR",
                        "last_used_label": "Last Used",
                        "reason": "Reason",
                    }
                )
                st.dataframe(reduced, use_container_width=True, hide_index=True)
        remaining.append(len(overflow))

    st.markdown("<div class='section-title' style='margin-top:10px;'>Recommended 6–7 Tactic Set (Current Global Context)</div>", unsafe_allow_html=True)
    rec_pool = tactical[tactical["status"].isin(["Strong Keep", "Keep", "Refine", "Situational", "Test More"])].copy()
    rec_pool["pick_score"] = rec_pool["weighted_wr"] * 0.52 + rec_pool["delta_vs_baseline"] * 2.1 + np.log1p(rec_pool["rounds"]) * 6
    slots = ["Pistol", "Eco A", "Eco B", "Standard A", "Standard B", "Mid", "Ivy"]
    picks = []
    for slot in slots:
        hit = rec_pool[rec_pool["coverage"] == slot].sort_values("pick_score", ascending=False)
        if not hit.empty:
            picks.append(hit.iloc[0])
    if len(picks) < 6:
        fallback = rec_pool.sort_values("pick_score", ascending=False)
        for _, r in fallback.iterrows():
            if all(r["tactic_name"] != p["tactic_name"] for p in picks):
                picks.append(r)
            if len(picks) >= 6:
                break
    picks = picks[:7]
    rec_cols = st.columns(min(4, len(picks)) if picks else 1, gap="small")
    for idx, row in enumerate(picks):
        with rec_cols[idx % len(rec_cols)]:
            st.markdown(
                f"<div class='recommend-slot'><div class='metric-title'>{row['coverage']}</div>"
                f"<div style='font-weight:760;color:#f2f8ff;font-size:.82rem'>{row['tactic_name']}</div>"
                f"<div class='muted'>Status: {row['status']} • WR {_fmt_pct(row['win_rate'])} • Δ {_fmt_signed(row['delta_vs_baseline'])}</div>"
                f"<div class='muted'>Included for coverage balance and weighted tier reliability in this active global context.</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div class='section-title' style='margin-top:10px;'>Recently Used & Emerging (last 5 days)</div>", unsafe_allow_html=True)
    recent_df = tactical[(tactical["is_recent_5d"]) | (tactical["rounds"] < 6)].copy().sort_values(
        ["is_recent_5d", "recent_wr", "rounds"], ascending=[False, False, True]
    )
    if recent_df.empty:
        st.info("No emerging/recent tactics in the last 5 days for this map + side.")
    else:
        st.dataframe(
            recent_df[["tactic_name", "tactic_type", "rounds", "win_rate", "recent_wr", "recent_delta", "last_used_label", "status"]]
            .rename(
                columns={
                    "tactic_name": "Tactic",
                    "tactic_type": "Type",
                    "rounds": "Rounds",
                    "win_rate": "Win Rate",
                    "recent_wr": "Recent WR",
                    "recent_delta": "Recent Δ",
                    "last_used_label": "Last Used",
                    "status": "Status",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("<div class='section-title' style='margin-top:10px;'>Premium Tactical Analysis Grid</div>", unsafe_allow_html=True)
    table = tactical[
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
            "status",
            "analyst_note",
        ]
    ].rename(
        columns={
            "tactic_name": "Tactic",
            "tactic_type": "Type",
            "map": "Map",
            "side": "Side",
            "rounds": "Rounds",
            "win_rate": "Win Rate",
            "delta_vs_baseline": "Δ vs Baseline",
            "recent_wr": "Recent WR",
            "last_used_label": "Last Used",
            "analyst_note": "Recommendation",
        }
    )
    st.dataframe(table.sort_values(["Δ vs Baseline", "Win Rate"], ascending=False), use_container_width=True, hide_index=True)

    st.markdown("<div class='section-title' style='margin-top:10px;'>Tactic Deep-Dive Analyst Tool</div>", unsafe_allow_html=True)
    st.caption(f"Context locked to Map: {map_context} • Side: {side_context} • Competition: {comp_context}")
    selected_tactic = st.selectbox("Inspect tactic", options=tactical["tactic_name"].sort_values().tolist())
    one = tactical[tactical["tactic_name"] == selected_tactic].iloc[0]

    d1, d2, d3 = st.columns([1.1, 1.1, 1.8], gap="small")
    with d1:
        st.markdown(
            f"<div class='panel'><div class='metric-title'>Performance Summary</div>"
            f"<div class='metric-value'>{_fmt_pct(one['win_rate'])}</div>"
            f"<div class='muted'>Baseline {_fmt_pct(one['baseline_wr'])} • Δ {_fmt_signed(one['delta_vs_baseline'])}</div>"
            f"<div class='muted'>Rounds {int(one['rounds'])} • Last used {one['last_used_label']}</div></div>",
            unsafe_allow_html=True,
        )
    with d2:
        st.markdown(
            f"<div class='panel'><div class='metric-title'>Tier Split & Risk Read</div>"
            f"<div class='muted'>S-tier {_fmt_pct(one['S']) if pd.notna(one['S']) else 'N/A'} | A-tier {_fmt_pct(one['A']) if pd.notna(one['A']) else 'N/A'}</div>"
            f"<div class='muted'>B-tier {_fmt_pct(one['B']) if pd.notna(one['B']) else 'N/A'} | C-tier {_fmt_pct(one['C']) if pd.notna(one['C']) else 'N/A'}</div>"
            f"<div class='muted'>Weighted WR {_fmt_pct(one['weighted_wr'])} emphasizes S/A outcomes.</div></div>",
            unsafe_allow_html=True,
        )
    with d3:
        trend_data = scoped[scoped["tactic_name"] == selected_tactic].copy().sort_values("match_ts")
        trend_data["wr"] = (trend_data["wins"] / (trend_data["wins"] + trend_data["losses"]).clip(lower=1) * 100).fillna(0)
        if PLOTLY_AVAILABLE and not trend_data.empty:
            tfig = px.line(trend_data, x="match_ts", y="wr", markers=True)
            tfig.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=220)
            tfig.add_hline(y=float(one["baseline_wr"]), line_dash="dot", line_color="#9fb4ca")
            st.plotly_chart(tfig, use_container_width=True)
        st.markdown(
            f"<div class='panel panel-tight'><div class='metric-title'>Analyst Rationale</div>"
            f"<div class='muted'>Status: {one['status']}. {one['analyst_note']}</div></div>",
            unsafe_allow_html=True,
        )
