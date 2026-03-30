import pandas as pd


def resolve_match_result(match_row: pd.Series, tactics_context: pd.DataFrame) -> str | None:
    direct_result_candidates = ["result", "match_result", "outcome", "wl"]
    for col in direct_result_candidates:
        if col not in match_row.index:
            continue
        value = str(match_row.get(col, "") or "").strip().casefold()
        if value in {"w", "win", "won", "victory"}:
            return "Win"
        if value in {"l", "loss", "lost", "defeat"}:
            return "Loss"

    if "win" in match_row.index:
        win_value = match_row.get("win")
        if isinstance(win_value, bool):
            return "Win" if win_value else "Loss"

    if tactics_context.empty or "match_id" not in tactics_context.columns:
        return None

    match_id = str(match_row.get("match_id", "") or "").strip()
    if not match_id:
        return None

    tactic_rows = tactics_context[tactics_context["match_id"].astype(str) == match_id]
    if tactic_rows.empty or "wins" not in tactic_rows.columns or "losses" not in tactic_rows.columns:
        return None

    wins = pd.to_numeric(tactic_rows["wins"], errors="coerce").sum(min_count=1)
    losses = pd.to_numeric(tactic_rows["losses"], errors="coerce").sum(min_count=1)
    if pd.isna(wins) or pd.isna(losses) or wins == losses:
        return None
    return "Win" if wins > losses else "Loss"


def _iter_valid_player_matches(df_context: pd.DataFrame, tactics_context: pd.DataFrame, player_name: str):
    required_cols = {"player", "date", "opponent_team", "kpd", "grevscore"}
    if df_context.empty or any(col not in df_context.columns for col in required_cols):
        return

    subset = df_context[df_context["player"].astype(str) == str(player_name)].copy()
    if subset.empty:
        return

    sort_cols = [col for col in ["date", "time", "match_id"] if col in subset.columns]
    if sort_cols:
        subset = subset.sort_values(sort_cols, ascending=[False] * len(sort_cols), kind="mergesort")

    for _, row in subset.iterrows():
        opponent = str(row.get("opponent_team", "") or "").strip()
        kpd = pd.to_numeric(row.get("kpd"), errors="coerce")
        grevscore = pd.to_numeric(row.get("grevscore"), errors="coerce")
        result = resolve_match_result(row, tactics_context)
        if not (opponent and result and pd.notna(kpd) and pd.notna(grevscore)):
            continue

        date_played = pd.to_datetime(row.get("date"), errors="coerce")
        tournament = str(
            row.get("competition")
            or row.get("raw_competition_name")
            or row.get("tournament")
            or ""
        ).strip()
        yield {
            "date": date_played,
            "date_played": date_played.strftime("%b %d, %Y") if pd.notna(date_played) else "",
            "opponent_team": opponent,
            "result": result,
            "kpd": float(kpd),
            "grevscore": float(grevscore),
            "tournament": tournament,
        }


def build_last_match_summary(df_context: pd.DataFrame, tactics_context: pd.DataFrame, player_name: str) -> dict | None:
    for item in _iter_valid_player_matches(df_context, tactics_context, player_name):
        return item
    return None


def build_best_match_summary(df_context: pd.DataFrame, tactics_context: pd.DataFrame, player_name: str) -> dict | None:
    matches = list(_iter_valid_player_matches(df_context, tactics_context, player_name))
    if not matches:
        return None
    return max(matches, key=lambda item: (item["grevscore"], item["date"] if pd.notna(item["date"]) else pd.Timestamp.min))


def build_last_n_matches(df_context: pd.DataFrame, tactics_context: pd.DataFrame, player_name: str, n: int = 5) -> list[dict]:
    if n <= 0:
        return []
    return list(_iter_valid_player_matches(df_context, tactics_context, player_name))[:n]


def build_best_n_matches(df_context: pd.DataFrame, tactics_context: pd.DataFrame, player_name: str, n: int = 5) -> list[dict]:
    if n <= 0:
        return []
    matches = list(_iter_valid_player_matches(df_context, tactics_context, player_name))
    matches.sort(
        key=lambda item: (
            item["grevscore"],
            item["date"] if pd.notna(item["date"]) else pd.Timestamp.min,
        ),
        reverse=True,
    )
    return matches[:n]
