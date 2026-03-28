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


def normalize_competitions(df: pd.DataFrame, name_col: str = "raw_competition_name", date_col: str = "date") -> pd.DataFrame:
    if df.empty or name_col not in df.columns:
        return df

    out = df.copy()
    parsed = out[name_col].fillna("").map(parse_competition_details)

    out["competition_family"] = parsed.map(lambda p: p.competition_family)
    out["parsed_season_number"] = pd.array(parsed.map(lambda p: p.parsed_season_number), dtype="Int64")
    out["parsed_event_instance_number"] = pd.array(parsed.map(lambda p: p.parsed_event_instance_number), dtype="Int64")
    out["should_group_competition"] = parsed.map(lambda p: bool(p.grouping_allowed))

    inferred = pd.Series([None] * len(out), index=out.index, dtype="object")
    if date_col in out.columns:
        inferred = _infer_nova_prime_season(out.rename(columns={date_col: "date"}))

    final_season = out["parsed_season_number"].astype("object").copy()
    fill_mask = final_season.isna() & inferred.notna()
    final_season.loc[fill_mask] = inferred.loc[fill_mask]

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
    out["season"] = pd.to_numeric(final_season, errors="coerce").astype("Int64").astype(str).replace("<NA>", None)

    # Backward-compatible alias used by older pages.
    out["competition_group"] = out["grouped_competition_name"]

    return out


def normalize_competition_name(name: str) -> str:
    details = parse_competition_details(name)
    if details.grouping_allowed and details.parsed_season_number is not None:
        return f"{details.family_display_name} Season {details.parsed_season_number}"
    return details.raw_name
