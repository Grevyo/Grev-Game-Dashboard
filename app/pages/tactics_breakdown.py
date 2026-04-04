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

from app.config import TIER_COLORS
from app.datetime_utils import build_match_timestamp, normalize_time_series
from app.page_layout import is_mobile_view
from app.tactics import (
    TACTICAL_TIER_WEIGHTS,
    TIER_ORDER,
    attach_normalized_tier,
    normalize_tier_values,
    tactic_category,
    weighted_tactical_win_rate,
)

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
    weighted_delta = float(row["weighted_delta_vs_baseline"])
    recent_delta = float(row["recent_delta"])
    rounds = float(row["rounds"])
    s_delta = float(row["s_tier_delta"])
    low_tier_inflation = float(row["c_tier_inflation"])
    depth_signal = float(row.get("depth_signal", 0.0))
    competitiveness_signal = float(row.get("competitiveness_signal", 0.0))
    context_confidence = float(row.get("context_confidence", 0.0))
    stomp_inflation = float(row.get("stomp_inflation", 0.0))
    high_tier_round_share = float(row.get("high_tier_round_share", 0.0))

    if rounds >= 12 and weighted_delta >= 8 and s_delta >= 4 and recent_delta >= -1 and context_confidence >= 0.52:
        return "Strong Keep", "Strong return vs S-tier opposition and clear weighted edge over baseline in this map+side context."
    if rounds >= 10 and weighted_delta >= 4 and s_delta >= 0 and context_confidence >= 0.45:
        return "Keep", "Positive weighted edge with credible S/A/B proof; keep in active set rotation."
    if rounds >= 8 and weighted_delta >= 0 and recent_delta < -6:
        return "Refine", "Still viable on weighted high-tier profile, but recent form dropped and needs refinement."
    if rounds < 8 and weighted_delta >= 2:
        return "Test More", "Early weighted signal is promising, but sample is still too thin to lock."
    if rounds >= 8 and weighted_delta < -9:
        return "Drop", "Weighted profile is materially below baseline, including pressure vs stronger tiers."
    if rounds >= 8 and (weighted_delta < -4 or s_delta <= -8):
        return "Risky", "Weak S-tier/high-tier outcomes increase downside risk in this context."
    if rounds >= 10 and weighted_delta >= 0 and (stomp_inflation >= 12 or context_confidence < 0.34):
        return "Refine", "Raw output is positive, but evidence quality is reduced by low-depth or stomp-heavy context."
    if low_tier_inflation > 6:
        return "Situational", "Raw return is inflated by C-tier results; keep only for selective reads until stronger-tier proof improves."
    if high_tier_round_share < 0.35 and depth_signal < 0.42 and competitiveness_signal < 0.45:
        return "Test More", "Limited higher-tier and low-depth context make current signal less trustworthy."
    return "Situational", "Mixed evidence profile; use conditionally rather than as a default call."


def _compose_reason(row: pd.Series) -> str:
    delta = float(row["delta_vs_baseline"])
    rounds = int(row["rounds"])
    recent_delta = float(row["recent_delta"])
    weighted = float(row["weighted_wr"])
    win_rate = float(row["win_rate"])
    s_delta = float(row["s_tier_delta"])
    c_inflation = float(row["c_tier_inflation"])
    days_since = int(row["days_since_used"])
    status = str(row["status"])
    high_tier_share = float(row.get("high_tier_round_share", 0.0))
    context_confidence = float(row.get("context_confidence", 0.0))
    depth_signal = float(row.get("depth_signal", 0.0))
    competitiveness_signal = float(row.get("competitiveness_signal", 0.0))
    stomp_inflation = float(row.get("stomp_inflation", 0.0))
    weighted_delta = float(row.get("weighted_delta_vs_baseline", 0.0))

    if status == "Strong Keep":
        if s_delta >= 4 and high_tier_share >= 0.6:
            return "High win rate against stronger tiers with stable sample and clear weighted edge."
        return "Strong weighted return in deeper, competitive matches with stable recent form."
    if status == "Keep":
        if high_tier_share >= 0.55 and weighted_delta >= 3:
            return "Positive S/A/B evidence and weighted return above map-side baseline."
        if context_confidence >= 0.55:
            return "Stable option in competitive, tactically deeper matches."
        return "Good weighted return, but evidence context is moderate rather than elite."
    if status == "Refine":
        if stomp_inflation >= 10:
            return "Good raw numbers, but much of the sample comes from low-complexity stomp wins."
        return "Long-run return is positive, but recent results softened and need tactical refinement."
    if status == "Test More":
        if rounds < 8:
            return "Promising early return, but sample and higher-tier proof are still limited."
        if context_confidence < 0.35:
            return "Results come from shallow match contexts; needs reps in closer, deeper games."
        return "Early return is promising, but low sample still limits confidence."
    if status == "Risky":
        if s_delta <= -8:
            return "S-tier outcomes are materially below baseline, so risk is elevated despite usage."
        if weighted_delta < -4 and high_tier_share >= 0.5:
            return "High usage but weighted return is trailing the current map-side baseline."
        return "Weighted high-tier profile is below baseline; use only as a conditional counter-look."
    if status == "Drop":
        if weighted_delta < -10 and recent_delta < -4:
            return "Weak recent trend and poor higher-tier evidence make this a low-confidence option."
        return "Sustained underperformance on weighted high-tier evidence warrants de-prioritization."
    if c_inflation > 6:
        return "Mostly inflated by lower-tier results; stronger-tier evidence is still limited."
    if s_delta >= 4 and context_confidence >= 0.5:
        return "Stronger than raw return suggests because results came in competitive match contexts."
    if depth_signal >= 0.62 and competitiveness_signal >= 0.55:
        return "Solid return in deeper tactical matches, but still more situational than core."
    if recent_delta >= 4:
        return "Recent form is improving, but stronger-tier evidence is still situational."
    if days_since > 21:
        return "Not used recently and evidence is mixed; retain only for niche game-state reads."
    return "Stable mid-band option for selective situations, but not a default call."


def _build_match_context(base: pd.DataFrame) -> pd.DataFrame:
    context_cols = ["match_id", "map", "side"]
    match_totals = (
        base.groupby(context_cols, dropna=False)
        .agg(
            side_wins=("wins", "sum"),
            side_losses=("losses", "sum"),
            side_rounds=("total_rounds", "sum"),
            distinct_tactics=("tactic_name", pd.Series.nunique),
        )
        .reset_index()
    )
    side_rounds = match_totals["side_rounds"].clip(lower=1.0)
    round_margin = (match_totals["side_wins"] - match_totals["side_losses"]).abs()
    match_totals["competitiveness"] = (1.0 - (round_margin / side_rounds)).clip(lower=0.0, upper=1.0)
    match_totals["depth_score"] = ((match_totals["distinct_tactics"] - 2.0) / 5.0).clip(lower=0.0, upper=1.0)
    match_totals["context_signal"] = (
        match_totals["competitiveness"] * 0.55
        + match_totals["depth_score"] * 0.45
    ).clip(lower=0.0, upper=1.0)
    match_totals["stomp_penalty"] = ((0.55 - match_totals["competitiveness"]).clip(lower=0.0) * 100.0).clip(upper=25.0)
    return match_totals


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


def _tactic_selection_key(row: pd.Series) -> str:
    return f"{row['map']}||{row['side']}||{row['tactic_name']}"


def _first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(col).strip().lower(): col for col in df.columns}
    for cand in candidates:
        col = normalized.get(cand.strip().lower())
        if col is not None:
            return col
    return None


def _dedupe_tactic_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    cleaned = df.copy()
    unnamed_cols = [c for c in cleaned.columns if str(c).strip().lower().startswith("unnamed:")]
    if unnamed_cols:
        cleaned = cleaned.drop(columns=unnamed_cols, errors="ignore")

    dedupe_keys = [
        "match_id",
        "date",
        "time",
        "map",
        "competition",
        "my_team",
        "opponent_team",
        "side",
        "tactic_name",
        "wins",
        "losses",
        "total_rounds",
        "win_rate_pct",
    ]
    existing_keys = [col for col in dedupe_keys if col in cleaned.columns]
    if not existing_keys:
        return cleaned

    return cleaned.drop_duplicates(subset=existing_keys, keep="first").reset_index(drop=True)


def _manual_exclusion_key(map_name: str, side: str) -> str:
    return f"tsr_excluded::{map_name}::{side}"


def _get_excluded_for_context(map_name: str, side: str, available: set[str]) -> set[str]:
    key = _manual_exclusion_key(map_name, side)
    stored = set(st.session_state.get(key, []))
    return {name for name in stored if name in available}


def _set_excluded_for_context(map_name: str, side: str, excluded: set[str]) -> None:
    key = _manual_exclusion_key(map_name, side)
    st.session_state[key] = sorted(excluded)


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
    tier_wins = tier_view.pivot_table(index=group_cols, columns="tier", values="twins", aggfunc="sum", fill_value=0).reset_index()
    tier_losses = tier_view.pivot_table(index=group_cols, columns="tier", values="tlosses", aggfunc="sum", fill_value=0).reset_index()
    for t in TIER_ORDER:
        if t not in tier_pivot.columns:
            tier_pivot[t] = np.nan
        if t not in tier_wins.columns:
            tier_wins[t] = 0.0
        if t not in tier_losses.columns:
            tier_losses[t] = 0.0
    tier_wins = tier_wins.rename(columns={t: f"{t}_wins" for t in TIER_ORDER})
    tier_losses = tier_losses.rename(columns={t: f"{t}_losses" for t in TIER_ORDER})

    context = _build_match_context(base)
    contextual_base = base.merge(
        context[["match_id", "map", "side", "competitiveness", "depth_score", "context_signal", "stomp_penalty", "distinct_tactics"]],
        on=["match_id", "map", "side"],
        how="left",
    )

    context_by_tactic = (
        contextual_base.groupby(group_cols, dropna=False)
        .agg(
            depth_signal=("depth_score", "mean"),
            competitiveness_signal=("competitiveness", "mean"),
            context_confidence=("context_signal", "mean"),
            stomp_inflation=("stomp_penalty", "mean"),
            avg_distinct_tactics=("distinct_tactics", "mean"),
        )
        .reset_index()
    )

    tactical = (
        tactical.merge(recent[group_cols + ["recent_wr", "rrounds"]], on=group_cols, how="left")
        .merge(tier_pivot[group_cols + TIER_ORDER], on=group_cols, how="left")
        .merge(tier_wins[group_cols + [f"{t}_wins" for t in TIER_ORDER]], on=group_cols, how="left")
        .merge(tier_losses[group_cols + [f"{t}_losses" for t in TIER_ORDER]], on=group_cols, how="left")
        .merge(context_by_tactic, on=group_cols, how="left")
    )
    tactical["weighted_wr"] = weighted_tactical_win_rate(tactical, fallback_wr_col="win_rate")

    baseline = (
        base.groupby(["map", "side"], dropna=False)
        .agg(base_wins=("wins", "sum"), base_losses=("losses", "sum"), base_rounds=("total_rounds", "sum"))
        .reset_index()
    )
    baseline["baseline_wr"] = (baseline["base_wins"] / (baseline["base_wins"] + baseline["base_losses"]).clip(lower=1) * 100).fillna(0)

    tactical = tactical.merge(baseline[["map", "side", "baseline_wr", "base_rounds"]], on=["map", "side"], how="left")
    tactical["delta_vs_baseline"] = tactical["win_rate"] - tactical["baseline_wr"]
    tactical["weighted_delta_vs_baseline"] = tactical["weighted_wr"] - tactical["baseline_wr"]
    tactical["depth_signal"] = tactical["depth_signal"].fillna(0.0).clip(lower=0.0, upper=1.0)
    tactical["competitiveness_signal"] = tactical["competitiveness_signal"].fillna(0.0).clip(lower=0.0, upper=1.0)
    tactical["context_confidence"] = tactical["context_confidence"].fillna(0.0).clip(lower=0.0, upper=1.0)
    tactical["stomp_inflation"] = tactical["stomp_inflation"].fillna(0.0).clip(lower=0.0, upper=25.0)
    tactical["avg_distinct_tactics"] = tactical["avg_distinct_tactics"].fillna(0.0)

    context_bonus = tactical["context_confidence"] * 4.4
    stomp_penalty = tactical["stomp_inflation"] * 0.42
    tactical["weighted_delta_vs_baseline"] = tactical["weighted_delta_vs_baseline"] + context_bonus - stomp_penalty
    tactical["s_tier_delta"] = tactical["S"].fillna(tactical["win_rate"]) - tactical["baseline_wr"]
    tactical["c_tier_inflation"] = (tactical["C"].fillna(tactical["win_rate"]) - tactical["weighted_wr"]).clip(lower=0)
    total_weighted_rounds = pd.Series(0.0, index=tactical.index, dtype=float)
    high_weighted_rounds = pd.Series(0.0, index=tactical.index, dtype=float)
    for tier in TIER_ORDER:
        wins = pd.to_numeric(tactical.get(f"{tier}_wins", 0), errors="coerce").fillna(0.0)
        losses = pd.to_numeric(tactical.get(f"{tier}_losses", 0), errors="coerce").fillna(0.0)
        weighted_rounds = (wins + losses) * float(TACTICAL_TIER_WEIGHTS.get(tier, 1.0))
        total_weighted_rounds = total_weighted_rounds + weighted_rounds
        if tier in {"S", "A", "B"}:
            high_weighted_rounds = high_weighted_rounds + weighted_rounds
    tactical["high_tier_round_share"] = (high_weighted_rounds / total_weighted_rounds.clip(lower=1e-9)).fillna(0.0)
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
        .tactic-card.selected{border-color:#9FE870;box-shadow:0 0 0 1px rgba(159,232,112,.35),0 0 18px rgba(159,232,112,.16);}
        .tactic-card h4{margin:0;color:#f4f8ff;font-size:.87rem;line-height:1.25;}
        .status-pill{display:inline-block;font-size:.56rem;letter-spacing:.11em;text-transform:uppercase;padding:2px 7px;border-radius:999px;border:1px solid #42596f;margin-top:6px;}
        .status-pill.good{color:#9FE870;border-color:#4a7242;background:#1a2b1b;}
        .status-pill.mid{color:#d3a85c;border-color:#78603b;background:#2a2418;}
        .status-pill.poor{color:#ff9f43;border-color:#865830;background:#2a1f14;}
        .status-pill.bad{color:#ff4d5e;border-color:#7a3540;background:#2a171d;}
        .status-pill.excluded{color:#f7c6ce;border-color:#7a3540;background:#2a171d;}
        .tactic-mini{font-size:.64rem;color:#94a6bb;margin-top:4px;}
        .recommend-slot{border:1px solid #34485f;border-radius:7px;background:#101c2a;padding:.55rem;}
        .tier-filter-wrap{display:flex;align-items:center;justify-content:flex-end;}
        .status-group{margin-top:12px;border:1px solid #2f4155;border-radius:10px;background:linear-gradient(180deg,#101a27,#0c1521);padding:.7rem;}
        .status-group-header{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;}
        .status-group h3{margin:0;font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:#d6e3f2;}
        .status-group-meta{font-size:.64rem;color:#95a8bc;}
        .tactic-card .grev-tier-row{margin-top:7px;grid-template-columns:repeat(4,minmax(0,1fr));}
        .tactic-card.excluded{opacity:.58;border-color:#72515c;background:linear-gradient(180deg,#281924,#181019);}
        .tactic-card.selected.excluded{border-color:#d18897;box-shadow:0 0 0 1px rgba(209,136,151,.35),0 0 18px rgba(148,71,87,.2);}
        .wr-tier-box{min-height:54px;padding:6px 5px;}
        .tactic-reason{margin-top:8px;font-size:.68rem;color:#d2deea;line-height:1.35;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_tactics_breakdown(ctx, *, recent_mode: bool = False):
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

    tdf = attach_normalized_tier(tdf, fallback="C")

    date_ser = tdf.get("date", pd.Series([None] * len(tdf), index=tdf.index))
    time_ser = normalize_time_series(tdf.get("time", pd.Series([None] * len(tdf), index=tdf.index)))
    tdf["time"] = time_ser
    tdf["match_ts"] = build_match_timestamp(date_ser, time_ser)
    tdf["match_ts"] = tdf["match_ts"].fillna(build_match_timestamp(date_ser))

    hero_subtitle = (
        "Recent-window tactical command centre for map-side decisions in the last N days."
        if recent_mode
        else "Analyst command centre for map-side specific tactical decisions: what to keep, what to refine, what to stress-test, and what to drop."
    )

    st.markdown(
        f"""
        <div class='hero-band'>
            <div class='section-title'>Tactical Intelligence Surface</div>
            <h1 class='tactics-hero-title'>{'Recent Tactics Breakdown' if recent_mode else 'Tactics Breakdown'}</h1>
            <p class='tactics-hero-subtitle'>
                {hero_subtitle}
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
        days_window = None
        if recent_mode:
            days_window = st.slider("Last N Days", min_value=1, max_value=14, value=7, step=1)
        else:
            st.caption("Full-history mode (no recent-window filter)")
    with c3:
        max_scope = tdf.copy()
        if tactic_type != "All":
            max_scope = max_scope[max_scope["tactic_type"] == tactic_type].copy()
        if recent_mode and days_window is not None and not max_scope.empty:
            newest_scope = max_scope["match_ts"].max()
            max_scope = max_scope[max_scope["match_ts"] >= (newest_scope - pd.Timedelta(days=int(days_window)))].copy()
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

    if recent_mode and days_window is not None:
        newest = scoped["match_ts"].max()
        scoped = scoped[scoped["match_ts"] >= (newest - pd.Timedelta(days=int(days_window)))].copy()

    tactical, baseline = _build_tactic_views(scoped)
    tactical = tactical[tactical["rounds"] >= int(sample_floor)].copy()
    if tactical.empty:
        st.warning("No tactics meet the minimum sample threshold for this map + side.")
        return
    tactical["tactic_uid"] = tactical.apply(_tactic_selection_key, axis=1)
    tactical["is_excluded"] = False
    selection_state_key = "tactics_breakdown_selected_tactic_uid"
    if selection_state_key not in st.session_state:
        st.session_state[selection_state_key] = None
    if st.session_state[selection_state_key] not in set(tactical["tactic_uid"]):
        st.session_state[selection_state_key] = None

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
        tactical["weighted_delta_vs_baseline"] * 2.9
        + tactical["weighted_wr"] * 0.34
        + np.log1p(tactical["rounds"]) * 5.8
        - tactical["volatility"] * 0.85
        - np.where(tactical["days_since_used"] > 18, 2.6, 0)
    )
    tactical["reason"] = tactical.apply(_compose_reason, axis=1)
    available_names_by_context = (
        tactical.groupby(["map", "side"], dropna=False)["tactic_name"].apply(lambda names: set(names.astype(str))).to_dict()
    )
    excluded_by_context: dict[tuple[str, str], set[str]] = {}
    for context, names in available_names_by_context.items():
        excluded_by_context[context] = _get_excluded_for_context(context[0], context[1], names)
    tactical["is_excluded"] = tactical.apply(
        lambda row: str(row["tactic_name"]) in excluded_by_context.get((str(row["map"]), str(row["side"])), set()),
        axis=1,
    )
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
                selected = st.session_state[selection_state_key] == row["tactic_uid"]
                selected_class = " selected" if selected else ""
                excluded = bool(row["is_excluded"])
                excluded_class = " excluded" if excluded else ""
                excluded_badge = "<div class='status-pill excluded'>Excluded</div>" if excluded else ""
                st.markdown(
                    f"<div class='tactic-card{selected_class}{excluded_class}'><h4>{row['tactic_name']}</h4>"
                    f"<div class='status-pill {accent}'>{row['status']}</div>"
                    f"{excluded_badge}"
                    f"<div class='tactic-mini'>{row['tactic_type']} • {row['coverage']}</div>"
                    f"<div class='tactic-mini'>WR {_fmt_pct(row['win_rate'])} | Δ {_fmt_signed(row['delta_vs_baseline'])}</div>"
                    f"<div class='tactic-mini'>Rounds {int(row['rounds'])} | Recent {_fmt_pct(row['recent_wr'])} ({_fmt_signed(row['recent_delta'])})</div>"
                    f"<div class='tactic-mini'>Last used {row['last_used_label']}</div>"
                    f"<div class='grev-tier-row'>{_wr_tier_box('S', row['S'])}{_wr_tier_box('A', row['A'])}{_wr_tier_box('B', row['B'])}{_wr_tier_box('C', row['C'])}</div>"
                    f"<div class='tactic-reason'>{row['reason']}</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Inspect tactic" if not selected else "Selected • viewing below",
                    key=f"inspect_tactic_{status}_{i}_{row['tactic_uid']}",
                    type="primary" if selected else "secondary",
                    use_container_width=True,
                ):
                    st.session_state[selection_state_key] = row["tactic_uid"]
                action_label = "Re-include tactic" if excluded else "Exclude tactic"
                if st.button(
                    action_label,
                    key=f"exclude_tactic_{status}_{i}_{row['tactic_uid']}",
                    type="secondary",
                    use_container_width=True,
                ):
                    context_key = (str(row["map"]), str(row["side"]))
                    current = set(excluded_by_context.get(context_key, set()))
                    tactic_name = str(row["tactic_name"])
                    if excluded:
                        current.discard(tactic_name)
                    else:
                        current.add(tactic_name)
                    excluded_by_context[context_key] = current
                    _set_excluded_for_context(context_key[0], context_key[1], current)
                    st.rerun()
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
    rec_pool = tactical[
        tactical["status"].isin(["Strong Keep", "Keep", "Refine", "Situational", "Test More"]) & ~tactical["is_excluded"]
    ].copy()
    rec_pool["pick_score"] = rec_pool["weighted_wr"] * 0.62 + rec_pool["weighted_delta_vs_baseline"] * 2.6 + np.log1p(rec_pool["rounds"]) * 6
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
    selected_uid = st.session_state.get(selection_state_key)
    if not selected_uid:
        st.info("Select a tactic to inspect full match history, tactic-specific trend graphs, and per-match outcomes.")
        return

    one = tactical[tactical["tactic_uid"] == selected_uid].iloc[0]
    selected_excluded = bool(one["is_excluded"])
    tactic_matches = scoped[
        (scoped["tactic_name"] == one["tactic_name"]) & (scoped["map"] == one["map"]) & (scoped["side"] == one["side"])
    ].copy()
    tactic_matches = _dedupe_tactic_rows(tactic_matches)
    tactic_matches["opponent"] = tactic_matches.get("opponent_team", "Unknown").astype(str).str.strip().replace("", "Unknown")
    tactic_matches["rounds_used"] = tactic_matches["total_rounds"]
    tactic_matches["rounds_won"] = tactic_matches["wins"]
    tactic_matches["rounds_lost"] = tactic_matches["losses"]

    team_score_col = _first_existing_col(tactic_matches, ["team_score", "my_team_score", "score_for", "our_score"])
    opp_score_col = _first_existing_col(tactic_matches, ["opponent_score", "opp_score", "score_against"])
    match_result_col = _first_existing_col(tactic_matches, ["match_result", "result"])

    agg = {
        "competition": "first",
        "map": "first",
        "side": "first",
        "opponent": "first",
        "tier": "first",
        "rounds_used": "sum",
        "rounds_won": "sum",
        "rounds_lost": "sum",
    }
    if team_score_col:
        agg[team_score_col] = "first"
    if opp_score_col:
        agg[opp_score_col] = "first"
    if match_result_col:
        agg[match_result_col] = "first"

    match_table = (
        tactic_matches.groupby(["match_id", "date", "time", "match_ts"], dropna=False)
        .agg(agg)
        .reset_index()
        .sort_values(["match_ts", "match_id"], ascending=[False, False])
    )
    match_table["win_rate_pct"] = (match_table["rounds_won"] / match_table["rounds_used"].clip(lower=1) * 100).fillna(0)
    if match_result_col is None and team_score_col and opp_score_col:
        match_table["derived_result"] = np.where(
            match_table[team_score_col] > match_table[opp_score_col],
            "Win",
            np.where(match_table[team_score_col] < match_table[opp_score_col], "Loss", "Draw"),
        )
        match_result_col = "derived_result"

    d1, d2, d3 = st.columns([1.1, 1.1, 1.8], gap="small")
    with d1:
        st.markdown(
            f"<div class='panel'><div class='metric-title'>Selected Tactic Context</div>"
            f"<div class='metric-value'>{one['tactic_name']}</div>"
            f"<div class='muted'>{one['map']} • {one['side']} • {one['tactic_type']}</div>"
            f"<div class='muted'>Status: {one['status']} | Rounds {int(one['rounds'])}</div></div>",
            unsafe_allow_html=True,
        )
    with d2:
        st.markdown(
            f"<div class='panel'><div class='metric-title'>Performance Summary</div>"
            f"<div class='metric-value'>{_fmt_pct(one['win_rate'])}</div>"
            f"<div class='muted'>Baseline {_fmt_pct(one['baseline_wr'])} • Δ {_fmt_signed(one['delta_vs_baseline'])}</div>"
            f"<div class='muted'>Weighted WR {_fmt_pct(one['weighted_wr'])} • Last used {one['last_used_label']}</div></div>",
            unsafe_allow_html=True,
        )
    with d3:
        st.markdown(
            f"<div class='panel panel-tight'><div class='metric-title'>Analyst Rationale</div>"
            f"<div class='muted'>Status: {one['status']}. {one['analyst_note']}</div></div>",
            unsafe_allow_html=True,
        )
        drill_label = "Re-include tactic in recommendation pool" if selected_excluded else "Exclude tactic from recommendation pool"
        if st.button(
            drill_label,
            key=f"drilldown_exclusion_{selected_uid}",
            use_container_width=True,
        ):
            context_key = (str(one["map"]), str(one["side"]))
            current = set(excluded_by_context.get(context_key, set()))
            tactic_name = str(one["tactic_name"])
            if selected_excluded:
                current.discard(tactic_name)
            else:
                current.add(tactic_name)
            _set_excluded_for_context(context_key[0], context_key[1], current)
            st.rerun()
        if selected_excluded:
            st.caption("This tactic is currently excluded from the shared recommendation candidate pool for this map+side context.")

    if PLOTLY_AVAILABLE and not match_table.empty:
        g1, g2 = st.columns([1.3, 1], gap="small")
        with g1:
            usage_fig = go.Figure()
            usage_fig.add_bar(
                x=match_table["match_ts"],
                y=match_table["rounds_used"],
                name="Rounds Used",
                marker_color="#53a7ff",
            )
            usage_fig.add_scatter(
                x=match_table["match_ts"],
                y=match_table["win_rate_pct"],
                name="Win Rate %",
                yaxis="y2",
                mode="lines+markers",
                line=dict(color="#9FE870", width=2),
            )
            usage_fig.update_layout(
                template="plotly_dark",
                margin=dict(l=8, r=8, t=8, b=8),
                height=360 if not mobile_view else 300,
                yaxis=dict(title="Rounds Used"),
                yaxis2=dict(title="Win Rate %", overlaying="y", side="right", range=[0, 100]),
            )
            st.plotly_chart(usage_fig, use_container_width=True)
        with g2:
            opp_perf = (
                match_table.groupby("opponent", dropna=False)
                .agg(matches=("match_id", "count"), rounds_won=("rounds_won", "sum"), rounds_used=("rounds_used", "sum"))
                .reset_index()
            )
            opp_perf["win_rate_pct"] = (opp_perf["rounds_won"] / opp_perf["rounds_used"].clip(lower=1) * 100).fillna(0)
            opp_perf = opp_perf.sort_values("win_rate_pct", ascending=False)
            opp_fig = px.bar(
                opp_perf,
                x="win_rate_pct",
                y="opponent",
                orientation="h",
                color="matches",
                color_continuous_scale="Tealgrn",
                labels={"win_rate_pct": "Win Rate %", "opponent": "Opponent"},
            )
            opp_fig.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=360 if not mobile_view else 300)
            st.plotly_chart(opp_fig, use_container_width=True)

        g3, g4 = st.columns([1, 1], gap="small")
        with g3:
            tier_perf = (
                match_table.assign(tier=normalize_tier_values(match_table["tier"]).fillna("C"))
                .groupby("tier", dropna=False)
                .agg(matches=("match_id", "count"), rounds_won=("rounds_won", "sum"), rounds_used=("rounds_used", "sum"))
                .reindex(TIER_ORDER, fill_value=0)
                .rename_axis("tier")
                .reset_index()
            )
            tier_perf["win_rate_pct"] = (tier_perf["rounds_won"] / tier_perf["rounds_used"].clip(lower=1) * 100).fillna(0)
            tier_perf["tier_label"] = tier_perf["tier"].map(lambda tier: f"{tier} Tier")
            tier_fig = px.bar(
                tier_perf,
                x="tier",
                y="win_rate_pct",
                color="tier",
                text=tier_perf["win_rate_pct"].map(lambda val: f"{val:.1f}%"),
                category_orders={"tier": TIER_ORDER},
                color_discrete_map=TIER_COLORS,
                labels={"tier": "Tier", "win_rate_pct": "Win Rate %"},
                hover_data={"matches": True, "tier_label": True, "tier": False},
            )
            tier_fig.update_traces(
                marker_line_width=1.25,
                marker_line_color="#0f1823",
                textposition="outside",
                cliponaxis=False,
            )
            tier_fig.update_layout(
                template="plotly_dark",
                margin=dict(l=8, r=8, t=8, b=8),
                height=310 if not mobile_view else 270,
                legend_title_text="Tier",
                showlegend=True,
                yaxis=dict(range=[0, max(100, float(tier_perf["win_rate_pct"].max()) + 8)]),
            )
            st.plotly_chart(tier_fig, use_container_width=True)
        with g4:
            comp_perf = (
                match_table.groupby("competition", dropna=False)
                .agg(matches=("match_id", "count"), rounds_won=("rounds_won", "sum"), rounds_used=("rounds_used", "sum"))
                .reset_index()
            )
            comp_perf["win_rate_pct"] = (comp_perf["rounds_won"] / comp_perf["rounds_used"].clip(lower=1) * 100).fillna(0)
            comp_perf = comp_perf.sort_values(["matches", "win_rate_pct"], ascending=[False, False]).head(10)
            comp_fig = px.bar(
                comp_perf,
                x="competition",
                y="win_rate_pct",
                color="matches",
                labels={"competition": "Competition", "win_rate_pct": "Win Rate %"},
            )
            comp_fig.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=310 if not mobile_view else 270, xaxis_tickangle=-30)
            st.plotly_chart(comp_fig, use_container_width=True)
    elif not PLOTLY_AVAILABLE:
        st.warning("Plotly unavailable in this environment; tactic-specific drill-down charts are disabled.")

    st.markdown("<div class='section-title' style='margin-top:8px;'>Selected Tactic Match History</div>", unsafe_allow_html=True)
    columns_order = [
        "date",
        "time",
        "competition",
        "map",
        "side",
        "opponent",
        "tier",
        "rounds_used",
        "rounds_won",
        "win_rate_pct",
        "match_id",
    ]
    if match_result_col:
        columns_order.insert(10, match_result_col)
    if team_score_col:
        columns_order.insert(11, team_score_col)
    if opp_score_col:
        columns_order.insert(12, opp_score_col)
    present_cols = [c for c in columns_order if c in match_table.columns]
    pretty_table = match_table[present_cols].rename(
        columns={
            "date": "Date",
            "time": "Time",
            "competition": "Competition",
            "map": "Map",
            "side": "Side",
            "opponent": "Opponent",
            "tier": "Tier",
            "rounds_used": "Rounds Used",
            "rounds_won": "Rounds Won",
            "win_rate_pct": "Win Rate %",
            "match_id": "match_id",
            "derived_result": "Match Result",
            "match_result": "Match Result",
            "result": "Match Result",
            "team_score": "Team Score",
            "my_team_score": "Team Score",
            "score_for": "Team Score",
            "our_score": "Team Score",
            "opponent_score": "Opponent Score",
            "opp_score": "Opponent Score",
            "score_against": "Opponent Score",
        }
    )
    st.dataframe(pretty_table, use_container_width=True, hide_index=True)


def render(ctx):
    _render_tactics_breakdown(ctx, recent_mode=False)


def render_recent(ctx):
    _render_tactics_breakdown(ctx, recent_mode=True)
