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
    TIER_ORDER,
    attach_normalized_tier,
    normalize_tier_values,
    tactic_category,
    weighted_tactical_win_rate,
    weighted_tier_round_share,
)
TEST_STATUS_ORDER = [
    "Promising",
    "Keep Trialing",
    "Test More",
    "Too Early To Judge",
    "Early Warning",
    "Weak Start",
    "Candidate Drop",
]
TEST_STATUS_CLASS = {
    "Promising": "good",
    "Keep Trialing": "good",
    "Test More": "mid",
    "Too Early To Judge": "mid",
    "Early Warning": "poor",
    "Weak Start": "poor",
    "Candidate Drop": "bad",
}


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _fmt_signed(value: float) -> str:
    return f"{float(value):+.1f}pp"


def _manual_exclusion_key(map_name: str, side: str) -> str:
    return f"tsr_excluded::{map_name}::{side}"


def _get_excluded_for_context(map_name: str, side: str, available: set[str]) -> set[str]:
    key = _manual_exclusion_key(map_name, side)
    stored = set(st.session_state.get(key, []))
    return {name for name in stored if name in available}


def _set_excluded_for_context(map_name: str, side: str, excluded: set[str]) -> None:
    key = _manual_exclusion_key(map_name, side)
    st.session_state[key] = sorted(excluded)


def _inject_page_css() -> None:
    st.markdown(
        """
        <style>
        .testing-hero-title{font-size:1.22rem;margin:0;color:#f5fbff;letter-spacing:.02em;}
        .testing-hero-subtitle{margin:.3rem 0 0;font-size:.82rem;color:#9fb0c4;max-width:920px;}
        .testing-command{padding:.7rem;margin-top:.6rem;}
        .testing-card{border:1px solid #2d3e51;background:linear-gradient(180deg,#122031,#0d1825);border-radius:8px;padding:.62rem;min-height:210px;}
        .testing-card.selected{border-color:#9FE870;box-shadow:0 0 0 1px rgba(159,232,112,.35),0 0 18px rgba(159,232,112,.16);}
        .testing-pill{display:inline-block;font-size:.56rem;letter-spacing:.11em;text-transform:uppercase;padding:2px 7px;border-radius:999px;border:1px solid #42596f;margin-top:6px;}
        .testing-pill.good{color:#9FE870;border-color:#4a7242;background:#1a2b1b;}
        .testing-pill.mid{color:#d3a85c;border-color:#78603b;background:#2a2418;}
        .testing-pill.poor{color:#ff9f43;border-color:#865830;background:#2a1f14;}
        .testing-pill.bad{color:#ff4d5e;border-color:#7a3540;background:#2a171d;}
        .testing-pill.excluded{color:#f7c6ce;border-color:#7a3540;background:#2a171d;}
        .testing-mini{font-size:.64rem;color:#94a6bb;margin-top:4px;}
        .testing-reason{margin-top:8px;font-size:.68rem;color:#d2deea;line-height:1.35;}
        .testing-status-group{margin-top:10px;border:1px solid #2f4155;border-radius:10px;background:linear-gradient(180deg,#101a27,#0c1521);padding:.7rem;}
        .testing-status-header{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;}
        .testing-status-header h3{margin:0;font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:#d6e3f2;}
        .testing-status-meta{font-size:.64rem;color:#95a8bc;}
        .testing-tier-row{margin-top:7px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;}
        .testing-tier-box{border:1px solid #354b61;border-radius:6px;background:#111d2b;padding:4px 5px;min-height:46px;}
        .testing-tier-name{display:block;font-size:.55rem;text-transform:uppercase;letter-spacing:.08em;color:#91a7c0;}
        .testing-tier-score{display:block;font-size:.73rem;color:#edf4ff;font-weight:700;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_logic(row: pd.Series) -> tuple[str, str, str]:
    rounds = float(row["rounds"])
    wr = float(row["recent_wr"])
    weighted_delta = float(row["weighted_wr"] - row["baseline_wr"])
    s_delta = float(row["s_tier_delta"])
    tier_focus = float(row["high_tier_round_share"])
    c_inflation = float(row["c_tier_inflation"])

    if rounds <= 3:
        return "Too Early To Judge", "No", "Sample is tiny; one result swing can invert this read."
    if rounds <= 5 and weighted_delta >= 8 and s_delta >= 2 and wr >= 58:
        return "Keep Trialing", "Yes", "Early signal is strong vs S/A/B-weighted opposition; schedule controlled reps."
    if rounds <= 5 and weighted_delta <= -10:
        return "Early Warning", "No", "Early weighted return is materially below baseline; revise before more exposure."
    if weighted_delta >= 9 and wr >= 60 and s_delta >= 3:
        return "Promising", "Yes", "Strong early return against higher-tier opposition, led by S-tier signal."
    if weighted_delta >= 4 and wr >= 52:
        return "Test More", "Yes", "Above weighted baseline so far; add reps to separate signal from noise."
    if weighted_delta <= -15 and rounds >= 8:
        return "Candidate Drop", "No", "Weak start has persisted on weighted high-tier evidence; de-prioritize."
    if weighted_delta <= -8 or s_delta <= -10:
        return "Weak Start", "No", "Under baseline versus stronger tiers in early testing; refine setup before scaling."
    if tier_focus >= 0.55 and weighted_delta >= 0:
        return "Keep Trialing", "Yes", "Holding at/above baseline despite substantial S/A/B weighted exposure."
    if c_inflation > 8:
        return "Too Early To Judge", "Yes", "Most upside is C-tier inflated; need stronger-tier reps before confidence rises."
    return "Too Early To Judge", "Yes", "Mixed low-sample profile; continue selective trials for clarity."


def _tier_box(tier: str, value: float | None) -> str:
    display = _fmt_pct(value) if pd.notna(value) else "N/A"
    return (
        "<div class='testing-tier-box'>"
        f"<span class='testing-tier-name'>vs {tier}</span>"
        f"<span class='testing-tier-score'>{display}</span>"
        "</div>"
    )


def _prepare_tactics(tdf: pd.DataFrame, days_window: int) -> pd.DataFrame:
    tdf = tdf.copy()
    tdf["map"] = tdf.get("map", "Unknown").astype(str).str.strip().replace("", "Unknown")
    tdf["side"] = tdf.get("side", "Unknown").astype(str).str.strip().replace("", "Unknown")
    tdf["tactic_name"] = tdf.get("tactic_name", "Unknown Tactic").astype(str).str.strip().replace("", "Unknown Tactic")
    tdf["wins"] = pd.to_numeric(tdf.get("wins", 0), errors="coerce").fillna(0)
    tdf["losses"] = pd.to_numeric(tdf.get("losses", 0), errors="coerce").fillna(0)
    tdf["total_rounds"] = pd.to_numeric(tdf.get("total_rounds", 0), errors="coerce").fillna(0)
    tdf["competition"] = tdf.get("competition", "Unknown").astype(str).str.strip().replace("", "Unknown")
    tdf["category"] = tdf["tactic_name"].map(tactic_category)
    tdf["tactic_type"] = tdf["category"].replace({"Standard": "Standard", "Eco": "Eco", "Pistol": "Pistol"})

    tdf = attach_normalized_tier(tdf, fallback="C")
    date_ser = tdf.get("date", pd.Series([None] * len(tdf), index=tdf.index))
    time_ser = normalize_time_series(tdf.get("time", pd.Series([None] * len(tdf), index=tdf.index)))
    tdf["time"] = time_ser
    tdf["match_ts"] = build_match_timestamp(date_ser, time_ser)
    tdf["match_ts"] = tdf["match_ts"].fillna(build_match_timestamp(date_ser))

    newest = tdf["match_ts"].max()
    cut = newest - pd.Timedelta(days=int(days_window))
    return tdf[tdf["match_ts"] >= cut].copy()


def render(ctx):
    tdf = ctx["tactics"].copy()
    mobile_view = is_mobile_view()

    if tdf.empty:
        st.warning("No tactics data after current global filters.")
        return

    _inject_page_css()

    st.markdown(
        f"""
        <div class='hero-band'>
            <div class='section-title'>Tactical Testing Lab</div>
            <h1 class='testing-hero-title'>Testing Tactics</h1>
            <p class='testing-hero-subtitle'>
                Fresh-tactic analyst board for recently used, low-sample map+side tactics. Designed to quickly classify what looks promising,
                what needs more reps, what should be refined, and what may be dropped.
            </p>
            <div style='margin-top:6px;'>
                <span class='chip chip-good'>Low-sample focus</span>
                <span class='chip chip-mid'>Recent window only</span>
                <span class='chip chip-poor'>Map + side specific judgement</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='panel testing-command'>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1.2, 1.1], gap="small")
    with c1:
        days_window = st.slider("Last N Days", min_value=1, max_value=14, value=7, step=1)
    with c2:
        max_rounds = st.slider("Max Rounds", min_value=4, max_value=40, value=25, step=1)
    with c3:
        tactic_type = st.segmented_control("Type", options=["All", "Standard", "Eco", "Pistol"], default="All")
    with c4:
        selected_tiers = st.multiselect("Opponent Tier", options=TIER_ORDER, default=TIER_ORDER)

    scoped_recent = _prepare_tactics(tdf, days_window=days_window)
    map_options = ["All"] + sorted(scoped_recent["map"].dropna().unique().tolist())
    side_options = ["All"] + sorted(scoped_recent["side"].dropna().unique().tolist())
    with c5:
        selected_map = st.selectbox("Map", options=map_options, index=0)
    with c6:
        selected_side = st.selectbox("Side", options=side_options, index=0)
    st.markdown("</div>", unsafe_allow_html=True)

    scoped = scoped_recent.copy()
    if tactic_type != "All":
        scoped = scoped[scoped["tactic_type"] == tactic_type].copy()
    if selected_tiers:
        scoped = scoped[scoped["tier"].isin(selected_tiers)].copy()
    if selected_map != "All":
        scoped = scoped[scoped["map"] == selected_map].copy()
    if selected_side != "All":
        scoped = scoped[scoped["side"] == selected_side].copy()

    if scoped.empty:
        st.warning("No tactics found in the selected recent window and filters.")
        return

    group_cols = ["map", "side", "tactic_name", "category", "tactic_type"]
    tactical = (
        scoped.groupby(group_cols, dropna=False)
        .agg(
            wins=("wins", "sum"),
            losses=("losses", "sum"),
            rounds=("total_rounds", "sum"),
            last_used=("match_ts", "max"),
            first_used=("match_ts", "min"),
        )
        .reset_index()
    )

    tactical = tactical[(tactical["rounds"] > 0) & (tactical["rounds"] <= int(max_rounds))].copy()
    if tactical.empty:
        st.warning("No low-sample tactics in the recent window meet the Max Rounds threshold.")
        return

    tactical["recent_wr"] = (tactical["wins"] / (tactical["wins"] + tactical["losses"]).clip(lower=1) * 100).fillna(0)
    tactical["last_used_label"] = tactical["last_used"].dt.strftime("%Y-%m-%d").fillna("N/A")

    baseline = (
        scoped.groupby(["map", "side"], dropna=False)
        .agg(base_wins=("wins", "sum"), base_losses=("losses", "sum"))
        .reset_index()
    )
    baseline["baseline_wr"] = (baseline["base_wins"] / (baseline["base_wins"] + baseline["base_losses"]).clip(lower=1) * 100).fillna(0)
    tactical = tactical.merge(baseline[["map", "side", "baseline_wr"]], on=["map", "side"], how="left")
    tactical["delta_vs_baseline"] = tactical["recent_wr"] - tactical["baseline_wr"]

    tier_view = (
        scoped.groupby(group_cols + ["tier"], dropna=False)
        .agg(twins=("wins", "sum"), tlosses=("losses", "sum"), trounds=("total_rounds", "sum"))
        .reset_index()
    )
    tier_view["tier_wr"] = (tier_view["twins"] / (tier_view["twins"] + tier_view["tlosses"]).clip(lower=1) * 100).fillna(0)
    tier_pivot = tier_view.pivot_table(index=group_cols, columns="tier", values="tier_wr", aggfunc="mean").reset_index()
    for tier in TIER_ORDER:
        if tier not in tier_pivot.columns:
            tier_pivot[tier] = np.nan
    tactical = tactical.merge(tier_pivot[group_cols + TIER_ORDER], on=group_cols, how="left")

    tier_wins = tier_view.pivot_table(index=group_cols, columns="tier", values="twins", aggfunc="sum", fill_value=0).reset_index()
    tier_losses = tier_view.pivot_table(index=group_cols, columns="tier", values="tlosses", aggfunc="sum", fill_value=0).reset_index()
    for tier in TIER_ORDER:
        if tier not in tier_wins.columns:
            tier_wins[tier] = 0.0
        if tier not in tier_losses.columns:
            tier_losses[tier] = 0.0
    tier_wins = tier_wins.rename(columns={tier: f"{tier}_wins" for tier in TIER_ORDER})
    tier_losses = tier_losses.rename(columns={tier: f"{tier}_losses" for tier in TIER_ORDER})
    tactical = tactical.merge(tier_wins[group_cols + [f"{tier}_wins" for tier in TIER_ORDER]], on=group_cols, how="left")
    tactical = tactical.merge(tier_losses[group_cols + [f"{tier}_losses" for tier in TIER_ORDER]], on=group_cols, how="left")
    tactical["weighted_wr"] = weighted_tactical_win_rate(tactical, fallback_wr_col="recent_wr")
    tier_rounds = tier_view.pivot_table(index=group_cols, columns="tier", values="trounds", aggfunc="sum", fill_value=0).reset_index()
    for tier in TIER_ORDER:
        if tier not in tier_rounds.columns:
            tier_rounds[tier] = 0
    tactical = tactical.merge(tier_rounds[group_cols + TIER_ORDER], on=group_cols, how="left", suffixes=("", "_rounds"))
    tactical["high_tier_round_share"] = weighted_tier_round_share(tactical, tiers=("S", "A", "B"))
    tactical["s_tier_delta"] = tactical["S"].fillna(tactical["recent_wr"]) - tactical["baseline_wr"]
    tactical["c_tier_inflation"] = (tactical["C"].fillna(tactical["recent_wr"]) - tactical["weighted_wr"]).clip(lower=0)

    status_frame = tactical.apply(_status_logic, axis=1, result_type="expand")
    tactical[["status", "keep_testing", "reason"]] = status_frame

    tactical["tactic_uid"] = tactical.apply(lambda row: f"{row['map']}||{row['side']}||{row['tactic_name']}", axis=1)
    selection_key = "testing_tactics_selected_tactic_uid"
    if selection_key not in st.session_state:
        st.session_state[selection_key] = None
    if st.session_state[selection_key] not in set(tactical["tactic_uid"]):
        st.session_state[selection_key] = tactical.sort_values(["status", "delta_vs_baseline"], ascending=[True, False]).iloc[0]["tactic_uid"]

    available_names_by_context = tactical.groupby(["map", "side"], dropna=False)["tactic_name"].apply(lambda names: set(names.astype(str))).to_dict()
    excluded_by_context = {
        context: _get_excluded_for_context(context[0], context[1], names) for context, names in available_names_by_context.items()
    }
    tactical["is_excluded"] = tactical.apply(
        lambda row: str(row["tactic_name"]) in excluded_by_context.get((str(row["map"]), str(row["side"])), set()),
        axis=1,
    )

    m1, m2, m3, m4, m5 = st.columns(5, gap="small")
    m1.markdown(f"<div class='panel panel-tight accent-good'><div class='metric-title'>Testing Tactics</div><div class='metric-value'>{len(tactical)}</div><div class='muted'>low-sample + recent</div></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='panel panel-tight accent-mid'><div class='metric-title'>Promising / Keep</div><div class='metric-value'>{int(tactical['status'].isin(['Promising','Keep Trialing']).sum())}</div><div class='muted'>continue development</div></div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='panel panel-tight accent-poor'><div class='metric-title'>Too Early</div><div class='metric-value'>{int((tactical['status'] == 'Too Early To Judge').sum())}</div><div class='muted'>sample still thin</div></div>", unsafe_allow_html=True)
    m4.markdown(f"<div class='panel panel-tight accent-bad'><div class='metric-title'>Weak / Drop</div><div class='metric-value'>{int(tactical['status'].isin(['Weak Start','Candidate Drop']).sum())}</div><div class='muted'>refine or remove</div></div>", unsafe_allow_html=True)
    m5.markdown(f"<div class='panel panel-tight accent-mid'><div class='metric-title'>Window Rounds</div><div class='metric-value'>{int(tactical['rounds'].sum())}</div><div class='muted'>tracked recent rounds</div></div>", unsafe_allow_html=True)

    if PLOTLY_AVAILABLE:
        v1, v2 = st.columns([1.2, 1], gap="small")
        with v1:
            scatter = px.scatter(
                tactical,
                x="rounds",
                y="recent_wr",
                color="status",
                size="rounds",
                hover_name="tactic_name",
                hover_data={"map": True, "side": True, "delta_vs_baseline": ":.1f", "baseline_wr": ":.1f"},
                category_orders={"status": TEST_STATUS_ORDER},
            )
            scatter.add_hline(y=float(tactical["baseline_wr"].mean()), line_dash="dot", line_color="#9fb4ca")
            scatter.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=380 if not mobile_view else 320)
            st.plotly_chart(scatter, use_container_width=True)
        with v2:
            recent_board = tactical.sort_values(["last_used", "rounds"], ascending=[False, False]).head(14).copy()
            timeline = px.bar(
                recent_board,
                x="last_used",
                y="tactic_name",
                orientation="h",
                color="status",
                category_orders={"status": TEST_STATUS_ORDER},
                hover_data={"map": True, "side": True, "rounds": True, "recent_wr": ":.1f"},
            )
            timeline.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=380 if not mobile_view else 320)
            st.plotly_chart(timeline, use_container_width=True)

        v3, v4 = st.columns(2, gap="small")
        with v3:
            tier_status = tactical.groupby("status", dropna=False).agg(tactics=("tactic_name", "count"), rounds=("rounds", "sum")).reset_index()
            status_fig = px.bar(
                tier_status,
                x="status",
                y="tactics",
                color="rounds",
                category_orders={"status": TEST_STATUS_ORDER},
                labels={"tactics": "Tactic Count", "status": "Testing Status"},
            )
            status_fig.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=320 if not mobile_view else 280, xaxis_tickangle=-20)
            st.plotly_chart(status_fig, use_container_width=True)
        with v4:
            tier_perf = (
                scoped.groupby("tier", dropna=False)
                .agg(rounds=("total_rounds", "sum"), wins=("wins", "sum"), losses=("losses", "sum"))
                .reindex(TIER_ORDER, fill_value=0)
                .rename_axis("tier")
                .reset_index()
            )
            tier_perf["wr"] = (tier_perf["wins"] / (tier_perf["wins"] + tier_perf["losses"]).clip(lower=1) * 100).fillna(0)
            tier_fig = px.bar(
                tier_perf,
                x="tier",
                y="wr",
                color="tier",
                category_orders={"tier": TIER_ORDER},
                color_discrete_map=TIER_COLORS,
                labels={"wr": "Win Rate %", "tier": "Tier"},
                hover_data={"rounds": True},
            )
            tier_fig.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=320 if not mobile_view else 280)
            st.plotly_chart(tier_fig, use_container_width=True)

    st.markdown("<div class='section-title' style='margin-top:8px;'>Testing Status Board</div>", unsafe_allow_html=True)
    per_group = 3 if not mobile_view else 2
    for status in TEST_STATUS_ORDER:
        block = tactical[tactical["status"] == status].sort_values(["delta_vs_baseline", "recent_wr", "last_used"], ascending=[False, False, False])
        if block.empty:
            continue
        st.markdown(
            f"<div class='testing-status-group'><div class='testing-status-header'><h3>{status}</h3><div class='testing-status-meta'>{len(block)} tactics in current scope</div></div></div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(3 if not mobile_view else 1, gap="small")
        for idx, row in block.head(per_group).reset_index(drop=True).iterrows():
            with cols[idx % len(cols)]:
                selected = st.session_state[selection_key] == row["tactic_uid"]
                selected_class = " selected" if selected else ""
                excluded = bool(row["is_excluded"])
                excluded_badge = "<div class='testing-pill excluded'>Excluded</div>" if excluded else ""
                st.markdown(
                    f"<div class='testing-card{selected_class}'><h4>{row['tactic_name']}</h4>"
                    f"<div class='testing-pill {TEST_STATUS_CLASS.get(status, 'mid')}'>{row['status']}</div>"
                    f"{excluded_badge}"
                    f"<div class='testing-mini'>{row['tactic_type']} • {row['map']} • {row['side']}</div>"
                    f"<div class='testing-mini'>Rounds {int(row['rounds'])} • WR {_fmt_pct(row['recent_wr'])} • Δ {_fmt_signed(row['delta_vs_baseline'])}</div>"
                    f"<div class='testing-mini'>Won {int(row['wins'])} / Lost {int(row['losses'])} • Last used {row['last_used_label']}</div>"
                    f"<div class='testing-mini'>Keep Testing? {row['keep_testing']}</div>"
                    f"<div class='testing-tier-row'>{_tier_box('S', row['S'])}{_tier_box('A', row['A'])}{_tier_box('B', row['B'])}{_tier_box('C', row['C'])}</div>"
                    f"<div class='testing-reason'>{row['reason']}</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Inspect tactic" if not selected else "Selected • viewing below",
                    key=f"testing_pick_{status}_{idx}_{row['tactic_uid']}",
                    use_container_width=True,
                    type="primary" if selected else "secondary",
                ):
                    st.session_state[selection_key] = row["tactic_uid"]
                action_label = "Re-include tactic" if excluded else "Exclude tactic"
                if st.button(action_label, key=f"testing_ex_{status}_{idx}_{row['tactic_uid']}", use_container_width=True):
                    context_key = (str(row["map"]), str(row["side"]))
                    current = set(excluded_by_context.get(context_key, set()))
                    name = str(row["tactic_name"])
                    if excluded:
                        current.discard(name)
                    else:
                        current.add(name)
                    excluded_by_context[context_key] = current
                    _set_excluded_for_context(context_key[0], context_key[1], current)
                    st.rerun()

    st.markdown("<div class='section-title' style='margin-top:10px;'>Recent Testing Grid</div>", unsafe_allow_html=True)
    table = tactical[
        [
            "tactic_name",
            "tactic_type",
            "map",
            "side",
            "rounds",
            "recent_wr",
            "wins",
            "losses",
            "last_used_label",
            "S",
            "A",
            "B",
            "C",
            "status",
            "reason",
            "keep_testing",
        ]
    ].rename(
        columns={
            "tactic_name": "Tactic",
            "tactic_type": "Type",
            "map": "Map",
            "side": "Side",
            "rounds": "Recent Rounds",
            "recent_wr": "Recent WR",
            "wins": "Rounds Won",
            "losses": "Rounds Lost",
            "last_used_label": "Last Used",
            "reason": "Reason",
            "keep_testing": "Keep Testing?",
        }
    )
    st.dataframe(table.sort_values(["Recent Rounds", "Recent WR"], ascending=[False, False]), use_container_width=True, hide_index=True)

    selected_uid = st.session_state.get(selection_key)
    selected = tactical[tactical["tactic_uid"] == selected_uid]
    if selected.empty:
        return
    one = selected.iloc[0]

    st.markdown("<div class='section-title' style='margin-top:10px;'>Inspect Tactic • Recent Window Drill-down</div>", unsafe_allow_html=True)
    st.caption(f"Context locked to {one['map']} • {one['side']} • Last {days_window} days")

    tactic_matches = scoped[
        (scoped["tactic_name"] == one["tactic_name"]) & (scoped["map"] == one["map"]) & (scoped["side"] == one["side"])
    ].copy()
    tactic_matches["opponent"] = tactic_matches.get("opponent_team", "Unknown").astype(str).str.strip().replace("", "Unknown")

    match_table = (
        tactic_matches.groupby(["match_id", "date", "time", "match_ts"], dropna=False)
        .agg(
            competition=("competition", "first"),
            opponent=("opponent", "first"),
            tier=("tier", "first"),
            rounds_used=("total_rounds", "sum"),
            rounds_won=("wins", "sum"),
            rounds_lost=("losses", "sum"),
        )
        .reset_index()
        .sort_values(["match_ts", "match_id"], ascending=[False, False])
    )
    match_table["win_rate_pct"] = (match_table["rounds_won"] / match_table["rounds_used"].clip(lower=1) * 100).fillna(0)

    d1, d2, d3 = st.columns(3, gap="small")
    d1.markdown(
        f"<div class='panel panel-tight'><div class='metric-title'>Selected Testing Tactic</div><div class='metric-value'>{one['tactic_name']}</div><div class='muted'>{one['map']} • {one['side']} • {one['tactic_type']}</div></div>",
        unsafe_allow_html=True,
    )
    d2.markdown(
        f"<div class='panel panel-tight'><div class='metric-title'>Recent Window Result</div><div class='metric-value'>{_fmt_pct(one['recent_wr'])}</div><div class='muted'>Rounds {int(one['rounds'])} • Baseline {_fmt_pct(one['baseline_wr'])} • Δ {_fmt_signed(one['delta_vs_baseline'])}</div></div>",
        unsafe_allow_html=True,
    )
    d3.markdown(
        f"<div class='panel panel-tight'><div class='metric-title'>Testing Verdict</div><div class='metric-value' style='font-size:1rem'>{one['status']}</div><div class='muted'>{one['reason']}</div></div>",
        unsafe_allow_html=True,
    )

    if PLOTLY_AVAILABLE and not match_table.empty:
        g1, g2 = st.columns(2, gap="small")
        with g1:
            usage = go.Figure()
            usage.add_bar(x=match_table["match_ts"], y=match_table["rounds_used"], name="Rounds Used", marker_color="#53a7ff")
            usage.add_scatter(
                x=match_table["match_ts"],
                y=match_table["win_rate_pct"],
                name="Win Rate %",
                yaxis="y2",
                mode="lines+markers",
                line=dict(color="#9FE870", width=2),
            )
            usage.update_layout(
                template="plotly_dark",
                margin=dict(l=8, r=8, t=8, b=8),
                height=320 if not mobile_view else 280,
                yaxis=dict(title="Rounds Used"),
                yaxis2=dict(title="Win Rate %", overlaying="y", side="right", range=[0, 100]),
            )
            st.plotly_chart(usage, use_container_width=True)
        with g2:
            tier_roll = (
                match_table.assign(tier=normalize_tier_values(match_table["tier"]).fillna("C"))
                .groupby("tier", dropna=False)
                .agg(matches=("match_id", "count"), rounds_won=("rounds_won", "sum"), rounds_used=("rounds_used", "sum"))
                .reindex(TIER_ORDER, fill_value=0)
                .rename_axis("tier")
                .reset_index()
            )
            tier_roll["wr"] = (tier_roll["rounds_won"] / tier_roll["rounds_used"].clip(lower=1) * 100).fillna(0)
            tfig = px.bar(
                tier_roll,
                x="tier",
                y="wr",
                color="tier",
                category_orders={"tier": TIER_ORDER},
                color_discrete_map=TIER_COLORS,
                labels={"tier": "Tier", "wr": "Win Rate %"},
                hover_data={"matches": True},
            )
            tfig.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), height=320 if not mobile_view else 280)
            st.plotly_chart(tfig, use_container_width=True)

    st.dataframe(
        match_table[
            [
                "date",
                "time",
                "competition",
                "opponent",
                "tier",
                "rounds_used",
                "rounds_won",
                "rounds_lost",
                "win_rate_pct",
                "match_id",
            ]
        ].rename(
            columns={
                "date": "Date",
                "time": "Time",
                "competition": "Competition",
                "opponent": "Opponent",
                "tier": "Tier",
                "rounds_used": "Rounds Used",
                "rounds_won": "Rounds Won",
                "rounds_lost": "Rounds Lost",
                "win_rate_pct": "Win Rate %",
                "match_id": "match_id",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
