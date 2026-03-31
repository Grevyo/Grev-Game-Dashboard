import re
import unicodedata
import streamlit as st

COUNTRY_TO_ISO2 = {
    "argentina": "AR",
    "australia": "AU",
    "austria": "AT",
    "belarus": "BY",
    "brazil": "BR",
    "canada": "CA",
    "china": "CN",
    "czech republic": "CZ",
    "denmark": "DK",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "hungary": "HU",
    "india": "IN",
    "indonesia": "ID",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "kazakhstan": "KZ",
    "latvia": "LV",
    "lithuania": "LT",
    "mexico": "MX",
    "netherlands": "NL",
    "norway": "NO",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "peru": "PE",
    "romania": "RO",
    "russia": "RU",
    "sweden": "SE",
    "switzerland": "CH",
    "slovakia": "SK",
    "serbia": "RS",
    "spain": "ES",
    "ukraine": "UA",
    "united kingdom": "GB",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "turkey": "TR",
}


def _normalize_country(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).strip().casefold()
    text = " ".join(text.split())
    text = re.sub(r"[^a-z\s]", "", text)
    return text


def country_to_flag_emoji(country_text: str | None) -> str:
    raw_text = str(country_text or "").strip()
    key = _normalize_country(raw_text)
    iso2 = COUNTRY_TO_ISO2.get(key)
    if not iso2 and len(raw_text) == 2 and raw_text.isalpha():
        iso2 = raw_text.upper()
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


def is_mobile_view(default: bool = False) -> bool:
    """Best-effort mobile detection based on request user-agent."""
    context = getattr(st, "context", None)
    headers = getattr(context, "headers", None) if context is not None else None
    if not headers:
        return default

    user_agent = str(headers.get("user-agent", "")).lower()
    if not user_agent:
        return default

    mobile_tokens = ["iphone", "android", "mobile", "ipad", "ipod", "windows phone"]
    return any(token in user_agent for token in mobile_tokens)
