import html
import math
import re

import pandas as pd
import streamlit as st

from app.achievements import achievements_for_player
from app.components import player_card, stat_card
from app.data_loader import get_medisports_roster_df, normalize_player_key, normalize_side_label
from app.descriptions import player_description
from app.image_helpers import find_team_logo, image_data_uri, resolve_player_photo
from app.map_utils import normalize_map_series
from app.metrics import stat_tone, trend_label
from app.page_layout import section_header
from app.presentation_helpers import nationality_label


NOT_AVAILABLE = "N/A"
TACTIC_TOP_N = 10


def _season_col(df: pd.DataFrame) -> str | None:
    for col in ("resolved_season", "season"):
        if col in df.columns:
            return col
    return None


def _season_value_series(df: pd.DataFrame) -> pd.Series:
    col = _season_col(df)
    if df.empty or not col:
        return pd.Series(pd.NA, index=df.index, dtype="Int64")
    return pd.to_numeric(df[col], errors="coerce").astype("Int64")


def _season_options(*frames: pd.DataFrame) -> list[int]:
    seasons: set[int] = set()
    for df in frames:
        values = _season_value_series(df).dropna().astype(int).tolist()
        seasons.update(values)
    return sorted(seasons)


def _season_label(season: int | str) -> str:
    if pd.isna(season):
        return "Unspecified"
    try:
        return f"Season {int(season)}"
    except (TypeError, ValueError):
        return f"Season {season}"


def _filter_seasons(df: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    if df.empty or not seasons:
        return df.iloc[0:0].copy()
    season_values = _season_value_series(df)
    return df[season_values.isin([int(s) for s in seasons])].copy()


def _filter_season(df: pd.DataFrame, season: int) -> pd.DataFrame:
    return _filter_seasons(df, [season])


def _extract_season_number(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    match = re.search(r"\d+", str(value))
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _filter_achievements_for_season(achievements_df: pd.DataFrame, season: int) -> pd.DataFrame:
    if achievements_df.empty or "season_name" not in achievements_df.columns:
        return achievements_df.iloc[0:0].copy()
    season_number = int(season)
    season_numbers = achievements_df["season_name"].map(_extract_season_number)
    return achievements_df[season_numbers == season_number].copy()


def _normalize_tactic_side(value) -> str:
    """Normalize tactic side aliases without mixing unknown values into Red/Blue."""
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none", "null", "<na>", "unknown", "unknown side"}:
        return "Unknown side"
    key = re.sub(r"[^a-z0-9]+", "", text.casefold())
    if key in {"red", "redside", "t", "tside", "terrorist", "terrorists", "attack", "attacking", "attacker", "attackers", "offense", "offence", "offensive"}:
        return "Red"
    if key in {"blue", "blueside", "ct", "ctside", "counterterrorist", "counterterrorists", "defence", "defense", "defending", "defender", "defenders", "defensive"}:
        return "Blue"
    normalized = normalize_side_label(text)
    return normalized if normalized in {"Red", "Blue"} else "Unknown side"


def _normalized_tactic_side_series(df: pd.DataFrame) -> pd.Series:
    if df.empty or "side" not in df.columns:
        return pd.Series("Unknown side", index=df.index, dtype="object")
    return df["side"].map(_normalize_tactic_side).astype("object")


def _resolved_tactic_map_series(df: pd.DataFrame) -> pd.Series:
    if df.empty or "map" not in df.columns:
        return pd.Series("Unknown Map", index=df.index, dtype="object")
    normalized = normalize_map_series(df["map"]).astype("object")
    text = normalized.fillna("").astype(str).str.strip()
    invalid = (text == "") | text.str.casefold().isin({"nan", "none", "null", "<na>"})
    text.loc[invalid] = "Unknown Map"
    return text


def _first_existing_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    return next((col for col in candidates if col in df.columns), None)


def _match_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    return int(df["match_id"].nunique()) if "match_id" in df.columns else int(len(df))


def _unique_count(df: pd.DataFrame, col: str) -> int:
    if df.empty or col not in df.columns:
        return 0
    values = df[col].dropna().astype(str).str.strip()
    values = values[values != ""]
    return int(values.nunique())


def _date_range(df: pd.DataFrame) -> str:
    if df.empty or "date" not in df.columns:
        return NOT_AVAILABLE
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return NOT_AVAILABLE
    return f"{dates.min().strftime('%Y-%m-%d')} → {dates.max().strftime('%Y-%m-%d')}"


def _season_window_range(season_windows: pd.DataFrame | None, season: int) -> str:
    if season_windows is None or season_windows.empty:
        return NOT_AVAILABLE
    required = {"season", "start_date", "end_date"}
    if not required.issubset(season_windows.columns):
        return NOT_AVAILABLE
    windows = season_windows.copy()
    windows["season"] = pd.to_numeric(windows["season"], errors="coerce").astype("Int64")
    rows = windows[windows["season"] == int(season)]
    if rows.empty:
        return NOT_AVAILABLE
    row = rows.iloc[0]
    start = pd.to_datetime(row.get("start_date"), errors="coerce")
    end = pd.to_datetime(row.get("end_date"), errors="coerce")
    if pd.isna(start):
        return NOT_AVAILABLE
    if pd.isna(end):
        return f"{start.strftime('%Y-%m-%d')} → onwards"
    return f"{start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}"


def _numeric_mean(df: pd.DataFrame, col: str) -> float | None:
    if df.empty or col not in df.columns:
        return None
    value = pd.to_numeric(df[col], errors="coerce").mean()
    return None if pd.isna(value) else float(value)


def _numeric_sum(df: pd.DataFrame, col: str) -> float | None:
    if df.empty or col not in df.columns:
        return None
    values = pd.to_numeric(df[col], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.sum())


def _fmt(value, decimals: int = 2, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return NOT_AVAILABLE
    return f"{float(value):.{decimals}f}{suffix}"


def _fmt_int(value) -> str:
    if value is None or pd.isna(value):
        return NOT_AVAILABLE
    return f"{int(round(float(value))):,}"


def _first_text(series: pd.Series, default: str = NOT_AVAILABLE) -> str:
    if series is None or series.empty:
        return default
    cleaned = series.dropna().astype(str).str.strip()
    cleaned = cleaned[(cleaned != "") & (~cleaned.str.casefold().isin({"nan", "none", "null", "<na>"}))]
    return str(cleaned.iloc[0]) if not cleaned.empty else default


def _value_counts_label(df: pd.DataFrame, col: str, limit: int = 2) -> str:
    if df.empty or col not in df.columns:
        return NOT_AVAILABLE
    values = df[col].dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return NOT_AVAILABLE
    counts = values.value_counts().head(limit)
    return ", ".join(f"{name} ({count})" for name, count in counts.items())


def _best_map_by_grevscore(df: pd.DataFrame, min_matches: int = 1) -> str:
    if df.empty or "map" not in df.columns or "grevscore" not in df.columns:
        return NOT_AVAILABLE
    working = df.copy()
    working["map"] = normalize_map_series(working["map"])
    working["grevscore"] = pd.to_numeric(working["grevscore"], errors="coerce")
    working = working[(working["map"].astype(str).str.strip() != "") & working["grevscore"].notna()]
    if working.empty:
        return NOT_AVAILABLE
    grouped = working.groupby("map", dropna=False).agg(grevscore=("grevscore", "mean"), matches=("match_id", "nunique") if "match_id" in working.columns else ("map", "size")).reset_index()
    eligible = grouped[grouped["matches"] >= min_matches]
    if eligible.empty:
        eligible = grouped
    best = eligible.sort_values(["grevscore", "matches"], ascending=[False, False]).head(1)
    return str(best.iloc[0]["map"]) if not best.empty else NOT_AVAILABLE


def _most_played_map(df: pd.DataFrame) -> str:
    if df.empty or "map" not in df.columns:
        return NOT_AVAILABLE
    working = df.copy()
    working["map"] = normalize_map_series(working["map"])
    working = working[working["map"].astype(str).str.strip() != ""]
    if working.empty:
        return NOT_AVAILABLE
    if "match_id" in working.columns:
        counts = working.drop_duplicates(["match_id", "map"])["map"].value_counts()
    else:
        counts = working["map"].value_counts()
    if counts.empty:
        return NOT_AVAILABLE
    return f"{counts.index[0]} ({int(counts.iloc[0])})"


def _players_meta_by_key(players: pd.DataFrame) -> pd.DataFrame:
    if players.empty:
        return pd.DataFrame()
    name_col = "player_clean" if "player_clean" in players.columns else "player" if "player" in players.columns else "name" if "name" in players.columns else None
    if not name_col:
        return pd.DataFrame()
    meta = players.copy()
    meta["player_key"] = meta[name_col].map(normalize_player_key)
    meta = meta[meta["player_key"] != ""]
    return meta.drop_duplicates("player_key", keep="first")


def _display_player_from_key(rows: pd.DataFrame, player_key: str) -> str:
    if "player_key" in rows.columns and "player" in rows.columns:
        names = rows.loc[rows["player_key"] == player_key, "player"].dropna().astype(str).str.strip()
        if not names.empty:
            return str(names.iloc[0])
    return player_key


def _trend_for_player_scope(p_df: pd.DataFrame) -> str:
    if p_df.empty or "grevscore" not in p_df.columns:
        return "Stable"
    sort_cols = [c for c in ["date", "time"] if c in p_df.columns]
    values = pd.to_numeric(p_df.sort_values(sort_cols)["grevscore"] if sort_cols else p_df["grevscore"], errors="coerce")
    label = trend_label(values)
    return "Heating Up" if label == "Rising" else "Cooling" if label == "Falling" else "Stable"


def _best_side_for_player_scope(p_df: pd.DataFrame, season_tactics: pd.DataFrame) -> str:
    if p_df.empty or "grevscore" not in p_df.columns:
        return NOT_AVAILABLE
    side_candidates = ["side", "team_side", "player_side", "starting_side"]
    player_side_col = next((c for c in side_candidates if c in p_df.columns), None)
    if player_side_col:
        side_rows = p_df[["grevscore", player_side_col]].rename(columns={player_side_col: "side_raw"}).copy()
    elif {"match_id"}.issubset(p_df.columns) and "match_id" in season_tactics.columns:
        tactic_side_col = next((c for c in side_candidates if c in season_tactics.columns), None)
        if not tactic_side_col:
            return NOT_AVAILABLE
        player_rows = p_df[["match_id", "grevscore"]].copy()
        player_rows["match_id"] = player_rows["match_id"].astype(str)
        tactic_rows = season_tactics[["match_id", tactic_side_col]].rename(columns={tactic_side_col: "side_raw"}).copy()
        tactic_rows["match_id"] = tactic_rows["match_id"].astype(str)
        side_rows = player_rows.merge(tactic_rows, on="match_id", how="inner")
    else:
        return NOT_AVAILABLE
    if side_rows.empty:
        return NOT_AVAILABLE
    side_rows["grevscore"] = pd.to_numeric(side_rows["grevscore"], errors="coerce")
    side_rows["side_norm"] = side_rows["side_raw"].map(normalize_side_label)
    side_rows = side_rows[(side_rows["side_norm"].astype(str).str.strip() != "") & side_rows["grevscore"].notna()]
    if side_rows["side_norm"].nunique() < 2:
        return NOT_AVAILABLE
    grouped = side_rows.groupby("side_norm", dropna=False).agg(grevscore=("grevscore", "mean"), rows=("side_norm", "size")).reset_index()
    best = grouped.sort_values(["grevscore", "rows"], ascending=[False, False]).head(1)
    return str(best.iloc[0]["side_norm"]) if not best.empty else NOT_AVAILABLE


def _tier_grevscores(p_df: pd.DataFrame) -> dict[str, float]:
    if p_df.empty or "tier" not in p_df.columns or "grevscore" not in p_df.columns:
        return {}
    summary = p_df.assign(grevscore=pd.to_numeric(p_df["grevscore"], errors="coerce")).dropna(subset=["grevscore"]).groupby("tier", dropna=False)["grevscore"].mean()
    return {str(tier).upper(): float(score) for tier, score in summary.items()}


def _best_match_summary(p_df: pd.DataFrame) -> dict | None:
    if p_df.empty or "grevscore" not in p_df.columns:
        return None
    working = p_df.copy()
    working["grevscore"] = pd.to_numeric(working["grevscore"], errors="coerce")
    working = working.dropna(subset=["grevscore"])
    if working.empty:
        return None
    row = working.sort_values("grevscore", ascending=False).iloc[0]
    return {
        "date_played": pd.to_datetime(row.get("date"), errors="coerce").strftime("%Y-%m-%d") if pd.notna(pd.to_datetime(row.get("date"), errors="coerce")) else "",
        "opponent_team": str(row.get("opponent_team", "")),
        "result": str(row.get("result", "Tracked")),
        "kpd": float(row.get("kpd", 0) or 0),
        "grevscore": float(row.get("grevscore", 0) or 0),
    }


def _last_match_summary(p_df: pd.DataFrame) -> dict | None:
    if p_df.empty:
        return None
    working = p_df.copy()
    if "date" in working.columns:
        working["_date_sort"] = pd.to_datetime(working["date"], errors="coerce")
        working = working.sort_values(["_date_sort", *(["time"] if "time" in working.columns else [])], na_position="last")
    row = working.iloc[-1]
    return {
        "date_played": pd.to_datetime(row.get("date"), errors="coerce").strftime("%Y-%m-%d") if pd.notna(pd.to_datetime(row.get("date"), errors="coerce")) else "",
        "opponent_team": str(row.get("opponent_team", "")),
        "result": str(row.get("result", "Tracked")),
        "kpd": float(row.get("kpd", 0) or 0),
        "grevscore": float(row.get("grevscore", 0) or 0),
    }


def _resolve_favourite_map(meta_row: pd.Series | None) -> str:
    if meta_row is None:
        return NOT_AVAILABLE
    for col in ("map", "favourite_map", "favorite_map", "fav_map", "favourite", "favorite", "map_favourite", "map_favorite"):
        if col in meta_row.index:
            value = str(meta_row.get(col, "") or "").strip()
            if value:
                return value
    return NOT_AVAILABLE


def season_player_summary(season_df: pd.DataFrame) -> pd.DataFrame:
    if season_df.empty or "player" not in season_df.columns:
        return pd.DataFrame()
    working = season_df.copy()
    working["player_key"] = working.get("player_clean", working["player"]).map(normalize_player_key)
    working = working[working["player_key"] != ""]
    if working.empty:
        return pd.DataFrame()
    for col in ["grevscore", "rating", "impact", "form", "kpd", "kpr", "accuracy_pct", "hs_pct", "kills", "deaths", "damage"]:
        if col in working.columns:
            working[col] = pd.to_numeric(working[col], errors="coerce")
    display_names = working.sort_values([c for c in ["date", "time", "player"] if c in working.columns]).groupby("player_key", dropna=False)["player"].first()
    agg = {"matches": ("match_id", "nunique") if "match_id" in working.columns else ("player", "size")}
    for col in ["grevscore", "rating", "impact", "form", "kpd", "kpr", "accuracy_pct", "hs_pct"]:
        if col in working.columns:
            agg[col] = (col, "mean")
    for col in ["kills", "deaths"]:
        if col in working.columns:
            agg[col] = (col, "sum")
    if "damage" in working.columns:
        agg["damage_avg"] = ("damage", "mean")
    summary = working.groupby("player_key", dropna=False).agg(**agg).reset_index()
    summary["player"] = summary["player_key"].map(display_names).fillna(summary["player_key"])
    return summary.sort_values(["grevscore", "matches"], ascending=[False, False], na_position="last")


def build_player_card_payloads(
    season_df: pd.DataFrame,
    season_tactics: pd.DataFrame,
    players: pd.DataFrame,
    achievements_df: pd.DataFrame,
    min_matches: int,
    season: int,
) -> list[dict]:
    season_df = _filter_season(season_df, season) if _season_col(season_df) else season_df.copy()
    season_tactics = _filter_season(season_tactics, season) if _season_col(season_tactics) else season_tactics.copy()
    summary = season_player_summary(season_df)
    if summary.empty:
        return []
    summary = summary[summary["matches"] >= int(min_matches)].copy()
    meta = _players_meta_by_key(players)
    season_achievements = _filter_achievements_for_season(achievements_df, season)
    team_logo = image_data_uri(find_team_logo("Medisports"))
    payloads: list[dict] = []
    for _, row in summary.iterrows():
        player_key = str(row.get("player_key", ""))
        player_rows = season_df[season_df["player_key"] == player_key].copy() if "player_key" in season_df.columns else season_df.iloc[0:0].copy()
        display = str(row.get("player") or _display_player_from_key(season_df, player_key))
        meta_row = None
        if not meta.empty and (meta["player_key"] == player_key).any():
            meta_row = meta[meta["player_key"] == player_key].iloc[0]
        photo = resolve_player_photo(display)
        if not photo.get("path") and player_key:
            photo = resolve_player_photo(player_key)
        achievements, hidden = achievements_for_player(season_achievements, display, cap=4, consumer="season_preview")
        nationality = ""
        if meta_row is not None:
            nationality = nationality_label(meta_row.get("nationality") or meta_row.get("country"))
        payload = {
            "player": display,
            "player_key": player_key,
            "country": meta_row.get("country", "") if meta_row is not None else "",
            "nationality": nationality,
            "role": meta_row.get("role", "") if meta_row is not None else "",
            "fame": meta_row.get("fame", "") if meta_row is not None else "",
            "matches": int(row.get("matches", 0) or 0),
            "grevscore": float(row.get("grevscore", 0) or 0),
            "rating": float(row.get("rating", 0) or 0),
            "impact": float(row.get("impact", 0) or 0),
            "form": float(row.get("form", 0) or 0),
            "kpd": float(row.get("kpd", 0) or 0),
            "kpr": float(row.get("kpr", 0) or 0),
            "accuracy_pct": float(row.get("accuracy_pct", 0) or 0),
            "hs_pct": float(row.get("hs_pct", 0) or 0),
            "kills": row.get("kills"),
            "deaths": row.get("deaths"),
            "damage_avg": row.get("damage_avg"),
            "favourite_map": _resolve_favourite_map(meta_row),
            "best_map": _best_map_by_grevscore(player_rows),
            "best_map_label": f"Best Map (Season): {_best_map_by_grevscore(player_rows)}",
            "best_side": _best_side_for_player_scope(player_rows, season_tactics),
            "trend": _trend_for_player_scope(player_rows),
            "tier_grevscores": _tier_grevscores(player_rows),
            "last_match": _last_match_summary(player_rows),
            "best_match": _best_match_summary(player_rows),
            "photo_uri": image_data_uri(photo.get("path")),
            "team_logo_uri": team_logo,
            "photo_missing_reason": photo.get("reason"),
            "achievements": achievements,
            "achievements_hidden": hidden,
        }
        payload["desc"] = (
            f"Season-specific line: {payload['matches']} matches, "
            f"{payload['grevscore']:.2f} GrevScore, {payload['kpd']:.2f} K/D. "
            f"Kills/deaths: {_fmt_int(payload.get('kills'))}/{_fmt_int(payload.get('deaths'))}."
        ) if (payload.get("kills") is not None and payload.get("deaths") is not None) else player_description(payload)
        payloads.append(payload)
    return sorted(payloads, key=lambda p: (p.get("grevscore", 0), p.get("matches", 0)), reverse=True)


def render_player_card_grid(payloads: list[dict]) -> None:
    if not payloads:
        st.info("No players meet the selected minimum matches for this season.")
        return
    for start in range(0, len(payloads), 5):
        cols = st.columns(5, gap="small")
        for col_idx, payload in enumerate(payloads[start : start + 5]):
            with cols[col_idx]:
                player_card(payload)


def _numeric_series(group: pd.DataFrame, col: str) -> pd.Series:
    if col not in group.columns:
        return pd.Series(pd.NA, index=group.index, dtype="Float64")
    return pd.to_numeric(group[col], errors="coerce")


def _sum_if_present(group: pd.DataFrame, col: str) -> float:
    values = _numeric_series(group, col).dropna()
    return float(values.sum()) if not values.empty else math.nan


def _win_pct_from_sums(wins, losses) -> float | None:
    if wins is None or losses is None or pd.isna(wins) or pd.isna(losses):
        return None
    denominator = float(wins) + float(losses)
    if denominator <= 0:
        return None
    return float(wins) / denominator * 100


def _weighted_pct_from_rows(group: pd.DataFrame) -> float | None:
    """Prefer summed wins/losses; only fall back to weighted row win-rate when counts are unavailable."""
    wins = _numeric_series(group, "wins")
    losses = _numeric_series(group, "losses")
    if wins.notna().any() or losses.notna().any():
        pct = _win_pct_from_sums(wins.fillna(0).sum(), losses.fillna(0).sum())
        if pct is not None:
            return pct
    if {"win_rate_pct", "total_rounds"}.issubset(group.columns):
        rates = pd.to_numeric(group["win_rate_pct"], errors="coerce")
        weights = pd.to_numeric(group["total_rounds"], errors="coerce")
        valid = rates.notna() & weights.notna() & (weights > 0)
        if valid.any():
            return float((rates[valid] * weights[valid]).sum() / weights[valid].sum())
    return None


def _normalize_tier_value(value) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none", "null", "<na>", "unknown"}:
        return "Unknown"
    key = re.sub(r"[^a-z0-9]+", "", text.casefold())
    if key.startswith("stier") or key == "s":
        return "S"
    if key.startswith("atier") or key == "a":
        return "A"
    if key.startswith("btier") or key == "b":
        return "B"
    if key.startswith("ctier") or key == "c":
        return "C"
    return "Unknown"


def _tier_series(group: pd.DataFrame) -> pd.Series:
    tier_col = _first_existing_col(group, ("tier", "Tier"))
    if not tier_col:
        return pd.Series("Unknown", index=group.index, dtype="object")
    return group[tier_col].map(_normalize_tier_value).astype("object")


def _tier_round_counts(group: pd.DataFrame, tiers: pd.Series) -> dict[str, float]:
    working = pd.DataFrame({"tier": tiers})
    if "total_rounds" in group.columns:
        rounds = pd.to_numeric(group["total_rounds"], errors="coerce")
        if rounds.notna().any():
            working["usage"] = rounds.fillna(0)
            return {str(k): float(v) for k, v in working.groupby("tier", dropna=False)["usage"].sum().items() if float(v) > 0}
    working["usage"] = 1
    return {str(k): float(v) for k, v in working.groupby("tier", dropna=False)["usage"].sum().items() if float(v) > 0}


def _tier_spread_label(counts: dict[str, float]) -> str:
    parts = []
    for tier in ["S", "A", "B", "C", "Unknown"]:
        value = counts.get(tier)
        if value is not None and value > 0:
            suffix = "r" if float(value).is_integer() else "r"
            parts.append(f"{tier}: {_fmt_int(value)}{suffix}")
    return " · ".join(parts) if parts else NOT_AVAILABLE


def _tier_win_rates(group: pd.DataFrame, tiers: pd.Series) -> dict[str, float | None]:
    rates: dict[str, float | None] = {tier: None for tier in ["S", "A", "B", "C"]}
    if not ({"wins", "losses"}.issubset(group.columns)):
        return rates
    working = group.copy()
    working["_tier_norm"] = tiers
    working["wins"] = pd.to_numeric(working["wins"], errors="coerce")
    working["losses"] = pd.to_numeric(working["losses"], errors="coerce")
    for tier, tier_rows in working.groupby("_tier_norm", dropna=False):
        tier_key = str(tier)
        if tier_key not in rates:
            continue
        if not (tier_rows["wins"].notna().any() or tier_rows["losses"].notna().any()):
            continue
        rates[tier_key] = _win_pct_from_sums(tier_rows["wins"].fillna(0).sum(), tier_rows["losses"].fillna(0).sum())
    return rates


def _tier_extreme_label(rates: dict[str, float | None], best: bool = True) -> str:
    valid = [(tier, rate) for tier, rate in rates.items() if rate is not None and pd.notna(rate)]
    if not valid:
        return NOT_AVAILABLE
    tier, rate = sorted(valid, key=lambda item: (item[1], item[0]), reverse=best)[0]
    return f"{tier} ({rate:.1f}%)"


def aggregate_top_tactics_by_map(tactics: pd.DataFrame, min_rounds: int = 1, top_n: int | None = TACTIC_TOP_N) -> pd.DataFrame:
    if tactics.empty or "tactic_name" not in tactics.columns:
        return pd.DataFrame()
    working = tactics.copy()
    working["resolved_season"] = _season_value_series(working)
    working["tactic_name"] = working["tactic_name"].astype(str).str.strip()
    working["map"] = _resolved_tactic_map_series(working)
    working["side"] = _normalized_tactic_side_series(working)
    working = working[(working["tactic_name"] != "") & working["resolved_season"].notna()].copy()
    if working.empty:
        return pd.DataFrame()

    for col in ["wins", "losses", "total_rounds", "win_rate_pct"]:
        if col in working.columns:
            working[col] = pd.to_numeric(working[col], errors="coerce")

    rows = []
    group_cols = ["resolved_season", "map", "side", "tactic_name"]
    for (season, map_name, side, tactic_name), group in working.groupby(group_cols, dropna=False):
        row_count = int(len(group))
        round_values = _numeric_series(group, "total_rounds")
        has_rounds = round_values.notna().any()
        total_rounds = float(round_values.sum()) if has_rounds else float(row_count)
        total_matches = int(group["match_id"].nunique()) if "match_id" in group.columns else row_count
        wins = _sum_if_present(group, "wins")
        losses = _sum_if_present(group, "losses")
        total_win_pct = _win_pct_from_sums(wins, losses)
        if total_win_pct is None:
            total_win_pct = _weighted_pct_from_rows(group)

        tiers = _tier_series(group)
        tier_counts = _tier_round_counts(group, tiers)
        tier_rates = _tier_win_rates(group, tiers)
        last_used_sort = pd.NaT
        last_used = NOT_AVAILABLE
        if "date" in group.columns:
            last_used_sort = pd.to_datetime(group["date"], errors="coerce").max()
            if pd.notna(last_used_sort):
                last_used = last_used_sort.strftime("%Y-%m-%d")
        avg_rounds = total_rounds / total_matches if total_matches else math.nan
        row = {
            "resolved_season": int(season),
            "map": str(map_name or "Unknown Map"),
            "side": _normalize_tactic_side(side),
            "tactic_name": tactic_name,
            "total_rounds": total_rounds,
            "total_matches": total_matches,
            "wins": wins,
            "losses": losses,
            "total_win_pct": total_win_pct,
            "s_tier_win_pct": tier_rates["S"],
            "a_tier_win_pct": tier_rates["A"],
            "b_tier_win_pct": tier_rates["B"],
            "c_tier_win_pct": tier_rates["C"],
            "tier_spread": _tier_spread_label(tier_counts),
            "last_used": last_used,
            "last_used_sort": last_used_sort,
            "avg_rounds_per_match": avg_rounds,
            "best_tier": _tier_extreme_label(tier_rates, best=True),
            "worst_tier": _tier_extreme_label(tier_rates, best=False),
            "_usage_sort": total_rounds,
            "_row_count": row_count,
        }
        # Backward-compatible labels used by summary code elsewhere on this page.
        row.update(
            {
                "Map": row["map"],
                "Side": row["side"],
                "Tactic name": row["tactic_name"],
                "Usage rounds": row["total_rounds"],
                "Matches used": row["total_matches"],
                "Wins": row["wins"],
                "Losses": row["losses"],
                "Win rate %": row["total_win_pct"],
                "Tier spread": row["tier_spread"],
                "Last used date": row["last_used"],
            }
        )
        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out[out["total_rounds"].fillna(0) >= int(min_rounds)].copy()
    if out.empty:
        return out
    out = _sort_tactic_rows(out, "Usage rounds", "Descending", top_n=top_n)
    return out


def aggregate_top_tactics(tactics: pd.DataFrame, min_rounds: int = 1, top_n: int = TACTIC_TOP_N) -> pd.DataFrame:
    return aggregate_top_tactics_by_map(tactics, min_rounds=min_rounds, top_n=top_n)


def _season_team_summary(season_df: pd.DataFrame, season_tactics: pd.DataFrame, season: int, season_windows: pd.DataFrame | None = None) -> dict:
    comp_col = "grouped_competition_name" if "grouped_competition_name" in season_df.columns else "competition"
    kills = _numeric_sum(season_df, "kills")
    deaths = _numeric_sum(season_df, "deaths")
    return {
        "season": season,
        "Season": _season_label(season),
        "Season Window": _season_window_range(season_windows, season),
        "Match Data Range": _date_range(season_df),
        "Matches": _match_count(season_df),
        "Unique opponents": _unique_count(season_df, "opponent_team"),
        "Competitions": _unique_count(season_df, comp_col),
        "Maps": _unique_count(season_df, "map") or _unique_count(season_tactics, "map"),
        "Avg GrevScore": _numeric_mean(season_df, "grevscore"),
        "Avg K/D": _numeric_mean(season_df, "kpd"),
        "Avg Impact": _numeric_mean(season_df, "impact"),
        "Total K/D": f"{_fmt_int(kills)} / {_fmt_int(deaths)}" if kills is not None or deaths is not None else NOT_AVAILABLE,
        "Best map by GrevScore": _best_map_by_grevscore(season_df),
        "Most played map": _most_played_map(season_df),
        "Unique players": int(season_df["player_key"].nunique()) if "player_key" in season_df.columns else 0,
    }


def build_season_comparison(
    roster_matches: pd.DataFrame,
    tactics: pd.DataFrame,
    seasons: list[int],
    min_player_matches: int = 1,
    tactic_min_rounds: int = 1,
    season_windows: pd.DataFrame | None = None,
) -> pd.DataFrame:
    top_tactics = aggregate_top_tactics(_filter_seasons(tactics, seasons), min_rounds=tactic_min_rounds, top_n=10_000)
    rows = []
    for season in seasons:
        season_df = _filter_season(roster_matches, season)
        season_tactics = _filter_season(tactics, season)
        row = _season_team_summary(season_df, season_tactics, season, season_windows=season_windows)
        tactic_rows = top_tactics[top_tactics["resolved_season"] == int(season)] if not top_tactics.empty else pd.DataFrame()
        if not tactic_rows.empty:
            tactic_usage = tactic_rows.groupby("Tactic name", dropna=False).agg(usage=("Usage rounds", "sum"), matches=("Matches used", "sum")).reset_index()
            most_used = tactic_usage.sort_values(["usage", "matches"], ascending=[False, False], na_position="last").head(1).iloc[0]
            row["Most used tactic overall"] = f"{most_used['Tactic name']} ({_fmt_int(most_used['usage'])})"
            most_used_map = tactic_rows.groupby("Map", dropna=False)["Usage rounds"].sum().sort_values(ascending=False).head(1)
            row["Most used map"] = f"{most_used_map.index[0]} ({_fmt_int(most_used_map.iloc[0])})" if not most_used_map.empty else NOT_AVAILABLE
        else:
            row["Most used tactic overall"] = NOT_AVAILABLE
            row["Most used map"] = NOT_AVAILABLE
        threshold = max(int(tactic_min_rounds), 10)
        best_pool = tactic_rows.copy()
        if not best_pool.empty and "Usage rounds" in best_pool.columns and best_pool["Usage rounds"].notna().any():
            best_pool = best_pool[best_pool["Usage rounds"].fillna(0) >= threshold]
        if not best_pool.empty:
            best = best_pool.sort_values(["Win rate %", "_usage_sort"], ascending=[False, False], na_position="last").head(1).iloc[0]
            row["Best tactic overall"] = f"{best['Tactic name']} on {best['Map']} ({_fmt(best.get('Win rate %'), 1, '%')})"
        else:
            row["Best tactic overall"] = NOT_AVAILABLE
        players = season_player_summary(season_df)
        if not players.empty:
            eligible = players[players["matches"] >= int(min_player_matches)]
            if eligible.empty:
                eligible = players
            best_player = eligible.sort_values(["grevscore", "matches"], ascending=[False, False], na_position="last").head(1).iloc[0]
            row["Best player"] = f"{best_player['player']} ({_fmt(best_player.get('grevscore'), 2)})"
        else:
            row["Best player"] = NOT_AVAILABLE
        rows.append(row)
    comparison = pd.DataFrame(rows)
    if comparison.empty:
        return comparison
    for col in ["Avg GrevScore", "Avg K/D", "Avg Impact"]:
        comparison[col] = comparison[col].map(lambda v: _fmt(v, 2))
    return comparison[
        [
            "Season",
            "Matches",
            "Season Window",
            "Match Data Range",
            "Avg GrevScore",
            "Avg K/D",
            "Avg Impact",
            "Unique players",
            "Unique opponents",
            "Competitions",
            "Maps",
            "Most used map",
            "Most used tactic overall",
            "Best tactic overall",
            "Best player",
        ]
    ]


def _render_season_stat_cards(summary: dict) -> None:
    cards = [
        ("Season Window", summary["Season Window"], "Official timeline dates", "mid"),
        ("Match Data Range", summary["Match Data Range"], "Available official match rows", "mid"),
        ("Matches Played", summary["Matches"], "Unique match IDs", "good"),
        ("Unique Opponents", summary["Unique opponents"], "Distinct opponents", "mid"),
        ("Competitions Entered", summary["Competitions"], "Grouped when available", "mid"),
        ("Maps Played", summary["Maps"], "Distinct maps", "mid"),
        ("Avg GrevScore", _fmt(summary["Avg GrevScore"], 2), "Mean player-row GrevScore", stat_tone("grevscore", summary["Avg GrevScore"] or 0)),
        ("Avg K/D", _fmt(summary["Avg K/D"], 2), "Mean player-row KPD", stat_tone("kpd", summary["Avg K/D"] or 0)),
        ("Avg Impact", _fmt(summary["Avg Impact"], 1), "Mean player-row impact", stat_tone("impact", summary["Avg Impact"] or 0)),
        ("Total Kills / Deaths", summary["Total K/D"], "Summed player rows", "mid"),
        ("Best Map", summary["Best map by GrevScore"], "Highest avg GrevScore", "good"),
        ("Most Played Map", summary["Most played map"], "Highest map match count", "mid"),
        ("Active Players", summary["Unique players"], "Normalized identities", "good"),
    ]
    cols = st.columns(4, gap="small")
    for idx, (title, value, note, tone) in enumerate(cards):
        with cols[idx % 4]:
            stat_card(title, value, note, tone)


TACTIC_SORT_OPTIONS = [
    "Usage rounds",
    "Total matches",
    "Total win %",
    "S-tier win %",
    "A-tier win %",
    "B-tier win %",
    "C-tier win %",
    "Tactic name",
    "Last used",
]

TACTIC_SORT_COLUMNS = {
    "Usage rounds": "total_rounds",
    "Total matches": "total_matches",
    "Total win %": "total_win_pct",
    "S-tier win %": "s_tier_win_pct",
    "A-tier win %": "a_tier_win_pct",
    "B-tier win %": "b_tier_win_pct",
    "C-tier win %": "c_tier_win_pct",
    "Tactic name": "tactic_name",
    "Last used": "last_used_sort",
}


def _fmt_win_rate(value) -> str:
    return _fmt(value, 1, "%") if value is not None and pd.notna(value) else NOT_AVAILABLE


def _html_escape(value) -> str:
    return html.escape(str(value if value is not None else NOT_AVAILABLE), quote=True)


def _tone_for_win_rate(value) -> str:
    if value is None or pd.isna(value):
        return "muted"
    rate = float(value)
    if rate >= 60:
        return "good"
    if rate >= 50:
        return "mid"
    if rate >= 40:
        return "poor"
    return "bad"


def _chip(label: str, value, tone: str = "neutral") -> str:
    tone_class = f" season-preview-chip-{tone} chip-{tone}" if tone and tone != "neutral" else ""
    return (
        f"<div class='season-preview-chip chip{tone_class}'>"
        f"<span class='season-preview-chip-label'>{_html_escape(label)}</span>"
        f"<span class='season-preview-chip-value'>{_html_escape(value)}</span>"
        "</div>"
    )


def _chip_row(chips: list[str]) -> str:
    return f"<div class='season-preview-chip-row'>{''.join(chips)}</div>"


def _sort_tactic_rows(top_tactics: pd.DataFrame, sort_by: str, direction: str, top_n: int | None = TACTIC_TOP_N) -> pd.DataFrame:
    if top_tactics.empty:
        return top_tactics.copy()
    sort_col = TACTIC_SORT_COLUMNS.get(sort_by, "total_rounds")
    if sort_col not in top_tactics.columns:
        sort_col = "total_rounds" if "total_rounds" in top_tactics.columns else "Usage rounds"
    ascending = direction == "Ascending"
    sorted_frames = []
    group_cols = [col for col in ["resolved_season", "map", "side"] if col in top_tactics.columns]
    if not group_cols:
        group_cols = [col for col in ["resolved_season", "Map", "Side"] if col in top_tactics.columns]

    for _, group in top_tactics.groupby(group_cols, dropna=False, sort=True) if group_cols else [(None, top_tactics)]:
        working = group.copy()
        if sort_col == "tactic_name":
            working["_sort_value"] = working[sort_col].fillna("").astype(str).str.casefold()
            working = working.sort_values(["_sort_value"], ascending=[ascending], kind="mergesort")
        else:
            working["_sort_value"] = pd.to_datetime(working[sort_col], errors="coerce") if sort_col == "last_used_sort" else pd.to_numeric(working[sort_col], errors="coerce")
            # N/A values always go last, regardless of requested direction.
            working["_sort_missing"] = working["_sort_value"].isna()
            tie_cols = []
            ascending_flags = [True, ascending]
            if sort_col != "total_rounds" and "total_rounds" in working.columns:
                tie_cols.append("total_rounds")
                ascending_flags.append(False)
            if sort_col != "total_matches" and "total_matches" in working.columns:
                tie_cols.append("total_matches")
                ascending_flags.append(False)
            if "tactic_name" in working.columns:
                working["_tactic_name_sort"] = working["tactic_name"].fillna("").astype(str).str.casefold()
                tie_cols.append("_tactic_name_sort")
                ascending_flags.append(True)
            working = working.sort_values(["_sort_missing", "_sort_value", *tie_cols], ascending=ascending_flags, kind="mergesort")
        if top_n is not None:
            working = working.head(int(top_n)).copy()
        working["Rank"] = range(1, len(working) + 1)
        sorted_frames.append(working.drop(columns=[c for c in ["_sort_value", "_sort_missing", "_tactic_name_sort"] if c in working.columns]))
    if not sorted_frames:
        return top_tactics.iloc[0:0].copy()
    return pd.concat(sorted_frames, ignore_index=True)


def _format_tactics_display_df(rows: pd.DataFrame) -> pd.DataFrame:
    """Return tactic rows with only Streamlit-facing columns and safe display names."""
    rename_map = {
        "tactic_name": "Tactic",
        "total_rounds": "Total rounds",
        "total_matches": "Total matches",
        "wins": "Wins",
        "losses": "Losses",
        "total_win_pct": "Total win %",
        "s_tier_win_pct": "S-tier win %",
        "a_tier_win_pct": "A-tier win %",
        "b_tier_win_pct": "B-tier win %",
        "c_tier_win_pct": "C-tier win %",
        "tier_spread": "Tier spread",
        "last_used": "Last used",
    }
    visible_columns = [
        "Rank",
        "tactic_name",
        "total_rounds",
        "total_matches",
        "wins",
        "losses",
        "total_win_pct",
        "s_tier_win_pct",
        "a_tier_win_pct",
        "b_tier_win_pct",
        "c_tier_win_pct",
        "tier_spread",
        "last_used",
    ]
    display = rows.loc[:, [col for col in visible_columns if col in rows.columns]].copy().rename(columns=rename_map)

    for col in ("Rank", "Total rounds", "Total matches", "Wins", "Losses"):
        if col in display.columns:
            display[col] = pd.to_numeric(display[col], errors="coerce")
    for col in ("Total win %", "S-tier win %", "A-tier win %", "B-tier win %", "C-tier win %"):
        if col in display.columns:
            display[col] = pd.to_numeric(display[col], errors="coerce")
    if "Last used" in display.columns:
        dates = pd.to_datetime(display["Last used"], errors="coerce")
        display["Last used"] = dates.dt.strftime("%Y-%m-%d").fillna(NOT_AVAILABLE)
    for col in ("Tactic", "Tier spread"):
        if col in display.columns:
            display[col] = display[col].fillna(NOT_AVAILABLE).astype(str)
    return display


def _tactics_column_config() -> dict:
    return {
        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
        "Tactic": st.column_config.TextColumn("Tactic", width="large"),
        "Total rounds": st.column_config.NumberColumn("Total rounds", format="%d"),
        "Total matches": st.column_config.NumberColumn("Total matches", format="%d"),
        "Wins": st.column_config.NumberColumn("Wins", format="%d"),
        "Losses": st.column_config.NumberColumn("Losses", format="%d"),
        "Total win %": st.column_config.ProgressColumn("Total win %", min_value=0, max_value=100, format="%.1f%%"),
        "S-tier win %": st.column_config.ProgressColumn("S-tier win %", min_value=0, max_value=100, format="%.1f%%"),
        "A-tier win %": st.column_config.ProgressColumn("A-tier win %", min_value=0, max_value=100, format="%.1f%%"),
        "B-tier win %": st.column_config.ProgressColumn("B-tier win %", min_value=0, max_value=100, format="%.1f%%"),
        "C-tier win %": st.column_config.ProgressColumn("C-tier win %", min_value=0, max_value=100, format="%.1f%%"),
        "Tier spread": st.column_config.TextColumn("Tier spread", width="medium"),
        "Last used": st.column_config.TextColumn("Last used", width="small"),
    }


def _side_summary(side_df: pd.DataFrame) -> dict:
    usage_col = "total_rounds" if "total_rounds" in side_df.columns else "Usage rounds"
    match_col = "total_matches" if "total_matches" in side_df.columns else "Matches used"
    win_col = "total_win_pct" if "total_win_pct" in side_df.columns else "Win rate %"
    usage = pd.to_numeric(side_df.get(usage_col, pd.Series(dtype=float)), errors="coerce").fillna(0)
    matches = pd.to_numeric(side_df.get(match_col, pd.Series(dtype=float)), errors="coerce").fillna(0)
    rates = pd.to_numeric(side_df.get(win_col, pd.Series(dtype=float)), errors="coerce").dropna()
    tactic_col = "tactic_name" if "tactic_name" in side_df.columns else "Tactic name" if "Tactic name" in side_df.columns else "Tactic"
    most_used_tactic = NOT_AVAILABLE
    if tactic_col in side_df.columns and not side_df.empty:
        sort_cols = [col for col in (usage_col, match_col, win_col) if col in side_df.columns]
        sorted_rows = side_df.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last") if sort_cols else side_df
        most_used_tactic = _first_text(sorted_rows[tactic_col])
    return {
        "tactics_shown": int(len(side_df)),
        "usage_rounds": float(usage.sum()),
        "total_matches": float(matches.sum()),
        "best_win_rate": None if rates.empty else float(rates.max()),
        "most_used_tactic": most_used_tactic,
    }


def _streamlit_container(border: bool = True):
    try:
        return st.container(border=border)
    except TypeError:
        return st.container()


def _render_side_header(side_name: str, side_df: pd.DataFrame, tactics_per_side: int) -> None:
    summary = _side_summary(side_df)
    side_label = {"Red": "Red side", "Blue": "Blue side"}.get(side_name, str(side_name or "Unknown side"))
    side_class = "side-red" if side_name == "Red" else "side-blue" if side_name == "Blue" else "side-unknown"
    best_rate = summary["best_win_rate"]
    chips = [
        _chip("Tactics shown", _fmt_int(summary["tactics_shown"]), "neutral"),
        _chip("Total rounds", _fmt_int(summary["usage_rounds"]), "neutral"),
        _chip("Total matches", _fmt_int(summary["total_matches"]), "neutral"),
        _chip("Best total win", _fmt_win_rate(best_rate), _tone_for_win_rate(best_rate)),
        _chip("Most used", summary["most_used_tactic"], "mid"),
    ]
    st.markdown(
        f"<div class='season-preview-side-panel {side_class}'>"
        "<div class='season-preview-side-head'>"
        f"<div><div class='season-preview-side-title'>{_html_escape(side_label)} — Top {_html_escape(tactics_per_side)}</div>"
        "<div class='season-preview-side-meta'>Rank resets for this map side</div></div>"
        "</div>"
        f"{_chip_row(chips)}"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_tactics_dataframe(side_df: pd.DataFrame, side_name: str) -> None:
    display_df = _format_tactics_display_df(side_df)
    table_height = min(520, 44 + (len(display_df) + 1) * 34)
    side_class = "side-red" if side_name == "Red" else "side-blue" if side_name == "Blue" else "side-unknown"
    st.markdown(f"<div class='table-frame season-preview-table-shell {side_class}'>", unsafe_allow_html=True)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=table_height,
        column_config=_tactics_column_config(),
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_side_tactics(side_name: str, side_df: pd.DataFrame, tactics_per_side: int) -> None:
    if side_df.empty:
        return
    with _streamlit_container(border=False):
        _render_side_header(side_name, side_df, tactics_per_side)
        _render_tactics_dataframe(side_df, side_name)


def _side_sort_key(side: str) -> tuple[int, str]:
    order = {"Red": 0, "Blue": 1, "Unknown side": 2}
    label = str(side or "Unknown side")
    return (order.get(label, 3), label)



def _render_map_header(map_name, map_rows: pd.DataFrame, red_rows: pd.DataFrame, blue_rows: pd.DataFrame, unknown_rows: pd.DataFrame) -> None:
    usage_values = pd.to_numeric(map_rows.get("total_rounds", pd.Series(dtype=float)), errors="coerce")
    usage_total = usage_values.fillna(0).sum()
    red_summary = _side_summary(red_rows)
    blue_summary = _side_summary(blue_rows)
    best_rate_values = pd.to_numeric(map_rows.get("total_win_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    best_total_win = None if best_rate_values.empty else float(best_rate_values.max())
    chips = [
        _chip("Total rounds", _fmt_int(usage_total), "neutral"),
        _chip("Best total win", _fmt_win_rate(best_total_win), _tone_for_win_rate(best_total_win)),
        _chip("Red shown", _fmt_int(red_summary["tactics_shown"]), "bad"),
        _chip("Blue shown", _fmt_int(blue_summary["tactics_shown"]), "good"),
    ]
    if not unknown_rows.empty:
        chips.append(_chip("Unknown side", _fmt_int(len(unknown_rows)), "muted"))
    st.markdown(
        "<div class='season-preview-map-panel'>"
        "<div class='season-preview-map-head'>"
        f"<div><div class='season-preview-map-title'>{_html_escape(map_name)}</div>"
        "<div class='season-preview-map-meta'>Official tactics · split by Red / Blue side</div></div>"
        "</div>"
        f"{_chip_row(chips)}"
        "</div>",
        unsafe_allow_html=True,
    )

def _render_tactics_by_map(top_tactics: pd.DataFrame, season: int, min_rounds: int, sort_by: str, sort_direction: str, tactics_per_side: int) -> None:
    if top_tactics.empty or "resolved_season" not in top_tactics.columns:
        season_tactics = pd.DataFrame()
    else:
        season_tactics = top_tactics[top_tactics["resolved_season"] == int(season)].copy()

    if not season_tactics.empty and "total_rounds" in season_tactics.columns:
        usage_rounds = pd.to_numeric(season_tactics["total_rounds"], errors="coerce").fillna(0)
        season_tactics = season_tactics[usage_rounds >= int(min_rounds)].copy()

    if season_tactics.empty:
        st.info("No official tactics rows meet the selected usage threshold for this season.")
        return

    season_tactics = _sort_tactic_rows(season_tactics, sort_by, sort_direction, top_n=tactics_per_side)
    map_col = "map" if "map" in season_tactics.columns else "Map"
    side_col = "side" if "side" in season_tactics.columns else "Side"
    sort_columns = [col for col in (map_col, side_col, "Rank") if col in season_tactics.columns]
    if sort_columns:
        season_tactics = season_tactics.sort_values(sort_columns)

    for map_name, map_rows in season_tactics.groupby(map_col, dropna=False):
        if map_rows.empty:
            continue

        red_rows = map_rows[map_rows[side_col] == "Red"] if side_col in map_rows.columns else pd.DataFrame()
        blue_rows = map_rows[map_rows[side_col] == "Blue"] if side_col in map_rows.columns else pd.DataFrame()
        unknown_rows = map_rows[map_rows[side_col] == "Unknown side"] if side_col in map_rows.columns else pd.DataFrame()
        if red_rows.empty and blue_rows.empty and unknown_rows.empty:
            continue

        with _streamlit_container(border=False):
            _render_map_header(map_name, map_rows, red_rows, blue_rows, unknown_rows)
            side_labels = sorted(map_rows[side_col].dropna().unique().tolist(), key=_side_sort_key)
            for side in side_labels:
                side_rows = map_rows[map_rows[side_col] == side].sort_values("Rank")
                if side_rows.empty:
                    continue
                _render_side_tactics(side, side_rows, tactics_per_side)


def _render_tactics_table(top_tactics: pd.DataFrame, season: int) -> None:
    _render_tactics_by_map(top_tactics, season, min_rounds=1, sort_by="Usage rounds", sort_direction="Descending", tactics_per_side=TACTIC_TOP_N)


def render(data: dict):
    full_matches = data.get("player_matches_full", data.get("player_matches", pd.DataFrame())).copy()
    tactics = data.get("tactics", pd.DataFrame()).copy()
    players = data.get("players", pd.DataFrame()).copy()
    achievements_df = data.get("achievements", pd.DataFrame()).copy()
    season_windows = data.get("season_windows", pd.DataFrame()).copy()

    section_header(
        "Season Preview",
        "Compare Medisports season by season across roster, form, maps, competitions, and tactical usage.",
    )

    roster_matches = get_medisports_roster_df(full_matches, player_col="player")
    if roster_matches.empty:
        st.warning("No Medisports player rows are available in the official match data.")
        return
    roster_matches["player_key"] = roster_matches.get("player_clean", roster_matches["player"]).map(normalize_player_key)
    roster_matches = roster_matches[roster_matches["player_key"] != ""].copy()

    seasons = _season_options(roster_matches, tactics)
    if not seasons:
        st.warning("No resolved season values are available in the official player or tactics data.")
        return

    latest = seasons[-1]
    with _streamlit_container(border=False):
        st.markdown(
            "<div class='season-preview-controls-head'>"
            "<div class='season-preview-controls-title'>Tactics controls</div>"
            "<div class='season-preview-map-meta'>Season filters, player cards, and official tactic table sorting</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns([2.2, 1.2, 1.2], gap="small")
        with c1:
            selected_seasons = st.multiselect(
                "Seasons",
                options=seasons,
                default=seasons,
                format_func=_season_label,
                key="season_preview_seasons",
            )
        with c2:
            sort_order = st.radio(
                "Sort seasons",
                options=["Newest first", "Oldest first"],
                horizontal=False,
                key="season_preview_sort",
            )
        with c3:
            min_player_matches = st.slider("Minimum player matches", min_value=1, max_value=10, value=1, step=1, key="season_preview_min_player_matches")
        c4, c5, c6 = st.columns([1.2, 1, 1], gap="small")
        with c4:
            tactic_min_rounds = st.slider("Tactic minimum rounds", min_value=1, max_value=100, value=1, step=1, key="season_preview_tactic_min_rounds")
        with c5:
            show_tactics = st.toggle("Show tactics tables", value=True, key="season_preview_show_tactics")
        with c6:
            show_players = st.toggle("Show detailed player cards", value=True, key="season_preview_show_players")
        st.caption("Tactics table controls apply to every season/map/side table below.")
        c7, c8, c9 = st.columns([1.5, 1.1, 1.4], gap="small")
        with c7:
            tactic_sort_by = st.selectbox("Sort tactics by", options=TACTIC_SORT_OPTIONS, index=0, key="season_preview_tactic_sort_by")
        with c8:
            tactic_sort_direction = st.selectbox("Sort direction", options=["Descending", "Ascending"], index=0, key="season_preview_tactic_sort_direction")
        with c9:
            tactics_per_side = st.slider("Tactics shown per side", min_value=3, max_value=15, value=TACTIC_TOP_N, step=1, key="season_preview_tactics_per_side")

    selected_seasons = [int(s) for s in selected_seasons]
    if not selected_seasons:
        st.info("Select at least one season to build the comparison board.")
        return
    selected_seasons = sorted(selected_seasons, reverse=(sort_order == "Newest first"))

    section_header("All-season comparison summary", "Compact comparison across selected official seasons.")
    comparison = build_season_comparison(roster_matches, tactics, selected_seasons, min_player_matches, tactic_min_rounds, season_windows=season_windows)
    if comparison.empty:
        st.info("No season comparison rows are available for the current selection.")
    else:
        st.dataframe(comparison, use_container_width=True, hide_index=True)

    section_header("Season rows", "Each section uses official player match rows and official tactics rows only.")
    top_tactics = aggregate_top_tactics_by_map(_filter_seasons(tactics, selected_seasons), min_rounds=tactic_min_rounds, top_n=None)
    for season in selected_seasons:
        season_df = _filter_season(roster_matches, season)
        season_tactics = _filter_season(tactics, season)
        summary = _season_team_summary(season_df, season_tactics, season, season_windows=season_windows)
        with st.expander(_season_label(season), expanded=(int(season) == int(latest))):
            _render_season_stat_cards(summary)
            if show_players:
                section_header("Players active this season", f"Season-specific player-card payloads with a minimum of {min_player_matches} match(es).")
                payloads = build_player_card_payloads(season_df, season_tactics, players, achievements_df, min_player_matches, season)
                render_player_card_grid(payloads)
            if show_tactics:
                section_header("Most-used tactics by map and side", f"Top {tactics_per_side} per side. Red and Blue are ranked separately within each map using the selected sorting controls.")
                _render_tactics_by_map(top_tactics, season, tactic_min_rounds, tactic_sort_by, tactic_sort_direction, tactics_per_side)
