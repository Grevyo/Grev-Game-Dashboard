import re

import pandas as pd

from app.image_helpers import find_achievement_image, image_data_uri

POSITION_PRIORITY = {
    "1st": 100,
    "2nd": 80,
    "3rd": 65,
    "4th": 50,
    "5th": 45,
    "6th": 40,
    "7th": 35,
    "8th": 30,
}
TIER_PRIORITY = {"S": 90, "A": 75, "B": 60, "C": 45, "D": 30}


def _player_key(player_name: str | None) -> str:
    return re.sub(r"^ⓜ\s*\|\s*", "", str(player_name or ""), flags=re.IGNORECASE).strip().casefold()


def normalize_season_label(season_value: str | int | float | None) -> str:
    text = str(season_value or "").strip()
    if not text:
        return ""
    match = re.search(r"(\d+)", text)
    if match:
        return f"Season {int(match.group(1))}"
    return text if text.lower().startswith("season ") else f"Season {text}"


def achievements_for_player(achievements_df: pd.DataFrame, player_name: str, cap: int = 3) -> tuple[list[dict], int]:
    if achievements_df.empty:
        return [], 0

    key = _player_key(player_name)
    pool = achievements_df.copy()
    if "player_clean" in pool.columns:
        mask = pool["player_clean"].astype(str).str.strip().str.casefold() == key
    else:
        mask = pool.get("player", pd.Series(index=pool.index, dtype=str)).astype(str).map(_player_key) == key
    pool = pool[mask]
    if pool.empty:
        return [], 0

    season_num = pd.to_numeric(pool.get("season_name"), errors="coerce").fillna(0)
    pos_priority = pool.get("position", "").astype(str).str.strip().map(POSITION_PRIORITY).fillna(10)
    tier_priority = pool.get("achievement_tier", "").astype(str).str.upper().map(TIER_PRIORITY).fillna(20)

    pool = pool.assign(_season=season_num, _pos=pos_priority, _tier=tier_priority)
    pool = pool.sort_values(["_pos", "_tier", "_season"], ascending=[False, False, False])

    top = pool.head(cap)
    items = []
    for _, row in top.iterrows():
        image_path = find_achievement_image(
            row.get("achievement_link") or row.get("achievement_name"),
            achievement_name=row.get("achievement_name"),
            placement=row.get("position"),
        )
        items.append(
            {
                "name": str(row.get("achievement_name", "Achievement")),
                "position": str(row.get("position", "")).strip(),
                "season": str(row.get("season_name", "")).strip(),
                "season_label": normalize_season_label(row.get("season_name")),
                "tier": str(row.get("achievement_tier", "")).strip(),
                "image_uri": image_data_uri(image_path),
            }
        )
    hidden = max(0, len(pool) - len(items))
    return items, hidden
