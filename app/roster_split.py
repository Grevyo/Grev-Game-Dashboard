import re

import pandas as pd


def _player_key(name: str) -> str:
    text = str(name or "").strip()
    text = re.sub(r"^ⓜ\s*\|\s*", "", text, flags=re.IGNORECASE)
    return text.casefold()


def _extract_metadata_players(players_meta: pd.DataFrame) -> list[str]:
    if players_meta.empty:
        return []

    name_col = None
    for candidate in ["player", "name", "player_clean"]:
        if candidate in players_meta.columns:
            name_col = candidate
            break
    if name_col is None:
        return []

    meta_names = players_meta[name_col].dropna().astype(str).str.strip()
    medisports_meta = meta_names[meta_names.str.contains("ⓜ", regex=False)]
    return sorted(set(medisports_meta.tolist()), key=str.casefold)


def split_roster_active_benched_transferred(
    summary: pd.DataFrame,
    player_match_counts: pd.DataFrame,
    full_medisports_matches: pd.DataFrame,
    players_meta: pd.DataFrame,
    active_threshold: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    counts = (
        player_match_counts[["player", "appearance_share"]].copy()
        if not player_match_counts.empty and {"player", "appearance_share"}.issubset(player_match_counts.columns)
        else pd.DataFrame(columns=["player", "appearance_share"])
    )

    merged = summary.merge(counts, on="player", how="left") if not summary.empty else summary.copy()
    if "appearance_share" not in merged.columns:
        merged["appearance_share"] = 0.0
    merged["appearance_share"] = merged["appearance_share"].fillna(0.0)

    active_summary = merged[merged["appearance_share"] > active_threshold].copy()
    benched_summary = merged[merged["appearance_share"] <= active_threshold].copy()

    roster_names = set(merged.get("player", pd.Series(dtype=object)).dropna().astype(str).tolist())
    meta_players = _extract_metadata_players(players_meta)
    all_known_players = sorted(roster_names.union(meta_players), key=str.casefold)

    if not all_known_players:
        return active_summary, benched_summary, pd.DataFrame(columns=merged.columns)

    season_series = pd.to_numeric(full_medisports_matches.get("season", pd.Series(dtype=float)), errors="coerce")
    latest_dataset_season = int(season_series.max()) if not season_series.dropna().empty else None

    usage = full_medisports_matches[["player", "match_id", "season"]].copy() if not full_medisports_matches.empty else pd.DataFrame(columns=["player", "match_id", "season"])

    transferred_players: list[str] = []
    for player in all_known_players:
        player_usage = usage[usage["player"].astype(str) == str(player)] if not usage.empty else pd.DataFrame()
        has_any_game_data = not player_usage.empty
        has_current_match_usage = bool(player_usage.get("match_id", pd.Series(dtype=float)).nunique() > 0) if has_any_game_data else False

        absent_two_plus_seasons = False
        if has_any_game_data and latest_dataset_season is not None and "season" in player_usage.columns:
            p_seasons = pd.to_numeric(player_usage["season"], errors="coerce").dropna()
            if not p_seasons.empty:
                player_latest = int(p_seasons.max())
                absent_two_plus_seasons = (latest_dataset_season - player_latest) >= 2

        appears_only_in_metadata = (player in meta_players) and (not has_any_game_data)

        if (not has_any_game_data) or (not has_current_match_usage) or absent_two_plus_seasons or appears_only_in_metadata:
            transferred_players.append(player)

    transferred_set = set(transferred_players)
    if transferred_set:
        active_summary = active_summary[~active_summary["player"].isin(transferred_set)].copy()
        benched_summary = benched_summary[~benched_summary["player"].isin(transferred_set)].copy()

    transferred_summary = merged[merged["player"].isin(transferred_set)].copy()

    missing_from_summary = [p for p in all_known_players if p in transferred_set and p not in set(transferred_summary.get("player", pd.Series(dtype=object)).astype(str))]
    if missing_from_summary:
        filler = pd.DataFrame({"player": missing_from_summary})
        for col in merged.columns:
            if col not in filler.columns:
                filler[col] = 0.0 if col in {"matches", "grevscore", "rating", "impact", "form", "kpd", "kpr", "accuracy_pct", "hs_pct", "appearance_share"} else ""
        transferred_summary = pd.concat([transferred_summary, filler[merged.columns]], ignore_index=True)

    transferred_summary = transferred_summary.sort_values(["appearance_share", "grevscore"], ascending=[True, False], na_position="last")
    return active_summary, benched_summary, transferred_summary
