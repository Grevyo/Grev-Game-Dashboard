import re
import unicodedata

COUNTRY_TO_ISO2 = {
    "belarus": "BY",
    "china": "CN",
    "greece": "GR",
    "japan": "JP",
    "latvia": "LV",
    "peru": "PE",
    "russia": "RU",
    "slovakia": "SK",
    "serbia": "RS",
    "spain": "ES",
    "turkey": "TR",
}


def _normalize_country(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).strip().casefold()
    text = " ".join(text.split())
    text = re.sub(r"[^a-z\s]", "", text)
    return text


def country_to_flag_emoji(country_text: str | None) -> str:
    key = _normalize_country(country_text)
    iso2 = COUNTRY_TO_ISO2.get(key)
    if not iso2 or len(iso2) != 2 or not iso2.isalpha():
        return ""
    base = 127397
    return "".join(chr(base + ord(ch)) for ch in iso2.upper())


def nationality_label(country_text: str | None) -> str:
    text = str(country_text or "").strip()
    if not text:
        return ""
    flag = country_to_flag_emoji(text)
    return f"{flag} {text}" if flag else text


def fame_to_stars(fame_value) -> tuple[str, str]:
    try:
        raw = float(fame_value)
    except (TypeError, ValueError):
        return "", ""

    clamped = max(0.0, min(5.0, raw))
    rounded = int(round(clamped))
    stars = "★" * rounded + "☆" * (5 - rounded)
    return stars, f"{raw:.1f}"
