import re


SEASON_TOKEN_RE = re.compile(r"(?i)\b(?:s|season|ꜱ)\s*(\d+)(?:\.(\d+))?\b")


def parse_competition_name(name: str) -> tuple[str, int | None, int | None]:
    """
    Parse competition strings while enforcing integer seasons.

    Examples:
    - "Cyberathletes Open Qualifier S10.30" -> ("Cyberathletes Open Qualifier", 10, 30)
    - "Cyberathletes Open Qualifier S10" -> ("Cyberathletes Open Qualifier", 10, None)
    - "Cyberathletes Open Qualifier Season 10" -> ("Cyberathletes Open Qualifier", 10, None)
    """
    if not isinstance(name, str) or not name.strip():
        return "Unknown Competition", None, None

    text = name.strip()
    match = SEASON_TOKEN_RE.search(text)
    if not match:
        return text, None, None

    season = int(match.group(1))
    instance = int(match.group(2)) if match.group(2) is not None else None

    family = (text[: match.start()] + text[match.end() :]).strip(" -_#")
    family = re.sub(r"\s{2,}", " ", family).strip()
    if not family:
        family = text
    return family, season, instance


def normalize_competition_name(name: str) -> str:
    family, season, _ = parse_competition_name(name)
    return f"{family} Season {season}" if season is not None else family
