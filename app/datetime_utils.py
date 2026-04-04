from __future__ import annotations

import pandas as pd


def normalize_time_string(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None

    for fmt in ("%H:%M:%S", "%H:%M"):
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%H:%M:%S")
    return None


def normalize_time_series(values: pd.Series) -> pd.Series:
    normalized = values.map(normalize_time_string)
    return normalized.astype("object")


def build_match_timestamp(date_values: pd.Series, time_values: pd.Series | None = None) -> pd.Series:
    date_parsed = pd.to_datetime(date_values, errors="coerce")
    if time_values is None:
        return date_parsed

    normalized_time = normalize_time_series(time_values)
    time_delta = pd.to_timedelta(normalized_time.fillna("00:00:00"), errors="coerce").fillna(pd.Timedelta(0))
    return date_parsed + time_delta
