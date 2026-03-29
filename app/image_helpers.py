import base64
import mimetypes
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.config import IMAGES

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def _normalize_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).casefold()
    text = text.replace("ⓜ", "m")
    text = text.replace("|", " ")
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _clean_display_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*\|\s*", " | ", text)
    return text


@lru_cache(maxsize=None)
def _build_index(folder: Path) -> list[tuple[str, Path]]:
    if not folder.exists():
        return []
    indexed: list[tuple[str, Path]] = []
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        indexed.append((_normalize_name(path.stem), path))
    return indexed


def _lookup_asset(folder_key: str, query: str | None) -> str | None:
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return None

    folder = IMAGES.get(folder_key)
    if folder is None:
        return None

    index = _build_index(folder)
    if not index:
        return None

    for normalized_stem, path in index:
        if normalized_stem == normalized_query:
            return str(path)

    for normalized_stem, path in index:
        if normalized_query in normalized_stem or normalized_stem in normalized_query:
            return str(path)

    query_parts = re.findall(r"[a-z0-9]{3,}", str(query).casefold()) if query else []
    if query_parts:
        for normalized_stem, path in index:
            if any(part in normalized_stem for part in query_parts):
                return str(path)

    return None


def find_player_photo(player_name: str | None) -> str | None:
    return resolve_player_photo(player_name).get("path")


def resolve_player_photo(player_name: str | None) -> dict[str, str | bool | None]:
    folder = IMAGES.get("player_photos")
    if folder is None or not folder.exists():
        return {"found": False, "path": None, "reason": "player_photos folder missing"}

    query = _clean_display_name(player_name)
    if not query:
        return {"found": False, "path": None, "reason": "empty player name"}

    supported = {ext for ext in SUPPORTED_EXTENSIONS if ext != ".svg"}
    candidates = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in supported
    ]

    by_name: dict[str, Path] = {}
    for path in candidates:
        by_name[path.name.casefold()] = path

    # 1) exact filename match first (with and without extension)
    query_lower = query.casefold()
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        direct = by_name.get(f"{query_lower}{ext}")
        if direct:
            return {"found": True, "path": str(direct), "reason": "exact filename"}

    if Path(query).suffix.lower() in supported:
        exact_file = by_name.get(Path(query).name.casefold())
        if exact_file:
            return {"found": True, "path": str(exact_file), "reason": "exact filename"}

    # 2) normalized match (preserves ability to match names with ⓜ)
    query_norm = _normalize_name(query)
    cleaned_query = re.sub(r"^\s*ⓜ\s*\|\s*", "", query, flags=re.IGNORECASE).strip()
    cleaned_norm = _normalize_name(cleaned_query)

    for path in candidates:
        stem_norm = _normalize_name(path.stem)
        if stem_norm and (stem_norm == query_norm or (cleaned_norm and stem_norm == cleaned_norm)):
            return {"found": True, "path": str(path), "reason": "normalized stem"}

    for path in candidates:
        stem_norm = _normalize_name(path.stem)
        if not stem_norm:
            continue
        if query_norm and (query_norm in stem_norm or stem_norm in query_norm):
            return {"found": True, "path": str(path), "reason": "normalized partial"}
        if cleaned_norm and (cleaned_norm in stem_norm or stem_norm in cleaned_norm):
            return {"found": True, "path": str(path), "reason": "cleaned partial"}

    return {"found": False, "path": None, "reason": "no matching photo asset"}


def find_team_logo(team_name: str | None) -> str | None:
    return _lookup_asset("team_logos", team_name)


def find_competition_logo(competition_name: str | None) -> str | None:
    return _lookup_asset("competition_logos", competition_name)


def resolve_transferred_logo(new_team: str | None) -> str | None:
    team_logo = find_team_logo(new_team)
    if team_logo:
        return team_logo
    return find_competition_logo("cpl")


def find_achievement_image(link_or_name: str | None) -> str | None:
    if not link_or_name:
        return None
    file_name = Path(str(link_or_name)).name
    direct = IMAGES["achievements"] / file_name
    if direct.exists() and direct.suffix.lower() in SUPPORTED_EXTENSIONS:
        return str(direct)
    return _lookup_asset("achievements", file_name or link_or_name)


def find_map_image(map_name: str | None) -> str | None:
    return _lookup_asset("map_images", map_name)


def image_data_uri(image_path: str | None) -> str | None:
    if not image_path:
        return None
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return None
    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "image/png"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime_type};base64,{encoded}"
