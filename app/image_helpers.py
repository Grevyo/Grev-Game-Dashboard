from pathlib import Path

from app.config import IMAGES


def find_player_photo(player_name: str) -> str | None:
    folder = IMAGES["player_photos"]
    stem = player_name.lower().replace("ⓜ |", "").strip()
    for p in folder.glob("*"):
        if stem and stem in p.stem.lower():
            return str(p)
    return None


def find_achievement_image(link: str | None) -> str | None:
    if not link:
        return None
    file_name = Path(link).name
    local = IMAGES["achievements"] / file_name
    return str(local) if local.exists() else None
