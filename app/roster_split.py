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


def split_roster_active_benched_streamer_transferred(
    summary: pd.DataFrame,
    player_match_counts: pd.DataFrame,
    full_medisports_matches: pd.DataFrame,
    players_meta: pd.DataFrame,
    active_threshold: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    counts = (
        player_match_counts[["player", "appearance_share"]].copy()
        if not player_match_counts.empty and {"player", "appearance_share"}.issubset(player_match_counts.columns)
        else pd.DataFrame(columns=["player", "appearance_share"])
    )

    merged = summary.merge(counts, on="player", how="left") if not summary.empty else summary.copy()
    if "appearance_share" not in merged.columns:
        merged["appearance_share"] = 0.0
    merged["appearance_share"] = merged["appearance_share"].fillna(0.0)

    roster_names = set(merged.get("player", pd.Series(dtype=object)).dropna().astype(str).tolist())
    meta_players = _extract_metadata_players(players_meta)
    all_known_players = sorted(roster_names.union(meta_players), key=str.casefold)

    if not all_known_players:
        empty = pd.DataFrame(columns=merged.columns)
        return empty.copy(), empty.copy(), empty.copy(), empty.copy()

    season_series = pd.to_numeric(full_medisports_matches.get("season", pd.Series(dtype=float)), errors="coerce")
    latest_dataset_season = int(season_series.max()) if not season_series.dropna().empty else None

    usage = full_medisports_matches[["player", "match_id", "season"]].copy() if not full_medisports_matches.empty else pd.DataFrame(columns=["player", "match_id", "season"])

    classified: dict[str, str] = {}
    for player in all_known_players:
        player_usage = usage[usage["player"].astype(str) == str(player)] if not usage.empty else pd.DataFrame()
        has_any_game_data = not player_usage.empty
        in_metadata = player in meta_players

        # 1) Streamer: exists in roster metadata, but has no game data at all.
        if in_metadata and not has_any_game_data:
            classified[player] = "streamer"
            continue

        # 2) Transferred: has historical data, but absent for more than 2 seasons.
        transferred = False
        if has_any_game_data and latest_dataset_season is not None and "season" in player_usage.columns:
            p_seasons = pd.to_numeric(player_usage["season"], errors="coerce").dropna()
            if not p_seasons.empty:
                player_latest = int(p_seasons.max())
                transferred = (latest_dataset_season - player_latest) >= 3

        if transferred:
            classified[player] = "transferred"
            continue

        # 3/4) Competitive buckets apply only to players with game data.
        appearance = counts.loc[counts["player"].astype(str) == str(player), "appearance_share"]
        appearance_share = float(appearance.iloc[0]) if not appearance.empty else 0.0
        classified[player] = "active" if appearance_share > active_threshold else "benched_academy"

    active_players = {name for name, bucket in classified.items() if bucket == "active"}
    benched_players = {name for name, bucket in classified.items() if bucket == "benched_academy"}
    streamer_players = {name for name, bucket in classified.items() if bucket == "streamer"}
    transferred_players = {name for name, bucket in classified.items() if bucket == "transferred"}

    active_summary = merged[merged["player"].isin(active_players)].copy()
    benched_summary = merged[merged["player"].isin(benched_players)].copy()
    streamer_summary = merged[merged["player"].isin(streamer_players)].copy()
    transferred_summary = merged[merged["player"].isin(transferred_players)].copy()

    missing_from_summary = [p for p in all_known_players if p in (streamer_players | transferred_players) and p not in set(merged.get("player", pd.Series(dtype=object)).astype(str))]
    if missing_from_summary:
        filler = pd.DataFrame({"player": missing_from_summary})
        for col in merged.columns:
            if col not in filler.columns:
                filler[col] = 0.0 if col in {"matches", "grevscore", "rating", "impact", "form", "kpd", "kpr", "accuracy_pct", "hs_pct", "appearance_share"} else ""
        streamer_missing = filler[filler["player"].isin(streamer_players)]
        transferred_missing = filler[filler["player"].isin(transferred_players)]
        if not streamer_missing.empty:
            streamer_summary = pd.concat([streamer_summary, streamer_missing[merged.columns]], ignore_index=True)
        if not transferred_missing.empty:
            transferred_summary = pd.concat([transferred_summary, transferred_missing[merged.columns]], ignore_index=True)

    streamer_summary = streamer_summary.sort_values(["appearance_share", "grevscore"], ascending=[True, False], na_position="last")
    transferred_summary = transferred_summary.sort_values(["appearance_share", "grevscore"], ascending=[True, False], na_position="last")
    return active_summary, benched_summary, streamer_summary, transferred_summary
