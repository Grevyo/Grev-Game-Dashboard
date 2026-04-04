import numpy as np
import pandas as pd
import streamlit as st
import re

try:
    import plotly.express as px
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

from app.page_layout import is_mobile_view
from app.datetime_utils import build_match_timestamp, normalize_time_series
from app.tactics import (
    TACTICAL_TIER_WEIGHTS,
    TIER_ORDER,
    attach_normalized_tier,
    tactic_category,
    weighted_tactical_win_rate,
    weighted_tier_round_share,
)

EXCLUDE_FOR_NOW_STATUS = "Exclude For Now"
EXCLUDE_FOR_NOW_DISPLAY = "Try Build Replacement"


def _display_status(status: str | None) -> str:
    value = str(status or "")
    return EXCLUDE_FOR_NOW_DISPLAY if value == EXCLUDE_FOR_NOW_STATUS else value


STATUS_ORDER = [
    "Locked In",
    "Strong Pick",
    "Viable",
    "Situational",
    "Test More",
    "Backup",
    EXCLUDE_FOR_NOW_STATUS,
]
STATUS_TONE = {
    "Locked In": "good",
    "Strong Pick": "good",
    "Viable": "mid",
    "Situational": "mid",
    "Test More": "poor",
    "Backup": "poor",
    EXCLUDE_FOR_NOW_STATUS: "bad",
}
STRONG_COVERAGE_STATUSES = {"Locked In", "Strong Pick"}
WEAK_COVERAGE_STATUSES = {"Situational", "Risky", "Drop", "Backup", EXCLUDE_FOR_NOW_STATUS}
TIER_COLORS = {"S": "#d4b15d", "A": "#9b6ef3", "B": "#4d8dff", "C": "#59b67a"}
REQUIRED_CORE_BUCKETS = ["Pistol", "Eco A", "Eco B", "Standard A", "Standard B"]
SPLIT_STYLE_LABEL = "AB / BA Split"
SPLIT_STYLE_PATTERNS = [
    r"(?<![A-Z0-9])AB(?![A-Z0-9])",
    r"(?<![A-Z0-9])BA(?![A-Z0-9])",
    r"(?<![A-Z0-9])A\s*[/_-]\s*B(?![A-Z0-9])",
    r"(?<![A-Z0-9])B\s*[/_-]\s*A(?![A-Z0-9])",
]
MAP_OPTIONAL_BUCKETS = {
    "train": ["Ivy", "Apps", "Connector"],
    "castle": ["Mid", "B Halls", "B Doors", "A Main"],
    "mill": ["Mid", "A Halls", "A Long", "B Long", "2nd Mid"],
}
MAP_OPTIONAL_PATTERNS = {
    "train": {
        "Ivy": [r"\bIVY\b"],
        "Apps": [r"\bAPPS?\b"],
        "Connector": [r"\bCONNECTOR\b", r"\bCONN\b", r"\bCON\b"],
    },
    "castle": {
        "Mid": [r"\bMID\b"],
        "B Halls": [r"\bB[\s\-_]*HALLS?\b"],
        "B Doors": [r"\bB[\s\-_]*DOORS?\b"],
        "A Main": [r"\bA[\s\-_]*MAIN\b"],
    },
    "mill": {
        "2nd Mid": [r"\b2ND[\s\-_]*MID\b", r"\bB[\s\-_]*MID\b"],
        "Mid": [r"\bMID\b"],
        "A Halls": [r"\bA[\s\-_]*(HALLS?|TUNS?|TUNNELS?)\b"],
        "A Long": [r"\bA[\s\-_]*LONG\b"],
        "B Long": [r"\bB[\s\-_]*LONG\b"],
    },
}


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _fmt_signed(value: float) -> str:
    return f"{float(value):+.1f}pp"


def _fmt_tier_pct(value: float) -> str:
    return "N/A" if pd.isna(value) else _fmt_pct(value)


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


def _canonical_map_name(map_name: str) -> str:
    return str(map_name).strip().lower()


def _has_lane_token(name: str, lane: str) -> bool:
    return bool(re.search(rf"\b{lane}\b", str(name).upper()))


def _has_lane_hint(name: str, lane: str) -> bool:
    norm = str(name).upper()
    return bool(re.search(rf"(?<![A-Z0-9]){lane}(?:\d+)?(?![A-Z])", norm))


def _role_to_core_bucket(role: str) -> str | None:
    return {
        "Pistol": "Pistol",
        "Eco A": "Eco A",
        "Eco B": "Eco B",
        "Standard A": "Standard A",
        "Standard B": "Standard B",
    }.get(str(role))


def _infer_core_bucket(name: str) -> str:
    n = str(name).upper()
    if "PISTOL" in n or "(P)" in n or re.match(r"^\s*P[\s\-_]", n):
        return "Pistol"
    if "ECO" in n or "(E)" in n or re.match(r"^\s*E[\s\-_]", n):
        if _has_lane_hint(n, "A"):
            return "Eco A"
        if _has_lane_hint(n, "B"):
            return "Eco B"
        return "Eco"
    if _has_lane_hint(n, "A") and not _has_lane_hint(n, "B"):
        return "Standard A"
    if _has_lane_hint(n, "B") and not _has_lane_hint(n, "A"):
        return "Standard B"
    return "Standard"


def _infer_optional_buckets(name: str, map_name: str) -> list[str]:
    map_key = _canonical_map_name(map_name)
    config = MAP_OPTIONAL_PATTERNS.get(map_key, {})
    norm_name = str(name).upper()
    matched: list[str] = []
    for bucket, patterns in config.items():
        if any(re.search(pattern, norm_name) for pattern in patterns):
            matched.append(bucket)
    return matched


def _is_split_site_tactic(name: str) -> bool:
    norm_name = str(name).upper()
    if any(re.search(pattern, norm_name) for pattern in SPLIT_STYLE_PATTERNS):
        return True

    # Also catch compact/segmented shorthand in tactic tokens (e.g., "[AB]", "A_B", "BA-").
    normalized = re.sub(r"[^A-Z0-9]+", " ", norm_name)
    tokens = [token for token in normalized.split() if token]
    return any(token in {"AB", "BA"} for token in tokens)


def _ensure_tactic_classification_fields(
    frame: pd.DataFrame,
    *,
    map_name: str | None = None,
    include_optional_buckets: bool = False,
) -> pd.DataFrame:
    out = frame.copy()
    if "tactic_name" not in out.columns:
        out["tactic_name"] = "Unknown Tactic"
    out["tactic_name"] = out["tactic_name"].astype(str).str.strip().replace("", "Unknown Tactic")

    out["category"] = out.get("category", out["tactic_name"].map(tactic_category))
    out["tactic_type"] = out.get("tactic_type", out["category"]).replace({"Standard": "Standard", "Eco": "Eco", "Pistol": "Pistol"})
    out["role"] = out.get("role", out["tactic_name"].map(_route_role))
    inferred_core = out["tactic_name"].map(_infer_core_bucket)
    role_core = out["role"].map(_role_to_core_bucket)
    existing_core = out.get("core_bucket")
    if existing_core is None:
        out["core_bucket"] = role_core.fillna(inferred_core)
    else:
        existing_series = pd.Series(existing_core, index=out.index).astype(str)
        existing_specific = existing_series.where(existing_series.isin(REQUIRED_CORE_BUCKETS))
        out["core_bucket"] = existing_specific.fillna(role_core).fillna(inferred_core)

    split_col = out.get("is_split_site", out["tactic_name"].map(_is_split_site_tactic))
    out["is_split_site"] = pd.Series(split_col, index=out.index).fillna(False).astype(bool)
    out["split_site_label"] = np.where(out["is_split_site"], SPLIT_STYLE_LABEL, "")
    out["split_site_bucket"] = np.where(out["is_split_site"], "Split-Site", "Single-Site")

    if include_optional_buckets:
        if map_name is None:
            out["optional_buckets"] = out.get("optional_buckets", pd.Series([[] for _ in range(len(out))], index=out.index))
        else:
            existing_optional = out.get("optional_buckets")
            if existing_optional is None:
                out["optional_buckets"] = out["tactic_name"].map(lambda n: _infer_optional_buckets(n, map_name))
            else:
                out["optional_buckets"] = existing_optional.map(lambda vals: vals if isinstance(vals, list) else [])
    return out


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
    weighted_delta = float(row["weighted_delta_vs_baseline"])
    rounds = float(row["rounds"])
    recent_delta = float(row["recent_delta"])
    confidence = float(row["confidence"])
    s_delta = float(row["s_tier_delta"])
    high_tier_share = float(row["high_tier_round_share"])
    weak_tier_inflation = float(row["c_tier_inflation"])

    if rounds >= 15 and weighted_delta >= 8 and confidence >= 78 and recent_delta >= -1 and s_delta >= 3:
        return "Locked In", "Strong S-tier return and high-tier weighted edge make this a reliable map+side lock."
    if rounds >= 10 and weighted_delta >= 4 and confidence >= 66 and s_delta >= 0:
        return "Strong Pick", "Credible edge on weighted high-tier evidence supports active set inclusion."
    if rounds >= 8 and weighted_delta >= 1 and confidence >= 56:
        return "Viable", "Playable option with meaningful S/A/B contribution for this map+side context."
    if rounds < 8 and weighted_delta >= 2:
        return "Test More", "Promising weighted signal but under-tested; schedule controlled reps before core inclusion."
    if rounds >= 8 and weighted_delta >= -1.5 and recent_delta < -5:
        return "Situational", "Historically useful, but recent form cooled and needs scenario-specific usage."
    if weak_tier_inflation > 5 and (s_delta < -2 or high_tier_share < 0.45):
        return "Backup", "Mostly inflated by lower-tier results; reserve until stronger-tier proof improves."
    return EXCLUDE_FOR_NOW_STATUS, "Weighted profile is below baseline or lacks stronger-tier trust for default call sheets."


def _build_views(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_cols = ["map", "side", "tactic_name", "category", "tactic_type", "role", "core_bucket"]

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
    tier_wins = tier.pivot_table(index=group_cols, columns="tier", values="twins", aggfunc="sum", fill_value=0).reset_index()
    tier_losses = tier.pivot_table(index=group_cols, columns="tier", values="tlosses", aggfunc="sum", fill_value=0).reset_index()
    for t in TIER_ORDER:
        if t not in tier_pivot.columns:
            tier_pivot[t] = np.nan
        if t not in tier_wins.columns:
            tier_wins[t] = 0.0
        if t not in tier_losses.columns:
            tier_losses[t] = 0.0
    tier_wins = tier_wins.rename(columns={t: f"{t}_wins" for t in TIER_ORDER})
    tier_losses = tier_losses.rename(columns={t: f"{t}_losses" for t in TIER_ORDER})

    tactical = tactical.merge(recent[group_cols + ["recent_wr"]], on=group_cols, how="left").merge(
        tier_pivot[group_cols + TIER_ORDER], on=group_cols, how="left"
    )
    tactical = tactical.merge(tier_wins[group_cols + [f"{t}_wins" for t in TIER_ORDER]], on=group_cols, how="left")
    tactical = tactical.merge(tier_losses[group_cols + [f"{t}_losses" for t in TIER_ORDER]], on=group_cols, how="left")
    tactical["weighted_wr"] = weighted_tactical_win_rate(tactical, fallback_wr_col="win_rate")

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
    tactical["weighted_delta_vs_baseline"] = tactical["weighted_wr"] - tactical["baseline_wr"]
    tactical["s_tier_delta"] = tactical["S"].fillna(tactical["win_rate"]) - tactical["baseline_wr"]
    tactical["c_tier_inflation"] = (tactical["C"].fillna(tactical["win_rate"]) - tactical["weighted_wr"]).clip(lower=0)
    tactical["high_tier_round_share"] = weighted_tier_round_share(tactical, tiers=("S", "A", "B"))
    tactical["sample_strength"] = np.clip(np.sqrt(tactical["rounds"].clip(lower=1)) * 20, 15, 100)
    tactical["confidence"] = (
        tactical["sample_strength"] * 0.55
        + np.clip(tactical["weighted_delta_vs_baseline"] + 12, 0, 28) * 1.45
        + np.clip(tactical["weighted_wr"] - 45, 0, 35) * 0.7 + np.clip(tactical["s_tier_delta"] + 8, 0, 24) * 0.4
    ).clip(20, 99)
    tactical["trust_label"] = np.where(
        tactical["confidence"] >= 78,
        "Trusted",
        np.where(tactical["confidence"] >= 62, "Playable", "Fragile"),
    )
    tactical["last_used_label"] = tactical["last_used"].dt.strftime("%Y-%m-%d").fillna("N/A")
    tactical["status"], tactical["status_note"] = zip(*tactical.apply(_status_logic, axis=1))
    tactical["recommendation_score"] = (
        tactical["weighted_delta_vs_baseline"] * 3.5
        + tactical["weighted_wr"] * 0.72
        + tactical["confidence"] * 0.45
        + tactical["rounds"].clip(upper=20) * 0.85
    )
    return tactical, baseline


def _select_recommended_set(
    pool: pd.DataFrame,
    map_name: str,
    max_picks: int = 7,
    required_fallback_pool: pd.DataFrame | None = None,
) -> pd.DataFrame:
    pool = _ensure_tactic_classification_fields(pool, map_name=map_name, include_optional_buckets=True)
    if required_fallback_pool is not None:
        required_fallback_pool = _ensure_tactic_classification_fields(
            required_fallback_pool,
            map_name=map_name,
            include_optional_buckets=True,
        )

    if pool.empty and (required_fallback_pool is None or required_fallback_pool.empty):
        return pool

    candidates = pool.sort_values(["recommendation_score", "confidence", "rounds"], ascending=False).copy()
    fallback = (
        required_fallback_pool.sort_values(["recommendation_score", "confidence", "rounds"], ascending=False).copy()
        if required_fallback_pool is not None
        else candidates.copy()
    )
    source = pd.concat([candidates, fallback], ignore_index=True).drop_duplicates(subset=["tactic_name"], keep="first")

    map_optional = MAP_OPTIONAL_BUCKETS.get(_canonical_map_name(map_name), [])
    selected_names: list[str] = []
    core_counts: dict[str, int] = {}
    covered_optional: set[str] = set()
    split_selected = False

    for role in REQUIRED_CORE_BUCKETS:
        role_rows = candidates[candidates["core_bucket"] == role]
        if role_rows.empty:
            role_rows = fallback[fallback["core_bucket"] == role]
        if role_rows.empty:
            continue
        chosen = role_rows.iloc[0]
        chosen_name = str(chosen["tactic_name"])
        if chosen_name not in selected_names:
            selected_names.append(chosen_name)
            core_counts[role] = core_counts.get(role, 0) + 1
            covered_optional.update(chosen["optional_buckets"] if isinstance(chosen["optional_buckets"], list) else [])
            split_selected = split_selected or bool(chosen.get("is_split_site", False))

    for idx, row in candidates.iterrows():
        if len(selected_names) >= max_picks:
            break
        row_name = str(row["tactic_name"])
        if row_name in selected_names:
            continue
        missing_required = [r for r in REQUIRED_CORE_BUCKETS if core_counts.get(r, 0) == 0]
        row_core = str(row["core_bucket"])
        row_optional = [b for b in row["optional_buckets"] if b in map_optional]
        gain_required = 1 if row_core in missing_required else 0
        gain_optional = len([b for b in row_optional if b not in covered_optional])
        gain_split = 1 if (not split_selected and bool(row.get("is_split_site", False))) else 0
        role_penalty = 35 if core_counts.get(row_core, 0) >= 2 else 0

        adjusted_score = float(row["recommendation_score"]) + gain_required * 1000
        if not missing_required:
            adjusted_score += gain_optional * 120
            adjusted_score += gain_split * 165
        adjusted_score -= role_penalty
        candidates.at[idx, "_adjusted_score"] = adjusted_score

    ordered = (
        candidates.sort_values(["_adjusted_score", "confidence", "rounds"], ascending=False)
        if "_adjusted_score" in candidates.columns
        else candidates
    )

    for _, row in ordered.iterrows():
        if len(selected_names) >= max_picks:
            break
        row_name = str(row["tactic_name"])
        if row_name in selected_names:
            continue
        missing_required = [r for r in REQUIRED_CORE_BUCKETS if core_counts.get(r, 0) == 0]
        row_core = str(row["core_bucket"])
        if missing_required and row_core not in missing_required and core_counts.get(row_core, 0) >= 2:
            continue
        selected_names.append(row_name)
        core_counts[row_core] = core_counts.get(row_core, 0) + 1
        covered_optional.update(row["optional_buckets"] if isinstance(row["optional_buckets"], list) else [])
        split_selected = split_selected or bool(row.get("is_split_site", False))

    if not selected_names:
        return candidates.head(0)
    out = source[source["tactic_name"].astype(str).isin(selected_names)].copy()
    out["__pick_order"] = out["tactic_name"].astype(str).map({name: i for i, name in enumerate(selected_names)})
    return out.sort_values(["__pick_order", "core_bucket", "role"], key=lambda s: s.map(_role_priority) if s.name != "__pick_order" else s).drop(
        columns="__pick_order"
    )


def _coverage_state(status: str | None) -> tuple[str, str]:
    norm = str(status or "").strip()
    if norm in STRONG_COVERAGE_STATUSES:
        return "Strongly Covered", "chip-good"
    if norm in WEAK_COVERAGE_STATUSES:
        return "Weak Coverage", "coverage-chip-weak"
    return "Covered", "chip-mid"


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
        .vs-tier-wrap{margin-top:10px;}
        .vs-tier-title{font-size:.56rem;letter-spacing:.11em;text-transform:uppercase;color:#9cb1c7;margin-bottom:5px;}
        .vs-tier-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.35rem;}
        .vs-tier-cell{border-radius:6px;padding:.34rem .2rem;text-align:center;border:1px solid rgba(255,255,255,0.18);}
        .vs-tier-label{font-size:.52rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700;}
        .vs-tier-value{font-size:.72rem;font-weight:760;margin-top:1px;}
        .tile-actions{margin-top:10px;display:flex;justify-content:flex-end;}
        .excluded-note{margin-top:8px;font-size:.58rem;color:#f2b8bf;letter-spacing:.06em;text-transform:uppercase;}
        .shortlist-bucket{border:1px solid #4b3440;background:linear-gradient(180deg,#211821,#16101a);border-radius:8px;padding:.58rem .62rem;margin-top:.55rem;}
        .shortlist-head{display:flex;justify-content:space-between;align-items:center;gap:.5rem;flex-wrap:wrap;}
        .shortlist-title{margin:0;font-size:.75rem;letter-spacing:.11em;text-transform:uppercase;color:#f0cad2;}
        .coverage-chip-weak{background:#3a2615 !important;border-color:#915c28 !important;color:#ffbe72 !important;}
        .coverage-detail{margin:-4px 0 8px 0;padding:6px 8px;border-radius:6px;border:1px solid #27394d;background:#111c29;font-size:.67rem;color:#c5d3e2;}
        .coverage-detail.weak{border-color:#7a4f2b;background:#1d1611;color:#ffca86;}
        .style-badge{display:inline-block;margin-top:6px;font-size:.56rem;letter-spacing:.11em;text-transform:uppercase;padding:2px 7px;border-radius:999px;border:1px solid #35587a;background:#122235;color:#9ec6ff;}
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
    tdf = _ensure_tactic_classification_fields(tdf)

    tdf = attach_normalized_tier(tdf, fallback="C")

    date_ser = tdf.get("date", pd.Series([None] * len(tdf), index=tdf.index))
    time_ser = normalize_time_series(tdf.get("time", pd.Series([None] * len(tdf), index=tdf.index)))
    tdf["time"] = time_ser
    tdf["match_ts"] = build_match_timestamp(date_ser, time_ser)
    tdf["match_ts"] = tdf["match_ts"].fillna(build_match_timestamp(date_ser))

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
    tactical = _ensure_tactic_classification_fields(tactical, map_name=map_name, include_optional_buckets=True)

    exclusion_key = f"tsr_excluded::{map_name}::{side}"
    override_key = f"tsr_model_override::{map_name}::{side}"
    excluded_tactics = set(st.session_state.get(exclusion_key, []))
    model_overrides = set(st.session_state.get(override_key, []))
    all_tactics = tactical["tactic_name"].dropna().astype(str).unique().tolist()
    excluded_tactics = {name for name in excluded_tactics if name in all_tactics}
    model_overrides = {name for name in model_overrides if name in all_tactics}

    show_excluded = st.toggle(
        "Show excluded tactics bucket",
        value=bool(excluded_tactics),
        help="Show a dedicated shortlist-management bucket where excluded tactics can be re-included.",
    )
    st.session_state[exclusion_key] = sorted(excluded_tactics)
    st.session_state[override_key] = sorted(model_overrides)

    active_pool = tactical[~tactical["tactic_name"].isin(excluded_tactics)].copy()
    manually_excluded = tactical[tactical["tactic_name"].isin(excluded_tactics)].copy()
    model_excluded_mask = active_pool["status"].isin(["Backup", EXCLUDE_FOR_NOW_STATUS])
    model_excluded_names = set(active_pool.loc[model_excluded_mask, "tactic_name"].astype(str).tolist())
    effective_model_excluded = model_excluded_names - model_overrides
    recommendation_pool = active_pool[~active_pool["tactic_name"].isin(effective_model_excluded)].copy()
    rec_set = _select_recommended_set(
        recommendation_pool,
        map_name=map_name,
        max_picks=7,
        required_fallback_pool=active_pool,
    )
    rec_set = _ensure_tactic_classification_fields(rec_set, map_name=map_name, include_optional_buckets=True)

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
                <span class='chip'>{len(excluded_tactics)} excluded</span>
                <span class='chip chip-bad'>{len(effective_model_excluded)} model excluded</span>
                <span class='chip chip-good'>{len(recommendation_pool)} active</span>
                <span class='chip chip-mid'>{len(model_overrides)} model overrides</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if show_excluded:
        st.markdown("<div class='shortlist-bucket'>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='shortlist-head'><h4 class='shortlist-title'>Excluded Tactics Bucket</h4><span class='chip chip-bad'>{len(excluded_tactics)} excluded</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='muted'>Managed shortlist bucket. Re-include any tactic to return it to the active recommendation pool and recalculate all set logic.</div>",
            unsafe_allow_html=True,
        )
        if not excluded_tactics:
            st.markdown("<div class='muted' style='margin-top:8px;'>No tactics are manually excluded in this map+side context.</div>", unsafe_allow_html=True)
        else:
            for _, r in tactical[tactical["tactic_name"].isin(excluded_tactics)].sort_values(
                "recommendation_score", ascending=False
            ).iterrows():
                c1, c2 = st.columns([4, 1], gap="small")
                with c1:
                    st.markdown(
                        f"<div class='decision-item'><strong>{r['tactic_name']}</strong>"
                        f"<span>{r['role']} • {_fmt_pct(r['win_rate'])} • {_fmt_signed(r['delta_vs_baseline'])} • conf {int(r['confidence'])}</span>"
                        f"<div class='excluded-note'>Excluded from candidate pool</div></div>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button(
                        "Re-include",
                        key=f"reinclude_bucket_{map_name}_{side}_{r['tactic_name']}",
                        use_container_width=True,
                    ):
                        excluded_tactics.discard(str(r["tactic_name"]))
                        st.session_state[exclusion_key] = sorted(excluded_tactics)
                        st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    global_filters = ctx.get("filters", {})
    comp = global_filters.get("competition") or ["All Competitions"]
    season = global_filters.get("season") or ["All Seasons"]
    newest = scoped["match_ts"].max().strftime("%Y-%m-%d")
    st.markdown(
        f"<div class='muted' style='margin:4px 0 8px 0;'>Tier weighting model for recommendations: S {TACTICAL_TIER_WEIGHTS['S']:.1f} • A {TACTICAL_TIER_WEIGHTS['A']:.1f} • B {TACTICAL_TIER_WEIGHTS['B']:.1f} • C {TACTICAL_TIER_WEIGHTS['C']:.1f} (S >> A≈B > C).</div>",
        unsafe_allow_html=True,
    )

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
    if rec_set.empty:
        st.info(
            "No recommendations available after exclusions for this map+side. Re-include tactics or override model exclusions to restore candidate coverage."
        )
    cols = st.columns(3 if not mobile_view else 1, gap="small")
    for i, (_, row) in enumerate(rec_set.iterrows()):
        tone = STATUS_TONE.get(str(row["status"]), "mid")
        col = cols[i % len(cols)]
        with col:
            tier_cells_html = "".join(
                [
                    (
                        f"<div class='vs-tier-cell' style='background:{TIER_COLORS[t]}1f;border-color:{TIER_COLORS[t]}66;'>"
                        f"<div class='vs-tier-label' style='color:{TIER_COLORS[t]};'>{t}</div>"
                        f"<div class='vs-tier-value'>{_fmt_tier_pct(row[t])}</div></div>"
                    )
                    for t in ["S", "A", "B", "C"]
                ]
            )
            st.markdown(
                f"""
                <div class='reco-tile'>
                  <h4 class='reco-name'>{row['tactic_name']}</h4>
                  <div class='reco-role'>{row['role']} • {row['tactic_type']}</div>
                  {"<span class='style-badge'>AB / BA Split</span>" if bool(row.get("is_split_site", False)) else ""}
                  <span class='status-pill {tone}'>{_display_status(row['status'])}</span>
                  <div class='mini-grid'>
                    <div class='mini-cell'><div class='mini-l'>Win Rate</div><div class='mini-v'>{_fmt_pct(row['win_rate'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Δ Baseline</div><div class='mini-v'>{_fmt_signed(row['delta_vs_baseline'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Rounds</div><div class='mini-v'>{int(row['rounds'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Recent</div><div class='mini-v'>{_fmt_pct(row['recent_wr'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Confidence</div><div class='mini-v'>{int(row['confidence'])}</div></div>
                    <div class='mini-cell'><div class='mini-l'>Last Used</div><div class='mini-v'>{row['last_used_label']}</div></div>
                  </div>
                  <div class='vs-tier-wrap'>
                    <div class='vs-tier-title'>VS Tier %</div>
                    <div class='vs-tier-grid'>{tier_cells_html}</div>
                  </div>
                  <div class='muted' style='margin-top:8px;'>{row['status_note']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Exclude", key=f"exclude_reco_{map_name}_{side}_{row['tactic_name']}", use_container_width=True):
                excluded_tactics.add(str(row["tactic_name"]))
                st.session_state[exclusion_key] = sorted(excluded_tactics)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    map_optional_buckets = MAP_OPTIONAL_BUCKETS.get(_canonical_map_name(map_name), [])
    core_counts = rec_set.groupby("core_bucket")["tactic_name"].count().to_dict()

    optional_count_map: dict[str, int] = {}
    for optional in map_optional_buckets:
        optional_count_map[optional] = int(
            rec_set["optional_buckets"].apply(lambda vals: optional in vals if isinstance(vals, list) else False).sum()
        )

    st.markdown("<div class='panel'><div class='section-title'>Coverage & Completeness Board</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Required core coverage is prioritized first. Optional map coverage and AB / BA split coverage are used to improve tactical completeness within the 7-call cap.</div>", unsafe_allow_html=True)
    st.markdown("<div class='brief-label' style='margin-top:10px;'>Required Core Coverage</div>", unsafe_allow_html=True)
    for bucket in REQUIRED_CORE_BUCKETS:
        chosen_candidates = rec_set[rec_set["core_bucket"] == bucket].sort_values(
            ["recommendation_score", "confidence", "rounds"],
            ascending=False,
        )
        if not chosen_candidates.empty:
            chosen = chosen_candidates.iloc[0]
            badge, chip_class = _coverage_state(str(chosen["status"]))
            fill = 100
            detail = f"{chosen['tactic_name']} • {_display_status(chosen['status'])}"
            detail_kind = " weak" if badge == "Weak Coverage" else ""
        else:
            fill = 0
            badge = "Missing"
            chip_class = "chip-bad"
            fallback_bucket = active_pool[active_pool["core_bucket"] == bucket].sort_values(
                ["recommendation_score", "confidence", "rounds"],
                ascending=False,
            )
            if fallback_bucket.empty:
                detail = "No tactic available for this required slot."
            else:
                nearest = fallback_bucket.iloc[0]
                detail = f"Closest available: {nearest['tactic_name']} • {_display_status(nearest['status'])}"
            detail_kind = ""
        st.markdown(
            f"""
            <div class='coverage-row'>
              <div class='brief-label'>{bucket}</div>
              <div class='coverage-track'><div class='coverage-fill' style='width:{fill}%;'></div></div>
              <div><span class='chip {chip_class}'>{badge}</span></div>
            </div>
            {f"<div class='coverage-detail{detail_kind}'>{detail}</div>" if detail else ""}
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div class='brief-label' style='margin-top:12px;'>Optional Lane Coverage</div>", unsafe_allow_html=True)
    if not map_optional_buckets:
        st.markdown("<div class='muted'>No optional coverage buckets configured for this map.</div>", unsafe_allow_html=True)
    else:
        for bucket in map_optional_buckets:
            count = int(optional_count_map.get(bucket, 0))
            fill = min(100, count * 100)
            badge = "Covered" if count > 0 else "Open"
            chip_class = "chip-good" if count > 0 else "chip-mid"
            st.markdown(
                f"""
                <div class='coverage-row'>
                  <div class='brief-label'>{bucket}</div>
                  <div class='coverage-track'><div class='coverage-fill' style='width:{fill}%;'></div></div>
                  <div><span class='chip {chip_class}'>{badge}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div class='brief-label' style='margin-top:12px;'>Split-Site Tactical Coverage</div>", unsafe_allow_html=True)
    split_candidates = rec_set[rec_set["is_split_site"] == True].sort_values(  # noqa: E712
        ["recommendation_score", "confidence", "rounds"],
        ascending=False,
    )
    split_fill = 100 if not split_candidates.empty else 0
    split_badge = "Available" if not split_candidates.empty else "Gap"
    split_chip = "chip-good" if not split_candidates.empty else "chip-mid"
    split_detail = (
        f"{split_candidates.iloc[0]['tactic_name']} • {_display_status(split_candidates.iloc[0]['status'])}"
        if not split_candidates.empty
        else "No AB / BA split tactic currently included in the recommended set."
    )
    st.markdown(
        f"""
        <div class='coverage-row'>
          <div class='brief-label'>{SPLIT_STYLE_LABEL}</div>
          <div class='coverage-track'><div class='coverage-fill' style='width:{split_fill}%;'></div></div>
          <div><span class='chip {split_chip}'>{split_badge}</span></div>
        </div>
        <div class='coverage-detail'>{split_detail}</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    included = recommendation_pool[recommendation_pool["tactic_name"].isin(rec_set["tactic_name"])].copy()
    borderline = recommendation_pool[
        recommendation_pool["status"].isin(["Viable", "Situational", "Test More"])
        & ~recommendation_pool["tactic_name"].isin(rec_set["tactic_name"])
    ].head(8)
    excluded_by_model = active_pool[active_pool["tactic_name"].isin(effective_model_excluded)].head(8)
    d1, d2, d3 = st.columns(3, gap="small")
    for col, title, frame in [
        (d1, "Included in Recommended Set", included),
        (d2, "Borderline / Rotational", borderline),
        (d3, "Excluded By Model", excluded_by_model),
    ]:
        with col:
            st.markdown(f"<div class='panel decision-col'><h4>{title}</h4>", unsafe_allow_html=True)
            if frame.empty:
                st.markdown("<div class='muted'>No tactics in this bucket for the active context.</div>", unsafe_allow_html=True)
            else:
                for _, r in frame.iterrows():
                    manual_note = "<div class='excluded-note'>Manually excluded</div>" if r["tactic_name"] in excluded_tactics else ""
                    override_note = (
                        "<div class='excluded-note' style='color:#9FE870;'>Manually re-included (model override)</div>"
                        if r["tactic_name"] in model_overrides
                        else ""
                    )
                    split_note = "<div class='style-badge'>AB / BA Split</div>" if bool(r.get("is_split_site", False)) else ""
                    st.markdown(
                        f"<div class='decision-item'><strong>{r['tactic_name']}</strong>"
                        f"<span>{r['role']} • {_fmt_pct(r['win_rate'])} • {_fmt_signed(r['delta_vs_baseline'])} • conf {int(r['confidence'])}</span>"
                        f"{split_note}"
                        f"{manual_note}{override_note}</div>",
                        unsafe_allow_html=True,
                    )
                    if title == "Excluded By Model":
                        if st.button(
                            "Override Model",
                            key=f"override_model_{map_name}_{side}_{r['tactic_name']}",
                            use_container_width=True,
                        ):
                            model_overrides.add(str(r["tactic_name"]))
                            excluded_tactics.discard(str(r["tactic_name"]))
                            st.session_state[override_key] = sorted(model_overrides)
                            st.session_state[exclusion_key] = sorted(excluded_tactics)
                            st.rerun()
                    else:
                        if st.button(
                            "Exclude tactic",
                            key=f"exclude_bucket_{title}_{map_name}_{side}_{r['tactic_name']}",
                            use_container_width=True,
                        ):
                            excluded_tactics.add(str(r["tactic_name"]))
                            model_overrides.discard(str(r["tactic_name"]))
                            st.session_state[override_key] = sorted(model_overrides)
                            st.session_state[exclusion_key] = sorted(excluded_tactics)
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    if PLOTLY_AVAILABLE:
        v1, v2 = st.columns([1.1, 1], gap="small")
        with v1:
            st.markdown("<div class='analytics-frame'><div class='section-title'>Recommendation Score vs Confidence</div></div>", unsafe_allow_html=True)
            scatter = px.scatter(
                recommendation_pool,
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
                    EXCLUDE_FOR_NOW_STATUS: "#ff4d5e",
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

    shortlist = recommendation_pool.copy()
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
            "is_split_site",
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
            "is_split_site": "AB / BA Split",
        }
    )
    shortlist["Excluded?"] = "No"
    shortlist["AB / BA Split"] = shortlist["AB / BA Split"].map({True: "Yes", False: "No"})
    shortlist["Recommendation Status"] = shortlist["Recommendation Status"].map(_display_status)

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

    if show_excluded and not manually_excluded.empty:
        excluded_shortlist = manually_excluded[
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
                "is_split_site",
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
                "is_split_site": "AB / BA Split",
            }
        )
        excluded_shortlist["Included?"] = "No"
        excluded_shortlist["Excluded?"] = "Yes"
        excluded_shortlist["AB / BA Split"] = excluded_shortlist["AB / BA Split"].map({True: "Yes", False: "No"})
        excluded_shortlist["Recommendation Status"] = excluded_shortlist["Recommendation Status"].map(_display_status)
        st.markdown("<div class='panel'><div class='section-title'>Excluded Tactics</div>", unsafe_allow_html=True)
        st.dataframe(
            excluded_shortlist,
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
    focus_source = active_pool if not active_pool.empty else tactical
    focus_name = st.selectbox("Inspect tactic", options=focus_source["tactic_name"].tolist(), index=0)
    focus = focus_source[focus_source["tactic_name"] == focus_name].iloc[0]

    f1, f2, f3 = st.columns(3, gap="small")
    with f1:
        st.markdown(f"<div class='stat-item'><div class='label'>Recommendation Status</div><div class='metric-value' style='font-size:1.1rem'>{_display_status(focus['status'])}</div><div class='muted'>{focus['status_note']}</div></div>", unsafe_allow_html=True)
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
