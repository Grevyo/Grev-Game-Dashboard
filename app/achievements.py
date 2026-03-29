import re

import pandas as pd

from app.image_helpers import image_data_uri_thumbnail, resolve_achievement_image

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
_CPL_OPEN_DEBUG_EMITTED = False


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


def achievements_for_player(
    achievements_df: pd.DataFrame,
    player_name: str,
    cap: int = 3,
    consumer: str = "unknown",
) -> tuple[list[dict], int]:
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
        image_resolution = resolve_achievement_image(
            row.get("achievement_link") or row.get("achievement_name"),
            achievement_name=row.get("achievement_name"),
            placement=row.get("position"),
        )
        image_path = image_resolution.get("final_path")
        image_uri = image_data_uri_thumbnail(image_path)
        global _CPL_OPEN_DEBUG_EMITTED
        if image_resolution.get("cpl_open_match") and not _CPL_OPEN_DEBUG_EMITTED:
            print(
                "[CPL_OPEN_DEBUG]",
                {
                    "raw_achievement_name": row.get("achievement_name"),
                    "raw_placement": row.get("position"),
                    "cpl_open_detected": image_resolution.get("cpl_open_match"),
                    "selected_filename": image_resolution.get("selected_filename"),
                    "resolved_filesystem_path": image_resolution.get("resolved_path"),
                    "resolved_file_exists": image_resolution.get("resolved_exists"),
                    "final_render_image_path": image_path,
                    "final_render_image_uri_present": bool(image_uri),
                    "overview_received_image_path": image_path if consumer == "overview" else None,
                    "overview_received_image_uri_present": bool(image_uri) if consumer == "overview" else None,
                    "consumer": consumer,
                    "resolver_source": image_resolution.get("source"),
                },
            )
            _CPL_OPEN_DEBUG_EMITTED = True
        items.append(
            {
                "name": str(row.get("achievement_name", "Achievement")),
                "position": str(row.get("position", "")).strip(),
                "season": str(row.get("season_name", "")).strip(),
                "season_label": normalize_season_label(row.get("season_name")),
                "tier": str(row.get("achievement_tier", "")).strip(),
                "image_uri": image_uri,
                "image_path": image_path,
                "image_render_type": "data_uri" if image_uri else "none",
            }
        )
    hidden = max(0, len(pool) - len(items))
    return items, hidden
