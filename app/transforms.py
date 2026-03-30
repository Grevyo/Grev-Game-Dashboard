import numpy as np
import pandas as pd


def with_player_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["kpr"] = np.where(out.get("rounds_played", 0) > 0, out.get("kills", 0) / out.get("rounds_played", 1), np.nan)
    out["mvp_rate"] = np.where(out.get("rounds_played", 0) > 0, out.get("mvps", 0) / out.get("rounds_played", 1) * 30, np.nan)

    baseline_kpd = max(float(out.get("kpd", pd.Series(dtype=float)).mean(skipna=True) or 1.0), 0.01)
    baseline_kpr = max(float(out.get("kpr", pd.Series(dtype=float)).mean(skipna=True) or 1.0), 0.01)
    baseline_acc = max(float(out.get("accuracy_pct", pd.Series(dtype=float)).mean(skipna=True) or 1.0), 0.01)
    baseline_hs = max(float(out.get("hs_pct", pd.Series(dtype=float)).mean(skipna=True) or 1.0), 0.01)
    baseline_mvp = max(float(out.get("mvp_rate", pd.Series(dtype=float)).mean(skipna=True) or 1.0), 0.01)

    normalized = (
        np.clip(out.get("kpd", 0).fillna(0) / baseline_kpd, 0, 2.5) * 0.38
        + np.clip(out.get("kpr", 0).fillna(0) / baseline_kpr, 0, 2.5) * 0.24
        + np.clip(out.get("accuracy_pct", 0).fillna(0) / baseline_acc, 0, 2.2) * 0.16
        + np.clip(out.get("hs_pct", 0).fillna(0) / baseline_hs, 0, 2.5) * 0.12
        + np.clip(out.get("mvp_rate", 0).fillna(0) / baseline_mvp, 0, 2.5) * 0.10
    )
    out["grevscore"] = np.clip(np.power(np.clip(normalized, 0, None), 1.08) * 1.12, 0, None)
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
