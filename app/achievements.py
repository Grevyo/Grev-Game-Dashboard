import re
from pathlib import Path

import pandas as pd

from app.image_helpers import image_data_uri, image_data_uri_thumbnail, resolve_achievement_image

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


def _is_present_text(value) -> bool:
    text = str(value or "").strip()
    return bool(text and text.casefold() not in {"nan", "none", "null"})


def _resolve_achievement_image_for_overview(row: pd.Series) -> tuple[str | None, str | None]:
    """Resolve achievement image with explicit priority for parsed achievement_link.

    Priority order:
    1) Usable non-empty achievement_link from row
    2) Existing resolver fallback logic
    3) Placeholder (no image)
    """
    link_value = str(row.get("achievement_link", "") or "").strip()
    if _is_present_text(link_value):
        if link_value.startswith("data:image/"):
            return link_value, None
        if re.match(r"^https?://", link_value, flags=re.IGNORECASE):
            return link_value, None

        link_path = Path(link_value).expanduser()
        if link_path.exists() and link_path.is_file():
            image_uri = image_data_uri_thumbnail(str(link_path))
            if image_uri:
                return image_uri, str(link_path)

    image_resolution = resolve_achievement_image(
        link_value or row.get("achievement_name"),
        achievement_name=row.get("achievement_name"),
        placement=row.get("position"),
    )
    image_path = image_resolution.get("final_path")
    image_uri = image_data_uri_thumbnail(image_path)
    return image_uri, image_path


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
    cap: int | None = None,
    consumer: str = "unknown",
) -> tuple[list[dict], int]:
    if achievements_df.empty:
        return [], 0

    key = _player_key(player_name)
    pool = achievements_df.copy()
    raw_player_mask = pool.get("player", pd.Series(index=pool.index, dtype=str)).astype(str).map(_player_key) == key
    if "player_clean" in pool.columns:
        # Use both normalized raw player names and player_clean to avoid dropping
        # rows when player_clean is missing/corrupted for a subset of entries.
        clean_mask = pool["player_clean"].astype(str).str.strip().str.casefold() == key
        mask = clean_mask | raw_player_mask
    else:
        mask = raw_player_mask
    pool = pool[mask]
    if pool.empty:
        return [], 0

    season_num = pd.to_numeric(pool.get("season_name"), errors="coerce").fillna(0)
    pos_priority = pool.get("position", "").astype(str).str.strip().map(POSITION_PRIORITY).fillna(10)
    tier_priority = pool.get("achievement_tier", "").astype(str).str.upper().map(TIER_PRIORITY).fillna(20)

    pool = pool.assign(_season=season_num, _pos=pos_priority, _tier=tier_priority)
    pool = pool.sort_values(["_pos", "_tier", "_season"], ascending=[False, False, False])

    if cap is None:
        top = pool
    else:
        top = pool.head(cap)
    items = []
    for _, row in top.iterrows():
        image_uri, image_path = _resolve_achievement_image_for_overview(row)
        if not image_uri and image_path and Path(str(image_path)).exists():
            # Hard fallback: if local file exists but thumbnail encoding failed, still force a data URI.
            image_uri = image_data_uri(str(image_path))
        items.append(
            {
                "name": str(row.get("achievement_name", "Achievement")),
                "position": str(row.get("position", "")).strip(),
                "season": str(row.get("season_name", "")).strip(),
                "season_label": normalize_season_label(row.get("season_name")),
                "tier": str(row.get("achievement_tier", "")).strip(),
                "image_uri": image_uri,
                "image_path": image_path,
                "image_render_type": "data_uri" if image_uri and str(image_uri).startswith("data:image/") else "url" if image_uri else "none",
            }
        )
    hidden = max(0, len(pool) - len(items))
    return items, hidden
