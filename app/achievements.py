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
_CPL_OPEN_DEBUG_EMITTED = False


def _is_present_text(value) -> bool:
    text = str(value or "").strip()
    return bool(text and text.casefold() not in {"nan", "none", "null"})


def _resolve_achievement_image_for_overview(row: pd.Series) -> tuple[str | None, str | None, str, dict]:
    """Resolve achievement image with explicit priority for parsed achievement_link.

    Priority order:
    1) Usable non-empty achievement_link from row
    2) Existing resolver fallback logic
    3) Placeholder (no image)
    """
    link_value = str(row.get("achievement_link", "") or "").strip()
    debug: dict = {
        "achievement_link_raw": link_value,
        "link_present": _is_present_text(link_value),
    }

    if _is_present_text(link_value):
        if link_value.startswith("data:image/"):
            debug["link_strategy"] = "data_uri_direct"
            return link_value, None, "achievement_link:data_uri", debug
        if re.match(r"^https?://", link_value, flags=re.IGNORECASE):
            debug["link_strategy"] = "http_url_direct"
            return link_value, None, "achievement_link:url", debug

        link_path = Path(link_value).expanduser()
        if link_path.exists() and link_path.is_file():
            image_uri = image_data_uri_thumbnail(str(link_path))
            debug["link_strategy"] = "filesystem_path"
            debug["link_exists"] = True
            debug["link_is_file"] = True
            debug["link_uri_generated"] = bool(image_uri)
            if image_uri:
                return image_uri, str(link_path), "achievement_link:file", debug
        else:
            debug["link_strategy"] = "filesystem_path"
            debug["link_exists"] = False
            debug["link_is_file"] = False

    image_resolution = resolve_achievement_image(
        link_value or row.get("achievement_name"),
        achievement_name=row.get("achievement_name"),
        placement=row.get("position"),
    )
    image_path = image_resolution.get("final_path")
    image_uri = image_data_uri_thumbnail(image_path)
    debug["resolver_source"] = image_resolution.get("source")
    debug["resolver_final_path"] = image_path
    debug["resolver_uri_generated"] = bool(image_uri)
    return image_uri, image_path, "resolver", debug


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

    top = pool
    if cap is not None:
        top = pool.head(cap)
    items = []
    for _, row in top.iterrows():
        image_uri, image_path, image_source, image_debug = _resolve_achievement_image_for_overview(row)
        if not image_uri and image_path and Path(str(image_path)).exists():
            # Hard fallback: if local file exists but thumbnail encoding failed, still force a data URI.
            image_uri = image_data_uri(str(image_path))
        global _CPL_OPEN_DEBUG_EMITTED
        is_cpl_open = "cpl open" in str(row.get("achievement_name", "")).casefold()
        if is_cpl_open and not _CPL_OPEN_DEBUG_EMITTED:
            image_path_exists = bool(image_path and Path(str(image_path)).exists())
            image_uri_is_none = image_uri is None
            image_uri_len = len(image_uri) if isinstance(image_uri, str) else 0
            has_image_branch = bool(image_uri)
            print(
                "[CPL_OPEN_DEBUG]",
                {
                    "player_name": player_name,
                    "achievement_name": row.get("achievement_name"),
                    "achievement_link": row.get("achievement_link"),
                    "resolved_image_path": image_path,
                    "resolved_image_path_exists": image_path_exists,
                    "image_uri_is_none": image_uri_is_none,
                    "image_uri_len": image_uri_len,
                    "image_uri_prefix": str(image_uri or "")[:48],
                    "image_source_selected": image_source,
                    "image_resolution_debug": image_debug,
                    "consumer": consumer,
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
                "image_render_type": "data_uri" if image_uri and str(image_uri).startswith("data:image/") else "url" if image_uri else "none",
            }
        )
    hidden = max(0, len(pool) - len(items))
    return items, hidden
