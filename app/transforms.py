import numpy as np
import pandas as pd


GREVSCORE_CAP = 2.5
GREVSCORE_WEIGHTS = {
    "kd": 0.24,
    "kda": 0.22,
    "kpd": 0.18,
    "mvps": 0.14,
    "accuracy_pct": 0.07,
    "hs_pct": 0.05,
    "damage": 0.10,
}


def _metric_series(df: pd.DataFrame, column: str, fallback: str | None = None) -> pd.Series:
    if column in df.columns:
        return pd.to_numeric(df[column], errors="coerce")
    if fallback and fallback in df.columns:
        return pd.to_numeric(df[fallback], errors="coerce")
    return pd.Series(0.0, index=df.index, dtype=float)


def _normalize_by_dataset_mean(series: pd.Series, cap: float = GREVSCORE_CAP) -> pd.Series:
    baseline = max(float(series.mean(skipna=True) or 1.0), 0.01)
    return np.clip(series.fillna(0.0) / baseline, 0.0, cap)


def compute_grevscore(df: pd.DataFrame) -> pd.Series:
    """
    Source-of-truth GrevScore built ONLY from trusted stats.

    GrevScore =
      0.24 * norm(kd)
    + 0.22 * norm(kda)
    + 0.18 * norm(kpd)
    + 0.14 * norm(mvps)
    + 0.07 * norm(accuracy_pct)
    + 0.05 * norm(hs_pct)
    + 0.10 * norm(damage)

    Normalization method (same for every metric):
      norm(x) = clip(x / dataset_mean(x), 0.0, 2.5)
    """
    kd = _metric_series(df, "kd", fallback="kpd")

    if "kda" in df.columns:
        kda = _metric_series(df, "kda")
    elif {"kills", "deaths", "assists"}.issubset(df.columns):
        kills = _metric_series(df, "kills")
        deaths = _metric_series(df, "deaths").replace(0, np.nan)
        assists = _metric_series(df, "assists")
        kda = (kills + assists) / deaths
    else:
        kda = kd.copy()

    normalized = {
        "kd": _normalize_by_dataset_mean(kd),
        "kda": _normalize_by_dataset_mean(kda),
        "kpd": _normalize_by_dataset_mean(_metric_series(df, "kpd", fallback="kd")),
        "mvps": _normalize_by_dataset_mean(_metric_series(df, "mvps")),
        "accuracy_pct": _normalize_by_dataset_mean(_metric_series(df, "accuracy_pct")),
        "hs_pct": _normalize_by_dataset_mean(_metric_series(df, "hs_pct")),
        "damage": _normalize_by_dataset_mean(_metric_series(df, "damage")),
    }

    score = sum(normalized[k] * w for k, w in GREVSCORE_WEIGHTS.items())
    dataset_anchor = max(float(sum(normalized[k].mean(skipna=True) * w for k, w in GREVSCORE_WEIGHTS.items()) or 1.0), 0.01)
    score = score / dataset_anchor
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
