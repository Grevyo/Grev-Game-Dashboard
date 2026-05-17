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
TACTIC_TOP_N = 15


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


def _weighted_pct_from_rows(group: pd.DataFrame) -> float | None:
    wins = pd.to_numeric(group.get("wins"), errors="coerce") if "wins" in group.columns else pd.Series(dtype=float)
    losses = pd.to_numeric(group.get("losses"), errors="coerce") if "losses" in group.columns else pd.Series(dtype=float)
    if not wins.dropna().empty or not losses.dropna().empty:
        wins_sum = float(wins.fillna(0).sum())
        losses_sum = float(losses.fillna(0).sum())
        denom = wins_sum + losses_sum
        if denom > 0:
            return wins_sum / denom * 100
    if {"win_rate_pct", "total_rounds"}.issubset(group.columns):
        rates = pd.to_numeric(group["win_rate_pct"], errors="coerce")
        weights = pd.to_numeric(group["total_rounds"], errors="coerce")
        valid = rates.notna() & weights.notna() & (weights > 0)
        if valid.any():
            return float((rates[valid] * weights[valid]).sum() / weights[valid].sum())
    if "win_rate_pct" in group.columns:
        rates = pd.to_numeric(group["win_rate_pct"], errors="coerce").dropna()
        if not rates.empty:
            return float(rates.mean())
    return None


def aggregate_top_tactics_by_map(tactics: pd.DataFrame, min_rounds: int = 1, top_n: int = TACTIC_TOP_N) -> pd.DataFrame:
    if tactics.empty or "tactic_name" not in tactics.columns:
        return pd.DataFrame()
    working = tactics.copy()
    working["resolved_season"] = _season_value_series(working)
    working["tactic_name"] = working["tactic_name"].astype(str).str.strip()
    working["map"] = _resolved_tactic_map_series(working)
    working = working[(working["tactic_name"] != "") & working["resolved_season"].notna()].copy()
    if working.empty:
        return pd.DataFrame()

    for col in ["wins", "losses", "total_rounds", "win_rate_pct"]:
        if col in working.columns:
            working[col] = pd.to_numeric(working[col], errors="coerce")
    tier_col = _first_existing_col(working, ("tier", "Tier"))

    rows = []
    for (season, map_name, tactic_name), group in working.groupby(["resolved_season", "map", "tactic_name"], dropna=False):
        row_count = int(len(group))
        round_values = pd.to_numeric(group["total_rounds"], errors="coerce") if "total_rounds" in group.columns else pd.Series(dtype=float)
        usage_rounds = float(round_values.sum()) if not round_values.dropna().empty else float(row_count)
        matches_used = int(group["match_id"].nunique()) if "match_id" in group.columns else row_count
        wins = float(group["wins"].sum()) if "wins" in group.columns and group["wins"].notna().any() else math.nan
        losses = float(group["losses"].sum()) if "losses" in group.columns and group["losses"].notna().any() else math.nan
        last_used = NOT_AVAILABLE
        if "date" in group.columns:
            max_date = pd.to_datetime(group["date"], errors="coerce").max()
            if pd.notna(max_date):
                last_used = max_date.strftime("%Y-%m-%d")
        rows.append(
            {
                "resolved_season": int(season),
                "Map": str(map_name or "Unknown Map"),
                "Tactic name": tactic_name,
                "Side": _value_counts_label(group, "side"),
                "Usage rounds": usage_rounds,
                "Matches used": matches_used,
                "Wins": wins,
                "Losses": losses,
                "Win rate %": _weighted_pct_from_rows(group),
                "Tier spread": _value_counts_label(group, tier_col, limit=4) if tier_col else NOT_AVAILABLE,
                "Last used date": last_used,
                "_usage_sort": usage_rounds,
                "_row_count": row_count,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out[out["Usage rounds"].fillna(0) >= int(min_rounds)].copy()
    if out.empty:
        return out
    out = out.sort_values(
        ["resolved_season", "Map", "_usage_sort", "Matches used", "Win rate %"],
        ascending=[True, True, False, False, False],
        na_position="last",
    )
    out["Rank"] = out.groupby(["resolved_season", "Map"]).cumcount() + 1
    return out[out["Rank"] <= int(top_n)].copy()


def aggregate_top_tactics(tactics: pd.DataFrame, min_rounds: int = 1, top_n: int = TACTIC_TOP_N) -> pd.DataFrame:
    return aggregate_top_tactics_by_map(tactics, min_rounds=min_rounds, top_n=top_n)


def _season_team_summary(season_df: pd.DataFrame, season_tactics: pd.DataFrame, season: int) -> dict:
    comp_col = "grouped_competition_name" if "grouped_competition_name" in season_df.columns else "competition"
    kills = _numeric_sum(season_df, "kills")
    deaths = _numeric_sum(season_df, "deaths")
    return {
        "season": season,
        "Season": _season_label(season),
        "Date range": _date_range(season_df),
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
) -> pd.DataFrame:
    top_tactics = aggregate_top_tactics(_filter_seasons(tactics, seasons), min_rounds=tactic_min_rounds, top_n=10_000)
    rows = []
    for season in seasons:
        season_df = _filter_season(roster_matches, season)
        season_tactics = _filter_season(tactics, season)
        row = _season_team_summary(season_df, season_tactics, season)
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
            "Date range",
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
        ("Date Range", summary["Date range"], "Official match dates", "mid"),
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


def _win_rate_tone(value) -> str:
    if value is None or pd.isna(value):
        return "neutral"
    value = float(value)
    if value >= 75:
        return "good"
    if value >= 55:
        return "mid"
    if value >= 45:
        return "neutral"
    return "poor"


def _html_text(value) -> str:
    if value is None or pd.isna(value):
        return NOT_AVAILABLE
    return html.escape(str(value))


def _fmt_win_rate(value) -> str:
    return _fmt(value, 1, "%") if value is not None and pd.notna(value) else NOT_AVAILABLE


def _render_tactics_by_map(top_tactics: pd.DataFrame, season: int, min_rounds: int) -> None:
    season_tactics = top_tactics[top_tactics["resolved_season"] == int(season)].copy() if not top_tactics.empty else pd.DataFrame()
    if season_tactics.empty:
        st.info("No official tactics rows meet the selected usage threshold for this season.")
        return

    css = """
    <style>
    .sp-map-panel {background: linear-gradient(135deg, rgba(12,18,32,.96), rgba(7,10,18,.98)); border: 1px solid rgba(148,163,184,.22); border-radius: 14px; margin: .75rem 0 1rem; overflow: hidden; box-shadow: 0 10px 28px rgba(0,0,0,.24);} 
    .sp-map-head {display:flex; justify-content:space-between; gap:1rem; align-items:flex-end; padding: .8rem 1rem; border-bottom: 1px solid rgba(148,163,184,.18); background: rgba(15,23,42,.72);} 
    .sp-map-title {font-size:1.05rem; font-weight:800; letter-spacing:.04em; color:#f8fafc; text-transform:uppercase;} 
    .sp-map-meta {display:flex; gap:.5rem; flex-wrap:wrap; justify-content:flex-end;} 
    .sp-pill {border:1px solid rgba(148,163,184,.28); background:rgba(30,41,59,.82); color:#cbd5e1; border-radius:999px; padding:.18rem .55rem; font-size:.72rem; font-weight:700; white-space:nowrap;} 
    .sp-table {width:100%; border-collapse: collapse; font-size:.78rem;} 
    .sp-table th {text-align:left; color:#94a3b8; font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; padding:.5rem .65rem; border-bottom:1px solid rgba(148,163,184,.16);} 
    .sp-table td {padding:.48rem .65rem; border-bottom:1px solid rgba(148,163,184,.08); color:#dbeafe; vertical-align:middle;} 
    .sp-table tr:last-child td {border-bottom:0;} 
    .sp-rank {display:inline-flex; width:1.65rem; height:1.65rem; align-items:center; justify-content:center; border-radius:.45rem; background:#f97316; color:#111827; font-weight:900;} 
    .sp-tactic {font-weight:800; color:#f8fafc;} 
    .sp-side {display:inline-block; border-radius:.35rem; background:rgba(59,130,246,.16); color:#bfdbfe; border:1px solid rgba(59,130,246,.26); padding:.12rem .38rem; font-weight:800;} 
    .sp-usage {font-weight:900; color:#fdba74;} 
    .sp-muted {color:#94a3b8; font-size:.72rem;} 
    .sp-wr {display:inline-block; border-radius:.35rem; padding:.12rem .4rem; font-weight:900;} 
    .sp-wr.good {background:rgba(34,197,94,.18); color:#86efac; border:1px solid rgba(34,197,94,.34);} 
    .sp-wr.mid {background:rgba(234,179,8,.18); color:#fde68a; border:1px solid rgba(234,179,8,.34);} 
    .sp-wr.neutral {background:rgba(148,163,184,.14); color:#cbd5e1; border:1px solid rgba(148,163,184,.28);} 
    .sp-wr.poor {background:rgba(239,68,68,.16); color:#fca5a5; border:1px solid rgba(239,68,68,.34);} 
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

    for map_name, map_rows in season_tactics.sort_values(["Map", "Rank"]).groupby("Map", dropna=False):
        map_rows = map_rows.sort_values("Rank")
        if map_rows.empty:
            continue
        usage_total = map_rows["Usage rounds"].sum()
        best_pool = map_rows[map_rows["Usage rounds"].fillna(0) >= int(min_rounds)].copy()
        best_label = NOT_AVAILABLE
        if not best_pool.empty:
            best = best_pool.sort_values(["Win rate %", "Usage rounds"], ascending=[False, False], na_position="last").head(1).iloc[0]
            best_label = f"{best['Tactic name']} · {_fmt_win_rate(best.get('Win rate %'))}"
        rows_html = []
        for _, row in map_rows.iterrows():
            wr = row.get("Win rate %")
            rows_html.append(
                "<tr>"
                f"<td><span class='sp-rank'>{int(row.get('Rank', 0))}</span></td>"
                f"<td><span class='sp-tactic'>{_html_text(row.get('Tactic name'))}</span></td>"
                f"<td><span class='sp-side'>{_html_text(row.get('Side'))}</span></td>"
                f"<td><span class='sp-usage'>{_fmt_int(row.get('Usage rounds'))}</span></td>"
                f"<td>{_fmt_int(row.get('Matches used'))}</td>"
                f"<td>{_fmt_int(row.get('Wins'))}</td>"
                f"<td>{_fmt_int(row.get('Losses'))}</td>"
                f"<td><span class='sp-wr {_win_rate_tone(wr)}'>{_fmt_win_rate(wr)}</span></td>"
                f"<td><span class='sp-muted'>{_html_text(row.get('Tier spread'))}</span></td>"
                f"<td><span class='sp-muted'>{_html_text(row.get('Last used date'))}</span></td>"
                "</tr>"
            )
        table_html = f"""
        <div class="sp-map-panel">
          <div class="sp-map-head">
            <div class="sp-map-title">{_html_text(map_name)}</div>
            <div class="sp-map-meta">
              <span class="sp-pill">{len(map_rows)} tactics shown</span>
              <span class="sp-pill">{_fmt_int(usage_total)} usage rounds</span>
              <span class="sp-pill">Best WR: {_html_text(best_label)}</span>
            </div>
          </div>
          <table class="sp-table">
            <thead><tr><th>Rank</th><th>Tactic</th><th>Side</th><th>Usage rounds</th><th>Matches used</th><th>Wins</th><th>Losses</th><th>Win rate</th><th>Tier spread</th><th>Last used</th></tr></thead>
            <tbody>{''.join(rows_html)}</tbody>
          </table>
        </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)


def _render_tactics_table(top_tactics: pd.DataFrame, season: int) -> None:
    _render_tactics_by_map(top_tactics, season, min_rounds=1)


def render(data: dict):
    full_matches = data.get("player_matches_full", data.get("player_matches", pd.DataFrame())).copy()
    tactics = data.get("tactics", pd.DataFrame()).copy()
    players = data.get("players", pd.DataFrame()).copy()
    achievements_df = data.get("achievements", pd.DataFrame()).copy()

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
    controls = st.container()
    with controls:
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

    selected_seasons = [int(s) for s in selected_seasons]
    if not selected_seasons:
        st.info("Select at least one season to build the comparison board.")
        return
    selected_seasons = sorted(selected_seasons, reverse=(sort_order == "Newest first"))

    section_header("All-season comparison summary", "Compact comparison across selected official seasons.")
    comparison = build_season_comparison(roster_matches, tactics, selected_seasons, min_player_matches, tactic_min_rounds)
    if comparison.empty:
        st.info("No season comparison rows are available for the current selection.")
    else:
        st.dataframe(comparison, use_container_width=True, hide_index=True)

    section_header("Season rows", "Each section uses official player match rows and official tactics rows only.")
    top_tactics = aggregate_top_tactics_by_map(_filter_seasons(tactics, selected_seasons), min_rounds=tactic_min_rounds, top_n=TACTIC_TOP_N)
    for season in selected_seasons:
        season_df = _filter_season(roster_matches, season)
        season_tactics = _filter_season(tactics, season)
        summary = _season_team_summary(season_df, season_tactics, season)
        with st.expander(_season_label(season), expanded=(int(season) == int(latest))):
            _render_season_stat_cards(summary)
            if show_players:
                section_header("Players active this season", f"Season-specific player-card payloads with a minimum of {min_player_matches} match(es).")
                payloads = build_player_card_payloads(season_df, season_tactics, players, achievements_df, min_player_matches, season)
                render_player_card_grid(payloads)
            if show_tactics:
                section_header(f"Top {TACTIC_TOP_N} most-used tactics by map", "Each map is ranked independently by usage rounds, matches used, and win rate.")
                _render_tactics_by_map(top_tactics, season, tactic_min_rounds)
