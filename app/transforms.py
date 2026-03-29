import re

import numpy as np
import pandas as pd




_SIDE_ALIASES = {
    "red": "Red",
    "t": "Red",
    "attack": "Red",
    "attacking": "Red",
    "offense": "Red",
    "offence": "Red",
    "blue": "Blue",
    "ct": "Blue",
    "counter": "Blue",
    "counter-terrorist": "Blue",
    "counter terrorist": "Blue",
    "defense": "Blue",
    "defence": "Blue",
    "defending": "Blue",
}


def normalize_side_label(side_value) -> str | None:
    """Normalize side labels from any known naming system into dashboard-standard Red/Blue."""
    text = str(side_value or "").strip()
    if not text:
        return None
    key = re.sub(r"[^a-z]+", " ", text.casefold()).strip()
    if not key:
        return None
    key = " ".join(key.split())
    return _SIDE_ALIASES.get(key)


def build_player_side_context(player_matches: pd.DataFrame, tactics: pd.DataFrame) -> pd.DataFrame:
    """Build a side-split context for player rows using match-linked tactic side rounds when needed."""
    if player_matches.empty or tactics.empty:
        return pd.DataFrame(columns=["player", "side", "grevscore", "match_id", "side_rounds", "date", "map"])

    required_player_cols = {"match_id", "player", "grevscore"}
    required_tactic_cols = {"match_id", "side"}
    if not required_player_cols.issubset(player_matches.columns) or not required_tactic_cols.issubset(tactics.columns):
        return pd.DataFrame(columns=["player", "side", "grevscore", "match_id", "side_rounds", "date", "map"])

    side_rounds = tactics[["match_id", "side"]].copy()
    side_rounds["side"] = side_rounds["side"].map(normalize_side_label)
    side_rounds = side_rounds[side_rounds["side"].notna()]
    if side_rounds.empty:
        return pd.DataFrame(columns=["player", "side", "grevscore", "match_id", "side_rounds", "date", "map"])

    # Tactics rows can appear per tactic execution; collapse to side-round totals per match first.
    if "total_rounds" in tactics.columns:
        side_rounds["side_rounds"] = pd.to_numeric(tactics["total_rounds"], errors="coerce").fillna(0)
    elif {"wins", "losses"}.issubset(tactics.columns):
        wins = pd.to_numeric(tactics["wins"], errors="coerce").fillna(0)
        losses = pd.to_numeric(tactics["losses"], errors="coerce").fillna(0)
        side_rounds["side_rounds"] = wins + losses
    else:
        side_rounds["side_rounds"] = 0

    side_rounds = side_rounds.groupby(["match_id", "side"], dropna=False)["side_rounds"].sum().reset_index()
    side_rounds = side_rounds[side_rounds["side_rounds"] > 0]
    if side_rounds.empty:
        return pd.DataFrame(columns=["player", "side", "grevscore", "match_id", "side_rounds", "date", "map"])

    player_cols = [c for c in ["match_id", "player", "grevscore", "date", "map"] if c in player_matches.columns]
    player_core = player_matches[player_cols].copy()
    side_context = player_core.merge(side_rounds, on="match_id", how="inner")
    if side_context.empty:
        return pd.DataFrame(columns=["player", "side", "grevscore", "match_id", "side_rounds", "date", "map"])

    match_total_side_rounds = side_context.groupby(["player", "match_id"], dropna=False)["side_rounds"].transform("sum")
    side_context["side_weight"] = np.where(match_total_side_rounds > 0, side_context["side_rounds"] / match_total_side_rounds, np.nan)
    # Keep a weighted GrevScore per side row so side summaries use real player match output with side round share.
    side_context["grevscore"] = side_context["grevscore"] * side_context["side_weight"].fillna(0)
    return side_context

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
