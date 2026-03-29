import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

SEASON_TOKEN_RE = re.compile(r"(?i)(?:\bseason\s*(\d+)\b|\bs\s*(\d+)(?:\.(\d+))?\b)")


@dataclass
class CompetitionParseResult:
    raw_name: str
    competition_family: str | None
    family_display_name: str
    parsed_season_number: int | None
    parsed_event_instance_number: int | None
    grouping_allowed: bool
    do_not_group: bool


def _normalize_for_matching(name: str) -> str:
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = text.translate(_SUPERSCRIPT_DIGITS)
    text = text.replace("ꜱ", "s").replace("Ｓ", "s")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_season_tokens(name: str) -> tuple[int | None, int | None]:
    normalized = _normalize_for_matching(name)
    match = SEASON_TOKEN_RE.search(normalized)
    if not match:
        return None, None

    season = match.group(1) or match.group(2)
    instance = match.group(3)
    return int(season), int(instance) if instance is not None else None


def parse_competition_name(name: str) -> tuple[str, int | None, int | None]:
    """Backward-compatible parser for legacy callers."""
    details = parse_competition_details(name)
    return details.family_display_name, details.parsed_season_number, details.parsed_event_instance_number


def parse_competition_details(name: str) -> CompetitionParseResult:
    raw = str(name or "").strip() or "Unknown Competition"
    lowered = _normalize_for_matching(raw).casefold()

    season, instance = _parse_season_tokens(raw)

    if "cyberathletes open qualifier" in lowered:
        return CompetitionParseResult(raw, "cyberathletes_open_qualifier", "Cyberathletes Open Qualifier", season, instance, True, False)

    if "cpl open tournament" in lowered:
        return CompetitionParseResult(raw, "cpl_open_tournament", "CPL Open Tournament", season, instance, True, False)

    if "nova prime championship" in lowered or "nova prime challengers" in lowered:
        return CompetitionParseResult(raw, "nova_prime_championship", "Nova Prime Championship", season, instance, True, False)

    if "cpl world ladder" in lowered:
        return CompetitionParseResult(raw, "cpl_world_ladder", raw, season, instance, False, True)

    if "league emerald" in lowered and re.search(r"#\s*\d+", lowered):
        return CompetitionParseResult(raw, "league_emerald", raw, season, instance, False, True)

    if "ᴍᴀᴅᴍᴇɴ" in raw or "madmen" in lowered:
        return CompetitionParseResult(raw, "madmen_event", raw, season, instance, False, True)

    return CompetitionParseResult(raw, None, raw, season, instance, False, False)


def _infer_nova_prime_season(df: pd.DataFrame) -> pd.Series:
    inferred = pd.Series([None] * len(df), index=df.index, dtype="object")
    if df.empty:
        return inferred

    anchor_mask = (
        (df["competition_family"] == "nova_prime_championship")
        & df["parsed_season_number"].notna()
        & df["date"].notna()
    )
    anchors = df.loc[anchor_mask, ["date", "parsed_season_number"]].copy()
    if anchors.empty:
        return inferred

    # Conservative season inference: only infer if exactly one known season exists
    # in a +/-60 day window around the stage-based event.
    for idx, row in df.iterrows():
        if row.get("competition_family") != "nova_prime_championship":
            continue
        if pd.notna(row.get("parsed_season_number")):
            continue
        if pd.isna(row.get("date")):
            continue

        nearby = anchors[(anchors["date"] - row["date"]).abs() <= pd.Timedelta(days=60)]
        seasons = sorted({int(s) for s in nearby["parsed_season_number"].dropna().tolist()})
        if len(seasons) == 1:
            inferred.loc[idx] = seasons[0]

    return inferred


def _build_season_date_anchors(df: pd.DataFrame) -> pd.DataFrame:
    """Build conservative per-season date anchors from explicit season rows."""
    required = {"parsed_season_number", "date"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame(columns=["season", "start_date", "end_date"])

    anchors = df[df["parsed_season_number"].notna() & df["date"].notna()].copy()
    if anchors.empty:
        return pd.DataFrame(columns=["season", "start_date", "end_date"])

    anchors["season"] = pd.to_numeric(anchors["parsed_season_number"], errors="coerce").astype("Int64")
    anchors = anchors[anchors["season"].notna()]
    if anchors.empty:
        return pd.DataFrame(columns=["season", "start_date", "end_date"])

    windows = (
        anchors.groupby("season", as_index=False)["date"]
        .agg(start_date="min", end_date="max")
        .sort_values("season")
        .reset_index(drop=True)
    )
    return windows


def build_season_anchors(df: pd.DataFrame) -> pd.DataFrame:
    """Public helper: season/date anchor windows from explicit season-labeled rows."""
    return _build_season_date_anchors(df)


def _infer_season_from_date(date_value: pd.Timestamp, season_windows: pd.DataFrame) -> int | None:
    if pd.isna(date_value) or season_windows.empty:
        return None

    # Prefer unambiguous proximity to a single season window.
    padded = season_windows.copy()
    padded["pad_start"] = padded["start_date"] - pd.Timedelta(days=45)
    padded["pad_end"] = padded["end_date"] + pd.Timedelta(days=45)
    in_window = padded[(padded["pad_start"] <= date_value) & (date_value <= padded["pad_end"])]
    unique_window_seasons = sorted({int(s) for s in in_window["season"].tolist()})
    if len(unique_window_seasons) == 1:
        return unique_window_seasons[0]

    # Fallback: assign by transition midpoints between explicit-season windows.
    rows = season_windows.sort_values("season").reset_index(drop=True)
    if rows.empty:
        return None

    boundaries: list[tuple[int, pd.Timestamp, pd.Timestamp]] = []
    for idx, row in rows.iterrows():
        season = int(row["season"])
        left = pd.Timestamp.min
        right = pd.Timestamp.max
        if idx > 0:
            prev = rows.iloc[idx - 1]
            left_mid = prev["end_date"] + (row["start_date"] - prev["end_date"]) / 2
            left = left_mid
        if idx < len(rows) - 1:
            nxt = rows.iloc[idx + 1]
            right_mid = row["end_date"] + (nxt["start_date"] - row["end_date"]) / 2
            right = right_mid
        boundaries.append((season, left, right))

    candidates = [season for season, left, right in boundaries if left <= date_value <= right]
    return candidates[0] if len(candidates) == 1 else None


def infer_season_from_name_or_date(
    raw_competition_name: str,
    event_date: pd.Timestamp | None,
    season_windows: pd.DataFrame,
) -> tuple[int | None, str]:
    """Resolve season using explicit marker first, then conservative date anchors."""
    details = parse_competition_details(raw_competition_name)
    if details.parsed_season_number is not None:
        return int(details.parsed_season_number), "explicit_from_name"

    inferred = _infer_season_from_date(event_date, season_windows)
    if inferred is not None:
        return inferred, "inferred_from_date_anchor"
    return None, "unresolved"


def resolve_row_season(
    raw_competition_name: str,
    event_date: pd.Timestamp | None,
    season_anchors: pd.DataFrame,
) -> tuple[int | None, str]:
    """Resolve one row season using explicit marker, then anchor-based date inference."""
    return infer_season_from_name_or_date(
        raw_competition_name=raw_competition_name,
        event_date=event_date,
        season_windows=season_anchors,
    )


def normalize_competitions(df: pd.DataFrame, name_col: str = "raw_competition_name", date_col: str = "date") -> pd.DataFrame:
    if df.empty or name_col not in df.columns:
        return df

    out = df.copy()
    parsed = out[name_col].fillna("").map(parse_competition_details)

    out["competition_family"] = parsed.map(lambda p: p.competition_family)
    out["parsed_season_number"] = pd.array(parsed.map(lambda p: p.parsed_season_number), dtype="Int64")
    out["parsed_event_instance_number"] = pd.array(parsed.map(lambda p: p.parsed_event_instance_number), dtype="Int64")
    out["should_group_competition"] = parsed.map(lambda p: bool(p.grouping_allowed))

    normalized_dates = pd.to_datetime(out[date_col], errors="coerce") if date_col in out.columns else pd.Series([pd.NaT] * len(out), index=out.index)
    out["date_for_season_inference"] = normalized_dates

    inference_df = out.copy()
    inference_df["date"] = inference_df["date_for_season_inference"]
    inferred_family = _infer_nova_prime_season(inference_df)
    season_windows = build_season_anchors(inference_df)

    resolved_seasons: list[int | None] = []
    resolve_strategies: list[str] = []
    for idx, row in out.iterrows():
        explicit = row.get("parsed_season_number")
        if pd.notna(explicit):
            resolved_seasons.append(int(explicit))
            resolve_strategies.append("explicit_from_name")
            continue

        name = row.get(name_col, "")
        date_value = row.get("date_for_season_inference")
        season_from_date, strategy = resolve_row_season(name, date_value, season_windows)

        # Keep legacy Nova Prime heuristic as a conservative fallback.
        if season_from_date is None and pd.notna(inferred_family.loc[idx]):
            season_from_date = int(inferred_family.loc[idx])
            strategy = "family_inferred_season_from_timeline"

        resolved_seasons.append(season_from_date)
        resolve_strategies.append(strategy)

    final_season = pd.Series(resolved_seasons, index=out.index, dtype="object")

    grouped_names: list[str] = []
    strategies: list[str] = []
    for idx, info in parsed.items():
        season = final_season.loc[idx]
        if info.do_not_group:
            grouped_names.append(info.raw_name)
            strategies.append("do_not_group_family")
            continue

        if info.grouping_allowed and pd.notna(season):
            grouped_names.append(f"{info.family_display_name} Season {int(season)}")
            if pd.notna(info.parsed_season_number):
                strategies.append("family_explicit_season")
            else:
                strategies.append("family_inferred_season_from_timeline")
            continue

        grouped_names.append(info.raw_name)
        if info.grouping_allowed:
            strategies.append("family_no_confident_season_keep_raw")
        else:
            strategies.append("standalone_raw")

    out["raw_competition_name"] = out[name_col].fillna("").astype(str).str.strip()
    out["grouped_competition_name"] = grouped_names
    out["grouping_strategy"] = strategies
    out["season_resolution_strategy"] = resolve_strategies
    out["season"] = pd.to_numeric(final_season, errors="coerce").astype("Int64").astype(str).replace("<NA>", None)
    out = out.drop(columns=["date_for_season_inference"], errors="ignore")

    # Backward-compatible alias used by older pages.
    out["competition_group"] = out["grouped_competition_name"]

    return out


def normalize_competition_name(name: str) -> str:
    details = parse_competition_details(name)
    if details.grouping_allowed and details.parsed_season_number is not None:
        return f"{details.family_display_name} Season {details.parsed_season_number}"
    return details.raw_name
