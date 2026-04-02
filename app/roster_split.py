import re

import pandas as pd

from app.data_loader import is_medisports_player, normalize_team_name

_EMPTY_NEW_TEAM_VALUES = {"", "-", "--", "n/a", "na", "none", "null", "unknown", "tbd"}
_NON_A_TEAM_MARKERS = (
    "academy",
    "bench",
    "benched",
    "streamer",
    "sub",
    "trial",
    "coach",
)

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


def _extract_metadata_streamer_keys(players_meta: pd.DataFrame) -> set[str]:
    if players_meta.empty:
        return set()

    if "role" not in players_meta.columns:
        return set()

    key_col = None
    for candidate in ["player_clean", "player", "name"]:
        if candidate in players_meta.columns:
            key_col = candidate
            break
    if key_col is None:
        return set()

    keep_cols = [key_col, "role"]
    if "player" in players_meta.columns and "player" not in keep_cols:
        keep_cols.append("player")
    if "name" in players_meta.columns and "name" not in keep_cols:
        keep_cols.append("name")

    meta = players_meta[keep_cols].copy()
    meta[key_col] = meta[key_col].astype(str).str.strip()
    meta["role_key"] = meta["role"].astype(str).str.strip().str.casefold()
    streamer_meta = meta[meta["role_key"] == "streamer"].copy()
    if streamer_meta.empty:
        return set()

    if "player" in streamer_meta.columns:
        streamer_meta = streamer_meta[streamer_meta["player"].map(is_medisports_player)]
    elif "name" in streamer_meta.columns:
        streamer_meta = streamer_meta[streamer_meta["name"].map(is_medisports_player)]

    return set(streamer_meta[key_col].map(_player_key).tolist())


def _extract_metadata_new_team_by_player_key(players_meta: pd.DataFrame) -> dict[str, str]:
    if players_meta.empty:
        return {}

    key_col = None
    for candidate in ["player_clean", "player", "name"]:
        if candidate in players_meta.columns:
            key_col = candidate
            break
    if key_col is None:
        return {}

    new_team_col = None
    for candidate in ["new_team", "New_team"]:
        if candidate in players_meta.columns:
            new_team_col = candidate
            break
    if new_team_col is None:
        return {}

    trimmed = players_meta[[key_col, new_team_col]].copy()
    trimmed[key_col] = trimmed[key_col].astype(str).map(_player_key)
    trimmed[new_team_col] = trimmed[new_team_col].astype(str).str.strip()
    trimmed = trimmed.dropna(subset=[key_col]).drop_duplicates(subset=[key_col], keep="first")
    return {
        str(row[key_col]): str(row[new_team_col]).strip()
        for _, row in trimmed.iterrows()
    }


def is_transferred_out_from_new_team(metadata_row: dict | pd.Series | None) -> bool:
    """Hard override for transfer classification based on metadata New_team/new_team."""
    if metadata_row is None:
        return False

    if isinstance(metadata_row, pd.Series):
        row = metadata_row.to_dict()
    else:
        row = dict(metadata_row)

    new_team_value = row.get("new_team")
    if new_team_value is None:
        new_team_value = row.get("New_team")

    raw = str(new_team_value or "").strip()
    if raw.casefold() in _EMPTY_NEW_TEAM_VALUES:
        return False

    normalized = normalize_team_name(raw)
    if not normalized:
        return False

    if any(marker in normalized for marker in _NON_A_TEAM_MARKERS):
        return False

    return True


def _resolved_season_series(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)

    primary = pd.to_numeric(df.get("resolved_season", pd.Series(index=df.index, dtype=float)), errors="coerce")
    return primary


def build_roster_bucket_debug_table(
    full_medisports_matches: pd.DataFrame,
    selected_medisports_matches: pd.DataFrame,
    bucket_by_player: dict[str, str],
) -> pd.DataFrame:
    cols = [
        "player",
        "total_rows_full_history",
        "total_rows_after_selected_season_filter",
        "seasons_seen_full_history",
        "most_recent_resolved_season",
        "assigned_bucket",
    ]
    if not bucket_by_player:
        return pd.DataFrame(columns=cols)

    full_usage = full_medisports_matches.copy()
    if not full_usage.empty:
        full_usage = full_usage.assign(
            resolved_season=_resolved_season_series(full_usage),
            player_key=full_usage.get("player", pd.Series(index=full_usage.index, dtype=object)).map(_player_key),
        )
        full_grouped = (
            full_usage.groupby("player_key", dropna=False)
            .agg(
                total_rows_full_history=("player_key", "size"),
                most_recent_resolved_season=("resolved_season", "max"),
                seasons_seen_full_history=("resolved_season", lambda s: ",".join([str(int(v)) for v in sorted(set(s.dropna().tolist()))])),
            )
            .reset_index()
        )
    else:
        full_grouped = pd.DataFrame(columns=["player_key", "total_rows_full_history", "most_recent_resolved_season", "seasons_seen_full_history"])

    selected_usage = selected_medisports_matches.copy()
    if not selected_usage.empty:
        selected_usage = selected_usage.assign(
            player_key=selected_usage.get("player", pd.Series(index=selected_usage.index, dtype=object)).map(_player_key),
        )
        selected_grouped = (
            selected_usage.groupby("player_key", dropna=False)
            .size()
            .rename("total_rows_after_selected_season_filter")
            .reset_index()
        )
    else:
        selected_grouped = pd.DataFrame(columns=["player_key", "total_rows_after_selected_season_filter"])

    table = pd.DataFrame({"player": list(bucket_by_player.keys())})
    table["player_key"] = table["player"].map(_player_key)
    table = table.merge(full_grouped, on="player_key", how="left")
    table = table.merge(selected_grouped, on="player_key", how="left")
    table["total_rows_full_history"] = table["total_rows_full_history"].fillna(0).astype(int)
    table["total_rows_after_selected_season_filter"] = table["total_rows_after_selected_season_filter"].fillna(0).astype(int)
    table["assigned_bucket"] = table["player"].map(bucket_by_player)
    table["seasons_seen_full_history"] = table["seasons_seen_full_history"].replace("", pd.NA).fillna("none")
    table = table.drop(columns=["player_key"])
    return table.sort_values("most_recent_resolved_season", ascending=False, na_position="last").reset_index(drop=True)[cols]


def get_player_last_played_season(full_medisports_matches: pd.DataFrame) -> dict[str, int]:
    """Most-recent resolved season per player across full historical data."""
    if full_medisports_matches.empty or "player" not in full_medisports_matches.columns:
        return {}

    usage = full_medisports_matches[["player"]].copy()
    usage["resolved_season"] = _resolved_season_series(full_medisports_matches)
    usage = usage.dropna(subset=["resolved_season"])
    if usage.empty:
        return {}

    usage = usage.assign(player_key=usage["player"].map(_player_key))
    grouped = usage.groupby("player_key", dropna=False)["resolved_season"].max()
    return {k: int(v) for k, v in grouped.items() if pd.notna(v)}


def can_classify_transferred_safely(full_medisports_matches: pd.DataFrame, minimum_span: int = 3) -> bool:
    """Require enough season history before allowing transferred classification."""
    seasons = _resolved_season_series(full_medisports_matches).dropna()
    if seasons.empty:
        return False

    min_season = int(seasons.min())
    max_season = int(seasons.max())
    return (max_season - min_season) >= minimum_span


def classify_roster_bucket(
    *,
    player: str,
    in_metadata: bool,
    last_played_season: int | None,
    current_season: int | None,
    is_transferred_out: bool,
    is_streamer: bool,
    can_classify_transferred: bool,
    appearance_share: float,
    active_threshold: float,
) -> str:
    """Centralized roster bucket rules.

    Order:
    - transferred (hard override from metadata New_team/new_team)
    - streamer (explicit metadata role)
    - streamer (metadata member with no game data)
    - transferred (only if safety guard passes and last_played <= current - 3)
    - active / benched_academy by current-context appearance share
    """
    _ = player  # explicit argument for readability in call-sites/debugging

    if is_transferred_out:
        return "transferred"

    if is_streamer:
        return "streamer"

    if in_metadata and last_played_season is None:
        return "streamer"

    if (
        can_classify_transferred
        and current_season is not None
        and last_played_season is not None
        and int(last_played_season) <= int(current_season) - 3
    ):
        return "transferred"

    return "active" if appearance_share > active_threshold else "benched_academy"


def split_roster_active_benched_streamer_transferred(
    summary: pd.DataFrame,
    player_match_counts: pd.DataFrame,
    selected_medisports_matches: pd.DataFrame,
    full_medisports_matches: pd.DataFrame,
    players_meta: pd.DataFrame,
    active_threshold: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    streamer_keys = _extract_metadata_streamer_keys(players_meta)
    new_team_by_key = _extract_metadata_new_team_by_player_key(players_meta)

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
        return empty.copy(), empty.copy(), empty.copy(), empty.copy(), pd.DataFrame(columns=["player", "total_rows_full_history", "total_rows_after_selected_season_filter", "seasons_seen_full_history", "most_recent_resolved_season", "assigned_bucket"])

    season_series = usage.get("resolved_season", pd.Series(dtype=float)).dropna()
    latest_dataset_season = int(season_series.max()) if not season_series.empty else None
    can_transfer_safely = can_classify_transferred_safely(full_medisports_matches, minimum_span=3)
    last_season_by_key = get_player_last_played_season(full_medisports_matches)

    classified: dict[str, str] = {}
    meta_by_key = {_player_key(name): name for name in meta_players}
    counts_by_key = counts.assign(player_key=counts["player"].map(_player_key)) if not counts.empty else counts.copy()
    for player in all_known_players:
        # 1) Exclude non-Medisports players entirely.
        if not is_medisports_player(player):
            continue

        player_key = _player_key(player)
        in_metadata = player_key in meta_by_key

        metadata_row = {"new_team": new_team_by_key.get(player_key)}
        is_transferred_out = is_transferred_out_from_new_team(metadata_row)

        # 2/3/4) Centralized classification; transferred includes metadata override + season-history rule.
        appearance = counts_by_key.loc[counts_by_key["player_key"] == player_key, "appearance_share"] if not counts_by_key.empty else pd.Series(dtype=float)
        appearance_share = float(appearance.iloc[0]) if not appearance.empty else 0.0
        classified[player] = classify_roster_bucket(
            player=player,
            in_metadata=in_metadata,
            last_played_season=last_season_by_key.get(player_key),
            current_season=latest_dataset_season,
            is_transferred_out=is_transferred_out,
            is_streamer=(player_key in streamer_keys),
            can_classify_transferred=can_transfer_safely,
            appearance_share=appearance_share,
            active_threshold=active_threshold,
        )

    active_players = {name for name, bucket in classified.items() if bucket == "active"}
    benched_players = {name for name, bucket in classified.items() if bucket == "benched_academy"}
    streamer_players = {name for name, bucket in classified.items() if bucket == "streamer"}
    transferred_players = {name for name, bucket in classified.items() if bucket == "transferred"}

    merged = merged.copy()
    merged["player_key"] = merged.get("player", pd.Series(index=merged.index, dtype=object)).map(_player_key)
    transferred_keys = {_player_key(name) for name in transferred_players}
    active_keys = {_player_key(name) for name in active_players}
    benched_keys = {_player_key(name) for name in benched_players}
    streamer_keys_bucket = {_player_key(name) for name in streamer_players}
    merged["is_transferred_out"] = merged["player_key"].isin(transferred_keys)

    # Priority enforcement: transferred players are excluded from lower-priority buckets.
    active_summary = merged[merged["player_key"].isin(active_keys) & ~merged["is_transferred_out"]].copy()
    benched_summary = merged[merged["player_key"].isin(benched_keys) & ~merged["is_transferred_out"]].copy()
    streamer_summary = merged[merged["player_key"].isin(streamer_keys_bucket) & ~merged["is_transferred_out"]].copy()
    transferred_summary = merged[merged["is_transferred_out"]].copy()

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

    for df in [active_summary, benched_summary, streamer_summary, transferred_summary]:
        if "player_key" in df.columns:
            df.drop(columns=["player_key"], inplace=True)

    streamer_summary = streamer_summary.sort_values(["appearance_share", "grevscore"], ascending=[True, False], na_position="last")
    transferred_summary = transferred_summary.sort_values(["appearance_share", "grevscore"], ascending=[True, False], na_position="last")
    bucket_debug = build_roster_bucket_debug_table(full_medisports_matches, selected_medisports_matches, classified)
    return active_summary, benched_summary, streamer_summary, transferred_summary, bucket_debug
