import re
from pathlib import Path

import pandas as pd

from app.image_helpers import image_data_uri, image_data_uri_thumbnail, resolve_achievement_image

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


def _normalized_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _extract_first_int(value) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def _placement_sort_value(position_value) -> float:
    """Return a comparable placement score where lower means better finish."""
    lower, _ = _placement_bounds(position_value)
    return float(lower if lower is not None else 9999.0)


def _placement_bounds(position_value) -> tuple[int | None, int | None]:
    """Return (best_possible_finish, worst_possible_finish)."""
    text = _normalized_text(position_value)
    if not text:
        return None, None

    # Top-N / Top N (e.g., "Top 10")
    top_n = re.search(r"\btop\s*-?\s*(\d+)\b", text)
    if top_n:
        n = int(top_n.group(1))
        n = max(1, n)
        return 1, n

    # Range forms (e.g., 4th-10th, 9th–16th)
    numbers = [int(value) for value in re.findall(r"\d+", text)]
    if numbers:
        return min(numbers), max(numbers)

    return None, None


def _is_cpl_open(achievement_name: str) -> bool:
    name = _normalized_text(achievement_name)
    return bool(re.search(r"\bcpl\b", name) and re.search(r"\bopen\b", name))


def _is_cpl_ladder(achievement_name: str) -> bool:
    name = _normalized_text(achievement_name)
    return bool(re.search(r"\bcpl\b", name) and re.search(r"\bladder\b", name))


def _is_top_10_ladder(achievement_name: str, position_value) -> bool:
    if not _is_cpl_ladder(achievement_name):
        return False
    lower, upper = _placement_bounds(position_value)
    if upper is not None:
        return upper <= 10
    return (lower or 9999) <= 10


def _achievement_priority_group(row: pd.Series) -> int:
    """Group order: ladder top-10 first, non-open middle, CPL Open last."""
    name = str(row.get("achievement_name", "") or "")
    position = row.get("position", "")
    if _is_top_10_ladder(name, position):
        return 0
    if _is_cpl_open(name):
        return 2
    return 1


def _achievement_sort_columns(pool: pd.DataFrame) -> pd.DataFrame:
    season_num = pd.to_numeric(pool.get("season_name"), errors="coerce")
    season_num = season_num.fillna(pool.get("season_name", "").map(_extract_first_int)).fillna(0)

    placement_rank = pool.get("position", "").map(_placement_sort_value)
    tier_priority = pool.get("achievement_tier", "").astype(str).str.upper().map(TIER_PRIORITY).fillna(20)
    name_key = pool.get("achievement_name", "").astype(str).str.strip().str.casefold()
    position_key = pool.get("position", "").astype(str).str.strip().str.casefold()
    group_priority = pool.apply(_achievement_priority_group, axis=1)

    return pool.assign(
        _season=season_num,
        _placement=placement_rank,
        _tier=tier_priority,
        _group=group_priority,
        _name_key=name_key,
        _position_key=position_key,
    )


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

    pool = _achievement_sort_columns(pool)
    pool = pool.sort_values(
        ["_group", "_placement", "_tier", "_season", "_name_key", "_position_key"],
        ascending=[True, True, False, False, True, True],
    )

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
