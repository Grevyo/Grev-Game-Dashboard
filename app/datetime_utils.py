from __future__ import annotations

import pandas as pd


def safe_to_datetime(values: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(values):
        return pd.to_datetime(values, errors="coerce")

    cleaned = values.astype("string").str.strip()
    cleaned = cleaned.replace(
        {
            "": pd.NA,
            "nan": pd.NA,
            "nat": pd.NA,
            "none": pd.NA,
            "null": pd.NA,
            "n/a": pd.NA,
            "na": pd.NA,
        }
    )
    return pd.to_datetime(cleaned, errors="coerce")


def coerce_date_columns(
    df: pd.DataFrame,
    columns: list[str] | tuple[str, ...],
    *,
    dataset_name: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    debug_rows: list[str] = []
    for column in columns:
        if column not in out.columns:
            continue

        raw = out[column]
        stripped = raw.astype("string").str.strip()
        converted = safe_to_datetime(raw)
        raw_non_null = int(raw.notna().sum())
        converted_non_null = int(converted.notna().sum())
        from_text = int((converted.notna() & stripped.notna() & stripped.ne("")).sum())
        parse_failures = int((converted.isna() & stripped.notna() & stripped.ne("")).sum())
        failure_samples = stripped[converted.isna() & stripped.notna() & stripped.ne("")].head(3).tolist()

        out[column] = converted
        debug_row = (
            f"{column}: non-null {raw_non_null}->{converted_non_null}, "
            f"parsed_from_text={from_text}, parse_failures={parse_failures}"
        )
        if failure_samples:
            debug_row += f", failure_samples={failure_samples}"
        debug_rows.append(debug_row)

    if debug_rows:
        print(f"[DATE_COERCE] dataset={dataset_name}")
        for row in debug_rows:
            print(f"[DATE_COERCE] {row}")
    return out


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
    date_parsed = safe_to_datetime(date_values)
    if time_values is None:
        return date_parsed

    normalized_time = normalize_time_series(time_values)
    time_delta = pd.to_timedelta(normalized_time.fillna("00:00:00"), errors="coerce").fillna(pd.Timedelta(0))
    return date_parsed + time_delta
