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
    return _lookup_asset("player_photos", player_name)


def find_team_logo(team_name: str | None) -> str | None:
    return _lookup_asset("team_logos", team_name)


def find_competition_logo(competition_name: str | None) -> str | None:
    return _lookup_asset("competition_logos", competition_name)


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
