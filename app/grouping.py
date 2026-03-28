import re


def normalize_competition_name(name: str) -> str:
    if not isinstance(name, str):
        return "Unknown Competition"
    text = name.strip()
    family = re.sub(r"\s*[#-]?\s*(?:s|season|ꜱ)?\s*\d+(?:\.\d+)?$", "", text, flags=re.IGNORECASE).strip()
    season_match = re.search(r"(?:s|season|ꜱ)\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if season_match:
        return f"{family} Season {season_match.group(1)}"
    return family or text
