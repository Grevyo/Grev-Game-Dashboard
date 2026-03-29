import re

import pandas as pd

from app.data_loader import is_medisports_player


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


def _resolved_season_series(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)

    primary = pd.to_numeric(df.get("season", pd.Series(index=df.index, dtype=float)), errors="coerce")
    fallback = pd.to_numeric(df.get("parsed_season_number", pd.Series(index=df.index, dtype=float)), errors="coerce")
    return primary.fillna(fallback)


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

    usage = (
        full_medisports_matches[["player", "match_id"]].copy()
        if not full_medisports_matches.empty and {"player", "match_id"}.issubset(full_medisports_matches.columns)
        else pd.DataFrame(columns=["player", "match_id"])
    )
    usage["resolved_season"] = _resolved_season_series(full_medisports_matches) if not usage.empty else pd.Series(dtype=float)

    usage_players = set(usage.get("player", pd.Series(dtype=object)).dropna().astype(str).tolist())
    medisports_roster_names = {
        p for p in roster_names.union(meta_players).union(usage_players)
        if is_medisports_player(p)
    }
    all_known_players = sorted(medisports_roster_names, key=str.casefold)

    if not all_known_players:
        empty = pd.DataFrame(columns=merged.columns)
        return empty.copy(), empty.copy(), empty.copy(), empty.copy()

    season_series = usage.get("resolved_season", pd.Series(dtype=float))
    latest_dataset_season = int(season_series.max()) if not season_series.dropna().empty else None

    usage_by_key = usage.assign(player_key=usage["player"].map(_player_key)) if not usage.empty else usage.copy()
    last_season_by_key = (
        usage_by_key.groupby("player_key", dropna=False)["resolved_season"].max().to_dict()
        if not usage_by_key.empty
        else {}
    )

    classified: dict[str, str] = {}
    meta_by_key = {_player_key(name): name for name in meta_players}
    counts_by_key = counts.assign(player_key=counts["player"].map(_player_key)) if not counts.empty else counts.copy()
    for player in all_known_players:
        # 1) Exclude non-Medisports players entirely.
        if not is_medisports_player(player):
            continue

        player_key = _player_key(player)
        has_any_game_data = player_key in last_season_by_key
        in_metadata = player_key in meta_by_key

        # 2) Streamer: exists in roster metadata, but has no game data at all.
        if in_metadata and not has_any_game_data:
            classified[player] = "streamer"
            continue

        # 3/4) Transferred: has historical data and last played season <= current_season - 3.
        transferred = False
        if has_any_game_data and latest_dataset_season is not None:
            player_latest = pd.to_numeric(last_season_by_key.get(player_key), errors="coerce")
            if pd.notna(player_latest):
                transferred = int(player_latest) <= int(latest_dataset_season) - 3

        if transferred:
            classified[player] = "transferred"
            continue

        # 5) Competitive buckets are split by current-context appearance share.
        appearance = counts_by_key.loc[counts_by_key["player_key"] == player_key, "appearance_share"] if not counts_by_key.empty else pd.Series(dtype=float)
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
