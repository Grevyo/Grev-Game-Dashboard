import numpy as np
import pandas as pd


GREVSCORE_CAP = 2.2
GREVSCORE_WEIGHTS = {
    "kd": 0.26,
    "kda": 0.24,
    "kpd": 0.20,
    "mvps": 0.12,
    "accuracy_pct": 0.05,
    "hs_pct": 0.03,
    "damage": 0.10,
}
GREVSCORE_REFERENCES = {
    "kd": 1.00,
    "kda": 1.25,
    "kpd": 1.00,
    "mvps": 2.00,
    "accuracy_pct": 68.0,
    "hs_pct": 40.0,
    "damage": 3300.0,
}
GREVSCORE_FLOORS = {
    "kd": 0.55,
    "kda": 0.55,
    "kpd": 0.55,
    "mvps": 0.75,
    "accuracy_pct": 0.90,
    "hs_pct": 0.90,
    "damage": 0.75,
}


def _metric_series(df: pd.DataFrame, column: str, fallbacks: tuple[str, ...] = ()) -> pd.Series:
    if column in df.columns:
        return pd.to_numeric(df[column], errors="coerce")
    for fallback in fallbacks:
        if fallback in df.columns:
            return pd.to_numeric(df[fallback], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype=float)


def _normalize_to_reference(series: pd.Series, reference: float, floor: float, cap: float = GREVSCORE_CAP) -> pd.Series:
    safe_reference = max(float(reference or 1.0), 0.01)
    normalized = series.fillna(safe_reference) / safe_reference
    return np.clip(normalized, floor, cap)


def compute_grevscore(df: pd.DataFrame) -> pd.Series:
    """
    Source-of-truth GrevScore built ONLY from trusted stats.

    GrevScore =
      0.26 * norm(kd)
    + 0.24 * norm(kda)
    + 0.20 * norm(kpd)
    + 0.12 * norm(mvps)
    + 0.05 * norm(accuracy_pct)
    + 0.03 * norm(hs_pct)
    + 0.10 * norm(damage)

    Normalization method:
      norm(metric) = clip(metric / reference_metric, floor_metric, 2.2)

    Missing trusted metrics are neutral (norm = 1.0) rather than punitive.
    """
    kd = _metric_series(df, "kd", fallbacks=("kpd",))
    kda = _metric_series(df, "kda", fallbacks=("kd", "kpd"))
    kpd = _metric_series(df, "kpd", fallbacks=("kd",))
    mvps = _metric_series(df, "mvps")
    accuracy_pct = _metric_series(df, "accuracy_pct")
    hs_pct = _metric_series(df, "hs_pct")
    damage = _metric_series(df, "damage")

    normalized = {
        "kd": _normalize_to_reference(kd, GREVSCORE_REFERENCES["kd"], GREVSCORE_FLOORS["kd"]),
        "kda": _normalize_to_reference(kda, GREVSCORE_REFERENCES["kda"], GREVSCORE_FLOORS["kda"]),
        "kpd": _normalize_to_reference(kpd, GREVSCORE_REFERENCES["kpd"], GREVSCORE_FLOORS["kpd"]),
        "mvps": _normalize_to_reference(mvps, GREVSCORE_REFERENCES["mvps"], GREVSCORE_FLOORS["mvps"]),
        "accuracy_pct": _normalize_to_reference(accuracy_pct, GREVSCORE_REFERENCES["accuracy_pct"], GREVSCORE_FLOORS["accuracy_pct"]),
        "hs_pct": _normalize_to_reference(hs_pct, GREVSCORE_REFERENCES["hs_pct"], GREVSCORE_FLOORS["hs_pct"]),
        "damage": _normalize_to_reference(damage, GREVSCORE_REFERENCES["damage"], GREVSCORE_FLOORS["damage"]),
    }

    score = sum(normalized[k] * w for k, w in GREVSCORE_WEIGHTS.items())
    return pd.Series(np.clip(score, 0.0, GREVSCORE_CAP), index=df.index)


def with_player_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["kpr"] = np.where(out.get("rounds_played", 0) > 0, out.get("kills", 0) / out.get("rounds_played", 1), np.nan)
    out["mvp_rate"] = np.where(out.get("rounds_played", 0) > 0, out.get("mvps", 0) / out.get("rounds_played", 1) * 30, np.nan)

    out["grevscore"] = compute_grevscore(out)

    baseline_kpr = max(float(out.get("kpr", pd.Series(dtype=float)).mean(skipna=True) or 1.0), 0.01)
    out["rating"] = (
        out.get("kpd", 0).fillna(0) * 0.65
        + (out.get("kpr", 0).fillna(0) / baseline_kpr) * 0.35
    )
    out["impact"] = out.get("kills", 0).fillna(0) + out.get("mvps", 0).fillna(0) * 2
    out["form"] = out.groupby("player", dropna=False)["grevscore"].transform(lambda s: s.rolling(5, min_periods=1).mean())
    return out


def latest_window(df: pd.DataFrame, days: int | None = None, matches: int | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.sort_values("date")
    if days and "date" in out.columns:
        cutoff = out["date"].max() - pd.Timedelta(days=days)
        out = out[out["date"] >= cutoff]
    if matches:
        out = out.groupby("player", group_keys=False).tail(matches)
    return out


def summarize_player(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    grp = (
        df.groupby("player", dropna=False)
        .agg(
            matches=("match_id", "nunique"),
            grevscore=("grevscore", "mean"),
            rating=("rating", "mean"),
            impact=("impact", "mean"),
            form=("form", "mean"),
            kpd=("kpd", "mean"),
            kpr=("kpr", "mean"),
            accuracy_pct=("accuracy_pct", "mean"),
            hs_pct=("hs_pct", "mean"),
        )
        .reset_index()
    )
    return grp.sort_values("grevscore", ascending=False)


def best_contexts(df: pd.DataFrame, by: str) -> pd.DataFrame:
    if df.empty or by not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby(by, dropna=False)
        .agg(grevscore=("grevscore", "mean"), matches=("match_id", "nunique"))
        .query("matches > 0")
        .sort_values("grevscore", ascending=False)
        .reset_index()
    )
