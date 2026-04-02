import pandas as pd

from app.data_loader import is_medisports_player, normalize_player_key

_EMPTY_NEW_TEAM_VALUES = {"", "-", "--", "n/a", "na", "none", "null", "unknown", "tbd", "nan"}


def normalize_new_team_value(value: object) -> str:
    """Return a cleaned New_team value; empty string means not transferred."""
    raw = "" if value is None else str(value).strip()
    return "" if raw.casefold() in _EMPTY_NEW_TEAM_VALUES else raw


def _player_key(name: str) -> str:
    return normalize_player_key(name)


def _metadata_name_column(players_meta: pd.DataFrame) -> str | None:
    for candidate in ["player_clean", "player", "name"]:
        if candidate in players_meta.columns:
            return candidate
    return None


def _extract_metadata_players(players_meta: pd.DataFrame) -> list[str]:
    if players_meta.empty:
        return []
    name_col = _metadata_name_column(players_meta)
    if not name_col:
        return []
    names = players_meta[name_col].dropna().astype(str).str.strip()
    medisports_names = names[names.map(is_medisports_player)]
    return sorted(set(medisports_names.tolist()), key=str.casefold)


def _extract_metadata_raw_new_team_by_player_key(players_meta: pd.DataFrame) -> dict[str, str]:
    if players_meta.empty:
        return {}

    name_col = _metadata_name_column(players_meta)
    if not name_col:
        return {}

    new_team_col = None
    for candidate in ["new_team", "New_team"]:
        if candidate in players_meta.columns:
            new_team_col = candidate
            break
    if not new_team_col:
        return {}

    trimmed = players_meta[[name_col, new_team_col]].copy()
    trimmed[name_col] = trimmed[name_col].astype(str).map(_player_key)
    trimmed = trimmed.dropna(subset=[name_col]).drop_duplicates(subset=[name_col], keep="first")

    return {
        str(row[name_col]): str(row[new_team_col]).strip()
        for _, row in trimmed.iterrows()
    }


def _extract_metadata_streamer_keys(players_meta: pd.DataFrame) -> set[str]:
    if players_meta.empty:
        return set()

    name_col = _metadata_name_column(players_meta)
    if not name_col:
        return set()

    meta = players_meta.copy()
    meta[name_col] = meta[name_col].astype(str).str.strip()

    streamer_mask = pd.Series([False] * len(meta), index=meta.index)

    if "role" in meta.columns:
        streamer_mask = streamer_mask | meta["role"].astype(str).str.strip().str.casefold().eq("streamer")

    ability_cols = [c for c in meta.columns if c.lower().startswith("ability")]
    if ability_cols:
        ability_tokens = meta[ability_cols].astype(str).apply(lambda s: s.str.strip().str.casefold())
        ability_match = ability_tokens.apply(lambda row: any("streamer" in token for token in row if token and token != "-"), axis=1)
        streamer_mask = streamer_mask | ability_match

    if not streamer_mask.any():
        return set()

    streamer_meta = meta[streamer_mask].copy()
    return set(streamer_meta[name_col].map(_player_key).tolist())


def _build_play_count_by_player_key(
    player_match_counts: pd.DataFrame,
    selected_medisports_matches: pd.DataFrame,
) -> dict[str, int]:
    if not player_match_counts.empty and "player" in player_match_counts.columns:
        counts_df = player_match_counts[["player"]].copy()
        count_col = "matches_played" if "matches_played" in player_match_counts.columns else "match_count" if "match_count" in player_match_counts.columns else None
        if count_col is None:
            count_col = "appearance_share" if "appearance_share" in player_match_counts.columns else None
        if count_col:
            counts_df["play_count"] = pd.to_numeric(player_match_counts[count_col], errors="coerce").fillna(0)
            grouped = counts_df.groupby("player", dropna=False)["play_count"].max().reset_index()
            grouped["play_count"] = grouped["play_count"].round().astype(int)
            return { _player_key(row["player"]): int(row["play_count"]) for _, row in grouped.iterrows() }

    if selected_medisports_matches.empty or "player" not in selected_medisports_matches.columns:
        return {}

    usage = selected_medisports_matches.copy()
    if "match_id" in usage.columns:
        grouped = usage.groupby("player", dropna=False)["match_id"].nunique()
    else:
        grouped = usage.groupby("player", dropna=False).size()

    return { _player_key(player): int(count) for player, count in grouped.items() }


def _top_active_five(play_count_by_key: dict[str, int]) -> set[str]:
    ranked = sorted(play_count_by_key.items(), key=lambda item: (-int(item[1]), item[0]))
    return {key for key, _ in ranked[:5]}


def build_roster_bucket_debug_table(debug_rows: list[dict]) -> pd.DataFrame:
    columns = [
        "player",
        "play_count",
        "active_top_5",
        "raw_new_team",
        "normalized_new_team",
        "is_streamer",
        "assigned_bucket",
    ]
    if not debug_rows:
        return pd.DataFrame(columns=columns)
    table = pd.DataFrame(debug_rows)
    return table[columns].sort_values(["assigned_bucket", "play_count", "player"], ascending=[True, False, True]).reset_index(drop=True)


def split_roster_active_benched_streamer_transferred(
    summary: pd.DataFrame,
    player_match_counts: pd.DataFrame,
    selected_medisports_matches: pd.DataFrame,
    full_medisports_matches: pd.DataFrame,
    players_meta: pd.DataFrame,
    active_threshold: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _ = active_threshold

    counts = (
        player_match_counts[["player", "appearance_share"]].copy()
        if not player_match_counts.empty and {"player", "appearance_share"}.issubset(player_match_counts.columns)
        else pd.DataFrame(columns=["player", "appearance_share"])
    )

    merged = summary.merge(counts, on="player", how="left") if not summary.empty else summary.copy()
    if "appearance_share" not in merged.columns:
        merged["appearance_share"] = 0.0
    merged["appearance_share"] = pd.to_numeric(merged["appearance_share"], errors="coerce").fillna(0.0)

    roster_names = set(merged.get("player", pd.Series(dtype=object)).dropna().astype(str).tolist())
    selected_usage_names = set(selected_medisports_matches.get("player", pd.Series(dtype=object)).dropna().astype(str).tolist()) if not selected_medisports_matches.empty else set()
    full_usage_names = set(full_medisports_matches.get("player", pd.Series(dtype=object)).dropna().astype(str).tolist()) if not full_medisports_matches.empty else set()
    meta_players = set(_extract_metadata_players(players_meta))

    all_known_players = sorted(
        {
            p for p in roster_names.union(selected_usage_names).union(full_usage_names).union(meta_players)
            if is_medisports_player(p)
        },
        key=str.casefold,
    )

    if not all_known_players:
        empty = pd.DataFrame(columns=merged.columns)
        return empty.copy(), empty.copy(), empty.copy(), empty.copy(), build_roster_bucket_debug_table([])

    canonical_name_by_key = {_player_key(name): name for name in all_known_players}

    play_count_by_key = _build_play_count_by_player_key(player_match_counts, selected_medisports_matches)
    active_top_five_keys = _top_active_five(play_count_by_key)

    raw_new_team_by_key = _extract_metadata_raw_new_team_by_player_key(players_meta)
    normalized_new_team_by_key = {k: normalize_new_team_value(v) for k, v in raw_new_team_by_key.items()}
    streamer_keys = _extract_metadata_streamer_keys(players_meta)

    assigned_bucket_by_key: dict[str, str] = {}
    debug_rows: list[dict] = []

    for player_name in all_known_players:
        player_key = _player_key(player_name)
        play_count = int(play_count_by_key.get(player_key, 0))
        raw_new_team = raw_new_team_by_key.get(player_key, "")
        normalized_new_team = normalized_new_team_by_key.get(player_key, "")
        is_active_top_five = player_key in active_top_five_keys
        is_streamer = player_key in streamer_keys

        if is_active_top_five:
            bucket = "active"
        elif normalized_new_team:
            bucket = "transferred"
        elif is_streamer:
            bucket = "streamer"
        else:
            bucket = "benched_academy"

        assigned_bucket_by_key[player_key] = bucket
        debug_rows.append(
            {
                "player": canonical_name_by_key[player_key],
                "play_count": play_count,
                "active_top_5": "yes" if is_active_top_five else "no",
                "raw_new_team": raw_new_team,
                "normalized_new_team": normalized_new_team,
                "is_streamer": "yes" if is_streamer else "no",
                "assigned_bucket": bucket,
            }
        )

    merged = merged.copy()
    merged["player_key"] = merged.get("player", pd.Series(index=merged.index, dtype=object)).map(_player_key)

    missing_players = [p for p in all_known_players if _player_key(p) not in set(merged.get("player_key", pd.Series(dtype=object)).dropna().astype(str).tolist())]
    if missing_players:
        filler = pd.DataFrame({"player": missing_players})
        for col in merged.columns:
            if col not in filler.columns:
                filler[col] = 0.0 if col in {"matches", "grevscore", "rating", "impact", "form", "kpd", "kpr", "accuracy_pct", "hs_pct", "appearance_share"} else ""
        filler["player_key"] = filler["player"].map(_player_key)
        merged = pd.concat([merged, filler[merged.columns]], ignore_index=True)

    merged["assigned_bucket"] = merged["player_key"].map(assigned_bucket_by_key).fillna("benched_academy")

    active_summary = merged[merged["assigned_bucket"] == "active"].copy()
    transferred_summary = merged[merged["assigned_bucket"] == "transferred"].copy()
    streamer_summary = merged[merged["assigned_bucket"] == "streamer"].copy()
    benched_summary = merged[merged["assigned_bucket"] == "benched_academy"].copy()

    for df in [active_summary, benched_summary, streamer_summary, transferred_summary]:
        if "player_key" in df.columns:
            df.drop(columns=["player_key"], inplace=True)

    active_summary = active_summary.sort_values(["appearance_share", "grevscore"], ascending=[False, False], na_position="last")
    transferred_summary = transferred_summary.sort_values(["appearance_share", "grevscore"], ascending=[False, False], na_position="last")
    streamer_summary = streamer_summary.sort_values(["appearance_share", "grevscore"], ascending=[False, False], na_position="last")
    benched_summary = benched_summary.sort_values(["appearance_share", "grevscore"], ascending=[False, False], na_position="last")

    bucket_debug = build_roster_bucket_debug_table(debug_rows)
    return active_summary, benched_summary, streamer_summary, transferred_summary, bucket_debug
