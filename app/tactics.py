import re

import pandas as pd

from app.descriptions import tactic_reason
from app.metrics import trend_label

TIER_ORDER = ["S", "A", "B", "C"]
TIER_COLUMN_PREFERENCES = (
    "tier",
    "opponent_tier",
    "league_tier",
    "unnamed:_13",
    "unnamed: 13",
    "unnamed_13",
    "unnamed:13",
    "",
)


def normalize_tier_values(series: pd.Series) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip().str.upper()
    compact = cleaned.str.replace(r"[\s_\-]+", "", regex=True)

    direct_map = {
        "S": "S",
        "A": "A",
        "B": "B",
        "C": "C",
        "STIER": "S",
        "ATIER": "A",
        "BTIER": "B",
        "CTIER": "C",
        "TIERS": "S",
        "TIERA": "A",
        "TIERB": "B",
        "TIERC": "C",
        "1": "S",
        "2": "A",
        "3": "B",
        "4": "C",
    }
    normalized = compact.map(direct_map)
    extracted = compact.str.extract(r"\b([SABC])(?:TIER)?\b", expand=False)
    normalized = normalized.combine_first(extracted)
    return normalized.where(normalized.isin(TIER_ORDER), pd.NA)


def best_tier_column(df: pd.DataFrame) -> str | None:
    if df.empty:
        return None

    normalized_cols = [str(col).strip().lower() for col in df.columns]
    best_col = None
    best_score = (-1, -1)

    for pref in TIER_COLUMN_PREFERENCES:
        pref_key = str(pref).strip().lower()
        matching = [col for col, norm in zip(df.columns, normalized_cols) if norm == pref_key]
        for col in matching:
            col_data = df[col]
            if isinstance(col_data, pd.DataFrame):
                # Duplicate column names can produce a DataFrame; use the most populated slice.
                for _, dup_series in col_data.items():
                    norm = normalize_tier_values(dup_series)
                    score = (int(norm.notna().sum()), int(dup_series.astype(str).str.strip().ne("").sum()))
                    if score > best_score:
                        best_score = score
                        best_col = col
            else:
                norm = normalize_tier_values(col_data)
                score = (int(norm.notna().sum()), int(col_data.astype(str).str.strip().ne("").sum()))
                if score > best_score:
                    best_score = score
                    best_col = col

    return best_col


def attach_normalized_tier(df: pd.DataFrame, *, fallback: str = "C") -> pd.DataFrame:
    out = df.copy()
    tier_col = best_tier_column(out)
    if tier_col is None:
        out["tier"] = fallback
        return out

    tier_raw = out[tier_col]
    if isinstance(tier_raw, pd.DataFrame):
        candidates = [normalize_tier_values(dup_series) for _, dup_series in tier_raw.items()]
        tier_series = max(candidates, key=lambda s: int(s.notna().sum())) if candidates else pd.Series(pd.NA, index=out.index)
    else:
        tier_series = normalize_tier_values(tier_raw)
    out["tier"] = tier_series.fillna(fallback)
    return out


def tactic_category(name: str) -> str:
    n = str(name).upper()
    if "(P)" in n or n.startswith("P"):
        return "Pistol"
    if "(E)" in n or n.startswith("E"):
        return "Eco"
    return "Standard"


def route_key(name: str) -> str:
    n = str(name).upper()
    patterns = ["A MID", "A HALL", "A MAIN", "B IVY", "B HALL", "B MAIN", "MID", "A", "B"]
    for p in patterns:
        if p in n:
            return p
    cleaned = re.sub(r"[^A-Z0-9]+", " ", n)
    return " ".join(cleaned.split()[:3])


def tactic_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
    x["category"] = x["tactic_name"].map(tactic_category)
    agg = (
        x.groupby(["map", "side", "tactic_name", "category"], dropna=False)
        .agg(wins=("wins", "sum"), losses=("losses", "sum"), uses=("total_rounds", "sum"))
        .reset_index()
    )
    agg["win_rate"] = (agg["wins"] / (agg["wins"] + agg["losses"]).clip(lower=1) * 100).fillna(0)
    agg["score"] = agg["win_rate"] * 0.6 + agg["uses"].clip(upper=25) * 1.6
    agg["route_key"] = agg["tactic_name"].map(route_key)
    agg["trend"] = agg["win_rate"].map(lambda w: "Rising" if w >= 60 else "Falling" if w < 45 else "Flat")
    agg["reason"] = agg.apply(lambda r: tactic_reason(r["tactic_name"], r["score"], r["trend"], r["uses"]), axis=1)
    return agg


def tactic_bucket(row) -> str:
    if row["uses"] < 5 and row["win_rate"] >= 55:
        return "Promising / needs more data"
    if row["win_rate"] >= 62 and row["uses"] >= 5:
        return "Working well"
    if row["win_rate"] < 40 and row["uses"] >= 5:
        return "Drop / not working"
    if row["win_rate"] < 50:
        return "Falling off"
    return "Neutral / situational"


def recommend_set(summary: pd.DataFrame, map_name: str, side: str) -> pd.DataFrame:
    pool = summary[(summary["map"] == map_name) & (summary["side"] == side)].copy()
    if pool.empty:
        return pool

    pool["bucket"] = pool.apply(tactic_bucket, axis=1)
    picks = []

    def pick(category, n, include=None):
        local = pool[pool["category"] == category].sort_values(["score", "uses"], ascending=False)
        chosen_routes = set()
        count = 0
        for _, row in local.iterrows():
            if include and include not in row["tactic_name"].upper():
                continue
            if row["route_key"] in chosen_routes:
                continue
            picks.append(row)
            chosen_routes.add(row["route_key"])
            count += 1
            if count >= n:
                break

    pick("Pistol", 1)
    pick("Eco", 2)
    pick("Standard", 2, include="A")
    pick("Standard", 2, include="B")

    out = pd.DataFrame(picks).drop_duplicates(subset=["tactic_name"]) if picks else pd.DataFrame()
    return out.sort_values("score", ascending=False)


# Tactical recommendation weighting: S-tier should dominate, A/B should be close, C should barely count.
TACTICAL_TIER_WEIGHTS = {"S": 5.4, "A": 2.2, "B": 2.0, "C": 0.2}


def weighted_tactical_win_rate(
    frame: pd.DataFrame,
    *,
    wins_suffix: str = "_wins",
    losses_suffix: str = "_losses",
    fallback_wr_col: str = "win_rate",
) -> pd.Series:
    """Round-weighted tier win rate for tactical recommendation systems.

    Uses weighted wins / weighted rounds by tier so S-tier round outcomes have
    substantially more decision impact than lower tiers.
    """
    if frame.empty:
        return pd.Series(dtype=float, index=frame.index)

    weighted_wins = pd.Series(0.0, index=frame.index, dtype=float)
    weighted_rounds = pd.Series(0.0, index=frame.index, dtype=float)
    for tier in TIER_ORDER:
        weight = float(TACTICAL_TIER_WEIGHTS[tier])
        wins = pd.to_numeric(frame.get(f"{tier}{wins_suffix}", 0), errors="coerce").fillna(0.0)
        losses = pd.to_numeric(frame.get(f"{tier}{losses_suffix}", 0), errors="coerce").fillna(0.0)
        rounds = (wins + losses).clip(lower=0.0)
        weighted_wins = weighted_wins + wins * weight
        weighted_rounds = weighted_rounds + rounds * weight

    fallback = pd.to_numeric(frame.get(fallback_wr_col, 0), errors="coerce").fillna(0.0)
    return (weighted_wins / weighted_rounds.clip(lower=1e-9) * 100.0).where(weighted_rounds > 0, fallback)


def weighted_tier_round_share(frame: pd.DataFrame, tiers: tuple[str, ...] = ("S", "A", "B")) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float, index=frame.index)
    weighted_focus = pd.Series(0.0, index=frame.index, dtype=float)
    weighted_all = pd.Series(0.0, index=frame.index, dtype=float)
    for tier in TIER_ORDER:
        wins = pd.to_numeric(frame.get(f"{tier}_wins", 0), errors="coerce").fillna(0.0)
        losses = pd.to_numeric(frame.get(f"{tier}_losses", 0), errors="coerce").fillna(0.0)
        rounds = (wins + losses).clip(lower=0.0)
        weight = float(TACTICAL_TIER_WEIGHTS[tier])
        term = rounds * weight
        weighted_all = weighted_all + term
        if tier in tiers:
            weighted_focus = weighted_focus + term
    return (weighted_focus / weighted_all.clip(lower=1e-9)).fillna(0.0)


def observed_tiers_from_row(
    row: pd.Series,
    *,
    wins_suffix: str = "_wins",
    losses_suffix: str = "_losses",
) -> list[str]:
    observed: list[str] = []
    for tier in TIER_ORDER:
        wins = pd.to_numeric(row.get(f"{tier}{wins_suffix}", 0), errors="coerce")
        losses = pd.to_numeric(row.get(f"{tier}{losses_suffix}", 0), errors="coerce")
        rounds = float(pd.Series([wins]).fillna(0).iloc[0]) + float(pd.Series([losses]).fillna(0).iloc[0])
        if rounds > 0:
            observed.append(tier)
    return observed


def tier_evidence_label(observed_tiers: list[str]) -> str:
    if not observed_tiers:
        return "limited tier evidence"
    return f"{'/'.join(observed_tiers)}-tier evidence"
