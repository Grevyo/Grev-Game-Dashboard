import numpy as np
import pandas as pd

from app.data_loader import normalize_side_label
from app.match_summaries import resolve_match_result


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


def best_side_from_wins(
    df_context: pd.DataFrame,
    tactics_context: pd.DataFrame,
    player_name: str,
    default: str = "N/A",
    tie_label: str = "Even",
) -> str:
    if df_context.empty or "player" not in df_context.columns:
        return default

    subset = df_context[df_context["player"].astype(str) == str(player_name)].copy()
    if subset.empty:
        return default

    side_candidates = ["side", "team_side", "player_side", "starting_side"]
    player_side_col = next((col for col in side_candidates if col in subset.columns), None)

    side_lookup: dict[str, str] = {}
    if player_side_col:
        raw_sides = (
            subset[["match_id", player_side_col]]
            .dropna(subset=[player_side_col])
            .assign(match_id=lambda d: d["match_id"].astype(str))
        ) if "match_id" in subset.columns else pd.DataFrame(columns=["match_id", player_side_col])
        if not raw_sides.empty:
            for _, side_row in raw_sides.iterrows():
                side_lookup[str(side_row["match_id"])] = str(side_row[player_side_col]).strip()
    elif not tactics_context.empty and "match_id" in subset.columns and "match_id" in tactics_context.columns:
        tactic_side_col = next((col for col in side_candidates if col in tactics_context.columns), None)
        if tactic_side_col:
            tactic_rows = (
                tactics_context[["match_id", tactic_side_col]]
                .dropna(subset=[tactic_side_col])
                .assign(match_id=lambda d: d["match_id"].astype(str))
            )
            if not tactic_rows.empty:
                side_lookup = {
                    str(row["match_id"]): str(row[tactic_side_col]).strip()
                    for _, row in tactic_rows.iterrows()
                }

    per_match = subset.copy()
    sort_cols = [col for col in ["date", "time"] if col in per_match.columns]
    if sort_cols:
        per_match = per_match.sort_values(sort_cols)
    if "match_id" in per_match.columns:
        per_match = per_match.drop_duplicates("match_id", keep="last")

    win_counts: dict[str, int] = {}
    for _, row in per_match.iterrows():
        result = resolve_match_result(row, tactics_context)
        if result != "Win":
            continue

        side_raw = ""
        if player_side_col:
            side_raw = str(row.get(player_side_col, "") or "").strip()
        if not side_raw and "match_id" in row.index:
            side_raw = side_lookup.get(str(row.get("match_id", "") or "").strip(), "")

        side = normalize_side_label(side_raw)
        if not side:
            continue
        win_counts[side] = win_counts.get(side, 0) + 1

    if not win_counts:
        return default

    ordered = sorted(win_counts.items(), key=lambda item: item[1], reverse=True)
    top_side, top_wins = ordered[0]
    if len(ordered) > 1 and ordered[1][1] == top_wins:
        return tie_label
    return top_side
