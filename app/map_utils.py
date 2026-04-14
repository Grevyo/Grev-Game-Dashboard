import re

import pandas as pd


def normalize_map_name(value: object, *, unknown_label: str = "") -> str:
    """Normalize map names and merge trailing `_V2` variants into the base map."""
    text = str(value or "").strip()
    if not text:
        return unknown_label

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?i)_v2$", "", text).strip()
    text = re.sub(r"[_\-\s]+$", "", text).strip()
    if not text:
        return unknown_label

    return text.title()


def normalize_map_series(series: pd.Series, *, unknown_label: str = "") -> pd.Series:
    return series.map(lambda value: normalize_map_name(value, unknown_label=unknown_label))


def normalize_map_column(df: pd.DataFrame, *, column: str = "map", unknown_label: str = "") -> pd.DataFrame:
    out = df.copy()
    if column in out.columns:
        out[column] = normalize_map_series(out[column], unknown_label=unknown_label)
    return out
