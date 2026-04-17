import base64
import html
import mimetypes
import re
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st

from app.config import IMAGES
from app.data_loader import get_medisports_player_names, normalize_player_key
from app.image_helpers import (
    find_achievement_image,
    find_competition_logo,
    image_data_uri_thumbnail,
    normalize_placement_value,
    resolve_achievement_image,
    resolve_player_photo,
    SUPPORTED_EXTENSIONS,
)
from app.page_layout import section_header


TIMELINE_TROPHY_EVENT_TYPES = {
    "result",
    "league result",
    "qualification",
    "invite",
}
TIMELINE_TROPHY_CATEGORIES = {"competition"}
EVENT_PHOTO_OVERRIDES = (
    {
        "asset": "bonk_transfer.png",
        "label": "Event Photo",
        "caption": "Taken by Barry Snail back in Season 8 before PAX Disbanded",
        "match": {
            "tokens_all": ("leon replaces bonk as igl",),
            "event_types": ("lineup_change",),
            "categories": ("roster",),
            "season": "11",
            "player_name": "leon",
        },
    },
    {
        "asset": "stroky_transfer.png",
        "label": "Event Photo",
        "caption": "After a failed run at the opens, Stroky venting frustrations",
        "match": {
            "tokens_any": ("stroky",),
            "event_types": ("transfer_in", "transfer_out"),
            "categories": ("roster",),
            "player_name": "stroky",
        },
    },
    {
        "asset": "S10_Nova.png",
        "label": "Event Photo",
        "caption": "Snap of the moment Medicart made it their furthest ever in Major qualifications, taken by Barry Snail",
        "match": {
            "tokens_all": (
                "qualified",
                "nova prime challengers",
                "season 10",
            ),
            "event_types": ("result", "qualification"),
            "categories": ("competition",),
            "season": "10",
        },
    },
)


def _display_value(value: object) -> str:
    if _is_missing(value):
        return ""
    text = str(value).strip()
    return "" if not text else text


def _to_int_text(value: object, *, fallback: str = "") -> str:
    if _is_missing(value):
        return fallback
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        text = str(value).strip()
        return text if text else fallback


def _timeline_meta_line(row: pd.Series) -> str:
    event_type = _display_value(row.get("event_type")).replace("_", " ").title()
    category = _display_value(row.get("category")).replace("_", " ").title()
    compact_label = event_type or category
    return compact_label


def _timeline_highlights(row: pd.Series) -> list[tuple[str, str]]:
    chips: list[tuple[str, str]] = []

    competition = _display_value(row.get("competition"))
    stage_or_group = _display_value(row.get("stage_or_group"))
    placement = _display_value(row.get("placement"))
    record = _display_value(row.get("record"))
    opponent = _display_value(row.get("opponent_or_org"))
    player_name = _display_value(row.get("player_name"))
    from_entity = _display_value(row.get("from_entity"))
    to_entity = _display_value(row.get("to_entity"))
    fee_text = _to_int_text(row.get("fee_cpl"))
    ranking_system = _display_value(row.get("ranking_system"))
    rank_from = _to_int_text(row.get("ranking_from"))
    rank_to = _to_int_text(row.get("ranking_to"))
    tier_after_event = _display_value(row.get("tier_after_event"))
    public_visibility = _display_value(row.get("public_visibility"))

    if competition:
        chips.append(("competition", f"Competition: {competition}"))
    if stage_or_group:
        chips.append(("stage", f"Stage: {stage_or_group}"))
    if placement:
        chips.append(("placement", f"Placement: {placement}"))
    if record:
        chips.append(("result", f"Record: {record}"))
    if player_name:
        chips.append(("player", f"Player: {player_name}"))
    if opponent:
        chips.append(("opponent", f"Org/Opponent: {opponent}"))
    if from_entity or to_entity:
        flow = " → ".join([part for part in [from_entity, to_entity] if part])
        if flow:
            chips.append(("movement", f"Movement: {flow}"))
    if fee_text:
        chips.append(("fee", f"Fee: {fee_text} CPL"))
    if rank_from or rank_to:
        rank_flow = " → ".join([part for part in [rank_from, rank_to] if part])
        if rank_flow:
            rank_label = f"{ranking_system} Ranking" if ranking_system else "Ranking"
            chips.append(("ranking", f"{rank_label}: {rank_flow}"))
    if tier_after_event:
        chips.append(("tier", f"Tier: {tier_after_event}"))
    if public_visibility:
        chips.append(("visibility", f"Visibility: {public_visibility}"))
    return chips


def _timeline_identity_chips(row: pd.Series, *, tone_label: str, priority: str) -> list[tuple[str, str]]:
    chips: list[tuple[str, str]] = []
    event_type = _display_value(row.get("event_type")).replace("_", " ").title()
    category = _display_value(row.get("category")).replace("_", " ").title()
    # Keep identity chips intentionally sparse to avoid repeating
    # information already shown in the integrated event header.
    if category and category.casefold() != event_type.casefold():
        chips.append(("identity-soft", category))
    elif tone_label and tone_label.casefold() != event_type.casefold():
        chips.append(("tone", tone_label))
    if priority == "featured" and not any(kind in {"identity-soft", "tone"} for kind, _ in chips):
        chips.append(("priority", "Featured"))
    return chips


def _event_tone(row: pd.Series) -> tuple[str, str]:
    event_type = _normalize_for_match(row.get("event_type"))
    category = _normalize_for_match(row.get("category"))
    text_blob = _normalize_for_match(
        " ".join(_display_value(row.get(field)) for field in ["title", "details", "notes"])
    )

    if category == "competition" or event_type in {"result", "league result", "qualification"}:
        return "competition", "Competition"
    if category == "roster" or any(token in event_type for token in ["transfer", "lineup", "sign"]):
        return "transfer", "Roster Move"
    if category == "ranking" or "ranking" in event_type or "tier change" in event_type:
        return "ranking", "Ranking"
    if category in {"community", "organisation"} or any(token in event_type for token in ["community", "rebrand", "founding"]):
        return "organisation", "Community / Org"
    if any(token in text_blob for token in ["milestone", "title", "champion", "historic", "achievement"]):
        return "milestone", "Milestone"
    return "general", "Update"


def _event_priority(row: pd.Series) -> str:
    event_type = _normalize_for_match(row.get("event_type"))
    category = _normalize_for_match(row.get("category"))
    placement = _normalize_for_match(row.get("placement"))
    title_blob = _normalize_for_match(" ".join(_display_value(row.get(field)) for field in ["title", "details", "notes"]))

    rank_from = _to_int_text(row.get("ranking_from"))
    rank_to = _to_int_text(row.get("ranking_to"))
    rank_delta = 0
    if rank_from.isdigit() and rank_to.isdigit():
        rank_delta = int(rank_from) - int(rank_to)

    if category in {"organisation", "community"} and event_type in {"founding", "rebrand", "community join", "community leave"}:
        return "featured"
    if category == "roster" and any(token in event_type for token in ["transfer", "lineup", "sign"]):
        return "featured"
    if category == "competition" and (
        placement.startswith("1")
        or any(token in placement for token in ["gold", "title", "champion"])
        or any(token in title_blob for token in ["won", "champion", "title", "qualified", "grand final", "final"])
    ):
        return "featured"
    if category == "ranking" and rank_delta >= 5:
        return "featured"
    if any(token in title_blob for token in ["major", "historic", "milestone", "first ever"]):
        return "featured"
    return "standard"


def _event_width_class(row: pd.Series, *, visuals_count: int, highlights_count: int, priority: str) -> str:
    details_len = len(_display_value(row.get("details")))
    notes_len = len(_display_value(row.get("notes")))
    title_len = len(_display_value(row.get("title")))
    event_type = _normalize_for_match(row.get("event_type"))
    category = _normalize_for_match(row.get("category"))

    richness_score = 0
    if priority == "featured":
        richness_score += 3
    richness_score += min(visuals_count, 2)
    richness_score += min(highlights_count, 3)
    richness_score += 1 if details_len > 130 else 0
    richness_score += 1 if notes_len > 90 else 0
    richness_score += 1 if title_len > 48 else 0
    if category in {"competition", "ranking"}:
        richness_score += 1
    if any(token in event_type for token in ["final", "qualification", "title", "transfer", "milestone"]):
        richness_score += 1

    if richness_score >= 7:
        return "expanded"
    if richness_score <= 2:
        return "compact"
    return "regular"


def _event_layout_variant(
    row: pd.Series,
    *,
    visuals_count: int,
    highlights_count: int,
    details: str,
    notes: str,
    priority: str,
) -> str:
    category = _normalize_for_match(row.get("category"))
    event_type = _normalize_for_match(row.get("event_type"))
    placement = _normalize_for_match(row.get("placement"))
    title_blob = _normalize_for_match(_display_value(row.get("title")))

    has_ranking_signal = (
        category == "ranking"
        or "ranking" in event_type
        or "tier change" in event_type
        or "promoted" in title_blob
        or "demoted" in title_blob
    )
    if has_ranking_signal:
        return "ranking"

    if category in {"organisation", "community"}:
        return "org"

    if category == "roster" or any(token in event_type for token in ["transfer", "lineup", "sign", "bench"]):
        return "roster"

    if category == "competition" or any(token in event_type for token in ["result", "qualification", "final"]):
        if visuals_count >= 1 or any(token in placement for token in ["1", "2", "3", "champion"]):
            return "competition"
        return "result-compact"

    text_len = len(details) + len(notes)
    if visuals_count == 0 and text_len < 90 and highlights_count <= 2 and priority != "featured":
        return "compact"
    if text_len > 170 or priority == "featured":
        return "story"
    return "milestone"


def _event_media_limit(layout_variant: str) -> int:
    if layout_variant in {"ranking", "org", "compact", "result-compact"}:
        return 0
    if layout_variant in {"roster", "milestone", "story"}:
        return 1
    if layout_variant == "competition":
        return 2
    return 1


def _redundancy_tokens(value: object) -> set[str]:
    text = _normalize_for_match(value)
    if not text:
        return set()
    stop_words = {
        "a", "an", "the", "was", "were", "is", "are",
        "to", "into", "in", "on", "at", "of", "for", "from", "as", "during",
        "season", "team", "main", "lineup",
        "move", "moved", "change", "changed",
        "started", "improved", "retained", "received",
        "direct", "invite", "result", "finish",
    }
    return {token for token in text.split() if token and token not in stop_words}


def _token_overlap(left: set[str], right: set[str]) -> float:
    if not left:
        return 0.0
    return len(left & right) / max(1, len(left))


def _should_render_timeline_details(
    *,
    row: pd.Series,
    title: str,
    details: str,
    notes: str,
    chips: list[tuple[str, str]],
    layout_variant: str,
    priority: str,
) -> bool:
    details_text = _display_value(details)
    if not details_text:
        return False

    # Keep richer/story cards unchanged.
    if priority == "featured" or layout_variant in {"competition", "story", "milestone"}:
        return True

    detail_tokens = _redundancy_tokens(details_text)
    title_tokens = _redundancy_tokens(title)
    chip_tokens = _redundancy_tokens(" ".join(chip for _, chip in chips))

    duplicate_of_title = bool(detail_tokens) and _token_overlap(detail_tokens, title_tokens) >= 0.74
    duplicate_of_chips = bool(detail_tokens) and _token_overlap(detail_tokens, chip_tokens) >= 0.60
    has_notes = bool(_display_value(notes))

    # Kill the repeated middle sentence on small/simple cards.
    if layout_variant in {"compact", "result-compact", "ranking", "org"}:
        if duplicate_of_title or duplicate_of_chips or len(details_text) <= 90:
            return False

    if layout_variant == "roster":
        if len(details_text) <= 100 and (duplicate_of_title or duplicate_of_chips or has_notes):
            return False

    return True


def _safe_html(value: object) -> str:
    return html.escape(_display_value(value))


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if not pd.api.types.is_scalar(value):
        return False
    return bool(pd.isna(value))


def _normalize_for_match(value: object) -> str:
    if _is_missing(value):
        text = ""
    else:
        text = str(value)
    text = unicodedata.normalize("NFKD", text).casefold()
    text = text.replace("ⓜ", "m")
    text = re.sub(r"[|/\\•·]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_player_plain(value: object) -> str:
    text = _display_value(value)
    if not text:
        return ""
    parts = [part.strip() for part in re.split(r"\|", text) if part.strip()]
    if parts:
        text = parts[-1]
    text = re.sub(r"^[^a-zA-Z0-9]+", "", text)
    return normalize_player_key(text)


def _placement_rank_text(value: object) -> str:
    parsed = normalize_placement_value(value)
    return str(parsed) if parsed else ""


def _text_for_entity_detection(row: pd.Series) -> str:
    fields = [
        _display_value(row.get("title")),
        _display_value(row.get("details")),
        _display_value(row.get("notes")),
        _display_value(row.get("opponent_or_org")),
        _display_value(row.get("from_entity")),
        _display_value(row.get("to_entity")),
        _display_value(row.get("competition")),
        _display_value(row.get("player_name")),
    ]
    return f" {_normalize_for_match(' '.join(fields))} "


def _competition_from_row(row: pd.Series, known_competitions: list[str], competition_logo_index: dict[str, str]) -> str:
    structured = _display_value(row.get("competition"))
    if structured:
        return structured

    row_text = _text_for_entity_detection(row)
    for competition in known_competitions:
        normalized = _normalize_for_match(competition)
        if normalized and f" {normalized} " in row_text:
            return competition
    for competition in competition_logo_index:
        if competition and f" {competition} " in row_text:
            return competition
    return ""


def _infer_gold_placement(row: pd.Series) -> str:
    placement = _display_value(row.get("placement"))
    if placement:
        return placement

    row_text = _normalize_for_match(" ".join(_display_value(row.get(field)) for field in ["title", "details", "notes"]))
    if any(token in row_text for token in [" champion", " won ", " 1st", " first place", " gold "]):
        return "1st"
    return ""


def _build_player_photo_index(data: dict) -> dict[str, str]:
    players_df = data.get("players", pd.DataFrame())
    matches_df = data.get("player_matches_full", pd.DataFrame())

    candidates: list[str] = []
    for col in ["player", "player_clean", "name"]:
        if col in players_df.columns:
            candidates.extend(players_df[col].dropna().astype(str).tolist())
    candidates.extend(get_medisports_player_names(matches_df, player_col="player"))

    photos_folder = IMAGES.get("player_photos")
    if photos_folder and photos_folder.exists():
        candidates.extend(
            path.stem
            for path in photos_folder.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    index: dict[str, str] = {}
    for player in candidates:
        key = _normalize_player_plain(player)
        if not key or key in index:
            continue
        photo = resolve_player_photo(player)
        path = photo.get("path")
        if path:
            index[key] = str(path)
    return index


def _resolve_player_visual(row: pd.Series, player_photo_index: dict[str, str]) -> tuple[str | None, str | None]:
    if not player_photo_index:
        return None, None

    structured_match = _resolve_structured_player_visual(row, player_photo_index)
    if structured_match[0]:
        return structured_match

    if _is_roster_like_event(row):
        return None, None

    haystack = _text_for_entity_detection(row)

    for key, path in player_photo_index.items():
        if not key:
            continue
        normalized_key = _normalize_for_match(key)
        if normalized_key and f" {normalized_key} " in haystack:
            return key, path
    return None, None


def _is_roster_like_event(row: pd.Series) -> bool:
    category = _normalize_for_match(row.get("category"))
    event_type = _normalize_for_match(row.get("event_type"))
    if category == "roster":
        return True
    return any(token in event_type for token in ["transfer", "lineup", "bench", "sign"])


def _resolve_structured_player_visual(
    row: pd.Series,
    player_photo_index: dict[str, str],
) -> tuple[str | None, str | None]:
    candidate_fields = ("player_name", "to_entity", "from_entity")
    for field in candidate_fields:
        candidate_name = _display_value(row.get(field))
        if not candidate_name:
            continue
        candidate_key = _normalize_player_plain(candidate_name)
        if not candidate_key:
            continue
        path = player_photo_index.get(candidate_key)
        if path:
            return candidate_key, path
    return None, None


def _build_competition_logo_index(known_competitions: list[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for competition in known_competitions:
        normalized = _normalize_for_match(competition)
        if not normalized:
            continue
        logo_path = find_competition_logo(competition)
        if logo_path:
            index[normalized] = logo_path

    logos_folder = IMAGES.get("competition_logos")
    if logos_folder and logos_folder.exists():
        for path in logos_folder.iterdir():
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            normalized = _normalize_for_match(path.stem)
            if normalized and normalized not in index:
                index[normalized] = str(path)
    return index


def _resolve_achievement_path_from_record(row: pd.Series) -> str | None:
    link_value = _display_value(row.get("achievement_link"))
    if link_value:
        file_name = Path(link_value).name
        candidate = IMAGES["achievements"] / file_name
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    resolved = resolve_achievement_image(
        link_or_name=row.get("achievement_name"),
        achievement_name=row.get("achievement_name"),
        placement=row.get("position"),
    )
    final_path = resolved.get("final_path")
    return str(final_path) if final_path else None


def _build_achievement_reference_index(data: dict) -> list[dict[str, object]]:
    achievements_df = data.get("achievements", pd.DataFrame())
    if achievements_df.empty:
        return []

    reference: list[dict[str, object]] = []
    dedupe: set[tuple[str, str, str, str]] = set()
    for _, ach_row in achievements_df.iterrows():
        achievement_name = _display_value(ach_row.get("achievement_name"))
        if not achievement_name:
            continue

        image_path = _resolve_achievement_path_from_record(ach_row)
        if not image_path:
            continue

        name_norm = _normalize_for_match(achievement_name)
        season_text = _to_int_text(ach_row.get("season_name"))
        placement_text = _display_value(ach_row.get("position"))
        placement_rank = _placement_rank_text(placement_text)
        dedupe_key = (name_norm, season_text, placement_rank, Path(image_path).name.casefold())
        if dedupe_key in dedupe:
            continue
        dedupe.add(dedupe_key)

        reference.append(
            {
                "name": achievement_name,
                "name_norm": name_norm,
                "season_text": season_text,
                "placement_text": placement_text,
                "placement_rank": placement_rank,
                "image_path": image_path,
            }
        )
    return reference


def _is_trophy_relevant_row(row: pd.Series) -> bool:
    category = _normalize_for_match(row.get("category"))
    event_type = _normalize_for_match(row.get("event_type"))
    return category in TIMELINE_TROPHY_CATEGORIES or event_type in TIMELINE_TROPHY_EVENT_TYPES


def _is_strong_achievement_signal(row: pd.Series, placement: str) -> bool:
    if not _is_trophy_relevant_row(row):
        return False
    # Do not attach trophy visuals for generic competition mentions.
    if not _placement_rank_text(placement):
        return False
    return True


def _resolve_trophy_from_achievement_reference(
    row: pd.Series,
    competition: str,
    placement: str,
    achievement_reference: list[dict[str, object]],
) -> str | None:
    if not achievement_reference or not _is_strong_achievement_signal(row, placement):
        return None

    competition_norm = _normalize_for_match(competition)
    placement_rank = _placement_rank_text(placement)
    timeline_season = _to_int_text(row.get("season"))
    if not competition_norm or not placement_rank:
        return None

    exact_matches: list[dict[str, object]] = []
    loose_matches: list[dict[str, object]] = []
    for record in achievement_reference:
        name_norm = str(record.get("name_norm") or "")
        if not name_norm:
            continue

        if competition_norm == name_norm:
            competition_match_kind = "exact"
        elif competition_norm in name_norm and len(competition_norm) >= 8:
            competition_match_kind = "contains"
        else:
            continue

        record_placement = str(record.get("placement_rank") or "")
        if not record_placement or placement_rank != record_placement:
            continue

        record_season = str(record.get("season_text") or "")
        if timeline_season and record_season and timeline_season != record_season:
            continue

        image_path = str(record.get("image_path") or "")
        if not image_path:
            continue

        if competition_match_kind == "exact":
            exact_matches.append(record)
        else:
            loose_matches.append(record)

    candidates = exact_matches or loose_matches
    if not candidates:
        return None

    if timeline_season:
        season_matched = [
            record for record in candidates if str(record.get("season_text") or "") == timeline_season
        ]
        if season_matched:
            candidates = season_matched

    if len(candidates) != 1:
        return None

    image_path = str(candidates[0].get("image_path") or "")
    return image_path or None


def _resolve_tournament_visual(
    row: pd.Series,
    known_competitions: list[str],
    competition_logo_index: dict[str, str],
    achievement_reference: list[dict[str, object]],
) -> tuple[str | None, str | None, str | None]:
    competition = _competition_from_row(row, known_competitions, competition_logo_index)
    if not competition:
        return None, None, None

    placement = _infer_gold_placement(row)
    trophy_path = _resolve_trophy_from_achievement_reference(
        row=row,
        competition=competition,
        placement=placement,
        achievement_reference=achievement_reference,
    )
    if not trophy_path:
        trophy_path = _resolve_truthful_trophy_visual(competition=competition, placement=placement)

    competition_logo = competition_logo_index.get(_normalize_for_match(competition))
    return competition, competition_logo, trophy_path


def _resolve_truthful_trophy_visual(competition: str, placement: str) -> str | None:
    """Resolve a trophy/achievement image only when we have a confident, truthful match."""
    competition_text = _normalize_for_match(competition)
    placement_text = _display_value(placement)
    placement_rank = _placement_rank_text(placement_text)

    if not competition_text or not placement_rank:
        return None

    # Use known explicit mapping logic (e.g. CPLOpen1..4) but reject fuzzy fallbacks.
    resolved = resolve_achievement_image(
        link_or_name=competition,
        achievement_name=competition,
        placement=placement_text,
    )
    if resolved.get("source") == "cpl_open_position_map":
        final_path = resolved.get("final_path")
        return str(final_path) if final_path else None

    # Strict league medal mapping: only use assets when league + placement genuinely match.
    if "league" in competition_text:
        league_tier = None
        for tier in ("bronze", "silver", "gold", "emerald", "diamond", "daimond"):
            if tier in competition_text:
                league_tier = "diamond" if tier == "daimond" else tier
                break

        if league_tier and placement_rank:
            # Diamond has dedicated finishing-place assets (4th..9th) in this project.
            if league_tier == "diamond" and placement_rank in {"4", "5", "6", "7", "8", "9"}:
                variants = [f"league-diamond-{placement_rank}th", f"league-daimond-{placement_rank}th"]
                for variant in variants:
                    direct = find_achievement_image(
                        link_or_name=variant,
                        achievement_name=competition,
                        placement=placement_rank,
                    )
                    if direct and _normalize_for_match(variant) in _normalize_for_match(Path(direct).stem):
                        return direct

            if placement_rank in {"1", "2", "3"}:
                medal_name = {"1": "gold", "2": "silver", "3": "bronze"}[placement_rank]
                expected = f"league-{league_tier}-{medal_name}"
                direct = find_achievement_image(
                    link_or_name=expected,
                    achievement_name=competition,
                    placement=placement_rank,
                )
                if direct and _normalize_for_match(expected) in _normalize_for_match(Path(direct).stem):
                    return direct

    # No confident match -> no trophy visual.
    return None


def _timeline_text_blob(row: pd.Series) -> str:
    return _normalize_for_match(
        " ".join(
            _display_value(row.get(field))
            for field in [
                "title",
                "details",
                "notes",
                "competition",
                "opponent_or_org",
                "from_entity",
                "to_entity",
                "player_name",
                "stage_or_group",
                "ranking_system",
                "tier_after_event",
                "public_visibility",
            ]
        )
    )


def _resolve_event_photo_override(row: pd.Series) -> dict[str, str] | None:
    photos_dir = IMAGES.get("news_photos")
    if not photos_dir or not photos_dir.exists():
        return None

    blob = _timeline_text_blob(row)
    event_type = _normalize_for_match(row.get("event_type"))
    category = _normalize_for_match(row.get("category"))
    season = _to_int_text(row.get("season"))

    for override in EVENT_PHOTO_OVERRIDES:
        matcher = override["match"]

        token_any = tuple(_normalize_for_match(token) for token in matcher.get("tokens_any", ()))
        if token_any and not any(token and token in blob for token in token_any):
            continue

        token_all = tuple(_normalize_for_match(token) for token in matcher.get("tokens_all", ()))
        if token_all and not all(token and token in blob for token in token_all):
            continue

        event_types = tuple(_normalize_for_match(token) for token in matcher.get("event_types", ()))
        if event_types and event_type not in event_types:
            continue

        categories = tuple(_normalize_for_match(token) for token in matcher.get("categories", ()))
        if categories and category not in categories:
            continue

        expected_season = matcher.get("season")
        if expected_season and season != expected_season:
            continue

        expected_player = _normalize_player_plain(matcher.get("player_name"))
        if expected_player:
            row_player = _normalize_player_plain(row.get("player_name"))
            if row_player != expected_player:
                continue

        expected_from = _normalize_for_match(matcher.get("from_entity"))
        if expected_from:
            row_from = _normalize_for_match(row.get("from_entity"))
            if row_from != expected_from:
                continue

        expected_to = _normalize_for_match(matcher.get("to_entity"))
        if expected_to:
            row_to = _normalize_for_match(row.get("to_entity"))
            if row_to != expected_to:
                continue

        expected_title = _normalize_for_match(matcher.get("title"))
        if expected_title:
            row_title = _normalize_for_match(row.get("title"))
            if row_title != expected_title:
                continue

        path = photos_dir / override["asset"]
        if not path.exists() or not path.is_file():
            continue

        return {
            "label": override["label"],
            "caption": override["caption"],
            "path": str(path),
        }
    return None


def _resolve_photo_asset_event_image(row: pd.Series) -> dict[str, str] | None:
    photos_dir = IMAGES.get("news_photos")
    if not photos_dir or not photos_dir.exists():
        return None

    asset_value = _display_value(row.get("photo_asset"))
    if not asset_value:
        return None

    asset_name = Path(asset_value).name
    if not asset_name:
        return None

    candidate = photos_dir / asset_name
    if candidate.exists() and candidate.is_file():
        return {"label": "Event Photo", "caption": "", "path": str(candidate)}

    stem = Path(asset_name).stem
    if not stem:
        return None

    for extension in SUPPORTED_EXTENSIONS:
        variant = photos_dir / f"{stem}{extension}"
        if variant.exists() and variant.is_file():
            return {"label": "Event Photo", "caption": "", "path": str(variant)}
    return None


def _resolve_event_photo(row: pd.Series) -> dict[str, str] | None:
    photo_asset_image = _resolve_photo_asset_event_image(row)
    if photo_asset_image:
        return photo_asset_image

    # Legacy fallback while older rows are still being migrated.
    return _resolve_event_photo_override(row)




def _image_uri_with_fallback(path: str | None, *, max_width: int, max_height: int) -> str | None:
    if not path:
        return None

    uri = image_data_uri_thumbnail(path, max_width=max_width, max_height=max_height)
    if uri:
        return uri

    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None

    mime_type, _ = mimetypes.guess_type(file_path.name)
    if not mime_type:
        mime_type = "image/png"

    try:
        payload = base64.b64encode(file_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime_type};base64,{payload}"

def _visual_priority(
    row: pd.Series,
    player_image_uri: str | None,
    competition_image_uri: str | None,
    trophy_image_uri: str | None,
) -> list[tuple[str, str]]:
    event_type = _normalize_for_match(row.get("event_type"))
    category = _normalize_for_match(row.get("category"))
    player_centric = any(token in event_type for token in ["transfer", "sign", "roster"]) or category == "roster"
    tournament_centric = category == "competition" or "qualification" in event_type or "result" in event_type

    visuals: list[tuple[str, str]] = []
    if player_image_uri:
        visuals.append(("Player", player_image_uri))
    if competition_image_uri:
        visuals.append(("Competition", competition_image_uri))
    if trophy_image_uri:
        visuals.append(("Achievement", trophy_image_uri))

    if player_centric and len(visuals) > 1:
        visuals = sorted(visuals, key=lambda item: 0 if item[0] == "Player" else 1)
    elif tournament_centric and len(visuals) > 1:
        visuals = sorted(
            visuals,
            key=lambda item: 0 if item[0] == "Competition" else (1 if item[0] == "Achievement" else 2),
        )

    if not visuals and player_image_uri:
        visuals = [("Player", player_image_uri)]
    return visuals[:2]


def render(data: dict):
    timeline_df = data.get("medisports_timeline", pd.DataFrame()).copy()
    section_header(
        "Medisports Timeline",
        "Long-form structured chronology powered by medisports_timeline.csv.",
    )

    if timeline_df.empty:
        st.info("No timeline rows available yet. Add entries in data/medisports_timeline.csv.")
        return

    seasons = sorted([str(int(v)) for v in timeline_df["season"].dropna().unique()])
    event_types = sorted([str(v).replace("_", " ").title() for v in timeline_df["event_type"].dropna().unique()])
    categories = sorted([str(v).replace("_", " ").title() for v in timeline_df["category"].dropna().unique()])

    visibility_values = (
        sorted(
            {
                value
                for value in timeline_df.get("public_visibility", pd.Series(dtype=str))
                .dropna()
                .astype(str)
                .map(str.strip)
                if value
            }
        )
        if "public_visibility" in timeline_df.columns
        else []
    )

    filter_cols = st.columns(5, gap="small")
    selected_seasons = filter_cols[0].multiselect("Season", options=seasons, default=[])
    selected_event_types = filter_cols[1].multiselect("Event Type", options=event_types, default=[])
    selected_categories = filter_cols[2].multiselect("Category", options=categories, default=[])
    sort_order = filter_cols[3].segmented_control("Order", ["Newest first", "Oldest first"], default="Newest first")
    selected_visibility = filter_cols[4].multiselect("Visibility", options=visibility_values, default=[])

    filtered = timeline_df.copy()
    if selected_seasons:
        filtered = filtered[filtered["season"].map(lambda v: str(int(v)) if pd.notna(v) else "").isin(selected_seasons)]
    if selected_event_types:
        filtered = filtered[
            filtered["event_type"]
            .fillna("")
            .map(lambda v: str(v).replace("_", " ").title())
            .isin(selected_event_types)
        ]
    if selected_categories:
        filtered = filtered[
            filtered["category"]
            .fillna("")
            .map(lambda v: str(v).replace("_", " ").title())
            .isin(selected_categories)
        ]
    if selected_visibility:
        filtered = filtered[
            filtered["public_visibility"]
            .fillna("")
            .map(lambda v: str(v).strip())
            .isin(selected_visibility)
        ]

    ascending = sort_order == "Oldest first"
    filtered = filtered.sort_values(["season", "date_sort", "title"], ascending=[ascending, ascending, True], na_position="last")
    known_competitions = (
        sorted({value for value in timeline_df.get("competition", pd.Series(dtype=str)).dropna().astype(str).map(str.strip) if value})
        if "competition" in timeline_df.columns
        else []
    )
    player_photo_index = _build_player_photo_index(data)
    competition_logo_index = _build_competition_logo_index(known_competitions)
    achievement_reference = _build_achievement_reference_index(data)

    st.markdown(
        """
        <style>
        .timeline-wrap { display:flex; flex-direction:column; gap:1.08rem; margin-top:.5rem; max-width:2100px; width:min(98vw, 2100px); margin-inline:auto; }
        .timeline-season-block { border:1px solid #223246; border-radius:18px; padding:.9rem 1.22rem 1rem 1.22rem; background:linear-gradient(180deg, rgba(10,16,24,.86) 0%, rgba(9,14,22,.98) 100%); }
        .timeline-season-header { display:flex; align-items:baseline; justify-content:space-between; gap:.4rem; border-bottom:1px solid rgba(88,118,150,.4); padding-bottom:.5rem; margin-bottom:.8rem; }
        .timeline-season-title { color:#e5f2ff; font-size:.88rem; font-weight:780; letter-spacing:.08em; text-transform:uppercase; }
        .timeline-season-count { color:#9ab1c8; font-size:.6rem; letter-spacing:.09em; text-transform:uppercase; }
        .timeline-season-flow { position:relative; display:grid; grid-template-columns:repeat(12, minmax(0, 1fr)); row-gap:.58rem; column-gap:.8rem; padding:0 .1rem; }
        .timeline-season-flow::before { content:""; position:absolute; left:50%; transform:translateX(-50%); top:.2rem; bottom:.18rem; width:4px; border-radius:10px; background:linear-gradient(180deg, rgba(122,184,232,.96) 0%, rgba(104,156,206,.68) 34%, rgba(126,105,205,.34) 72%, rgba(76,101,126,.2) 100%); box-shadow:0 0 0 1px rgba(15,29,44,.72), 0 0 22px rgba(92,142,196,.34); }
        .timeline-event-shell { --meta-col:clamp(26px, 2.2vw, 34px); --media-col:clamp(44px, 4vw, 70px); position:relative; min-width:0; width:100%; }
        .timeline-event-shell.lane-left { grid-column:1 / span 6; justify-self:stretch; padding-right:1.35rem; }
        .timeline-event-shell.lane-right { grid-column:7 / span 6; justify-self:stretch; padding-left:1.35rem; margin-top:1.7rem; }
        .timeline-event-shell.width-expanded,
        .timeline-event-shell.width-regular,
        .timeline-event-shell.width-compact { max-width:none; width:100%; }
        .timeline-event-shell.width-expanded { --meta-col:clamp(27px, 2.3vw, 36px); --media-col:clamp(50px, 4.6vw, 80px); }
        .timeline-event-shell.width-compact { --meta-col:clamp(24px, 2vw, 32px); --media-col:clamp(40px, 3.2vw, 60px); }
        .timeline-event-shell::before { content:""; position:absolute; top:1.2rem; height:2px; z-index:1; }
        .timeline-event-shell.lane-left::before { right:-2.08rem; width:2.08rem; background:linear-gradient(90deg, rgba(107,168,227,.14) 0%, rgba(112,165,218,.92) 82%, rgba(123,176,231,.97) 100%); }
        .timeline-event-shell.lane-right::before { left:-2.08rem; width:2.08rem; background:linear-gradient(90deg, rgba(123,176,231,.97) 0%, rgba(112,165,218,.9) 18%, rgba(107,168,227,.14) 100%); }
        .timeline-event-shell::after { content:""; position:absolute; top:.76rem; width:1.02rem; height:.9rem; border-top:2px solid rgba(109,162,217,.5); z-index:1; }
        .timeline-event-shell.lane-left::after { right:-2.18rem; border-right:2px solid rgba(109,162,217,.52); border-top-right-radius:.88rem; }
        .timeline-event-shell.lane-right::after { left:-2.18rem; border-left:2px solid rgba(109,162,217,.52); border-top-left-radius:.88rem; }
        .timeline-event-node { position:absolute; top:.81rem; width:.74rem; height:.74rem; border-radius:999px; border:2px solid #6ea8de; background:#0e1825; box-shadow:0 0 0 3px rgba(20,33,47,.65), 0 0 14px rgba(89,157,223,.34); z-index:2; }
        .timeline-event-shell.lane-left .timeline-event-node { right:-2.53rem; }
        .timeline-event-shell.lane-right .timeline-event-node { left:-2.53rem; }
        .timeline-event-shell.stagger-none { margin-top:.2rem; }
        .timeline-event-shell.stagger-sm { margin-top:1.72rem; }
        .timeline-event-shell.stagger-md { margin-top:3.26rem; }
        .timeline-event-shell.stagger-lg { margin-top:4.9rem; }
        .timeline-event { border:1px solid #3c5670; border-left-width:4px; border-radius:15px; background:
            radial-gradient(145% 92% at 8% -26%, rgba(181, 214, 248, .18) 0%, rgba(181, 214, 248, 0) 52%),
            linear-gradient(167deg, rgba(28,44,63,.98) 0%, rgba(16,27,40,.97) 38%, rgba(10,16,26,.99) 100%);
            box-shadow:0 14px 30px rgba(0,0,0,.4), 0 0 0 1px rgba(134,166,197,.18), inset 0 1px 0 rgba(236,246,255,.1), inset 0 -1px 0 rgba(11,19,30,.65);
            overflow:hidden; position:relative; }
        .timeline-event::before { content:""; position:absolute; inset:0; pointer-events:none; background:linear-gradient(180deg, rgba(235,246,255,.06) 0%, rgba(235,246,255,0) 32%, rgba(7,13,21,.15) 100%); }
        .timeline-event.featured { border-left-width:5px; background:
            radial-gradient(140% 90% at 10% -24%, rgba(250, 220, 155, .22) 0%, rgba(250, 220, 155, 0) 48%),
            linear-gradient(167deg, rgba(32,47,66,.98) 0%, rgba(16,26,40,.98) 40%, rgba(9,16,26,.99) 100%);
            box-shadow:0 18px 36px rgba(0,0,0,.46), 0 0 0 1px rgba(191,214,236,.22), 0 0 26px rgba(152,184,218,.22), inset 0 1px 0 rgba(247,233,199,.16); }
        .timeline-event-grid { display:grid; grid-template-columns:minmax(0, 1fr); gap:.62rem; padding:.68rem .66rem; align-items:start; }
        .timeline-head-top { display:flex; flex-wrap:wrap; gap:.28rem; align-items:center; margin:0 0 .2rem 0; }
        .timeline-date { color:#e8f4ff; font-size:.6rem; letter-spacing:.11em; text-transform:uppercase; font-weight:780; line-height:1.2; }
        .timeline-meta { color:#a7c0d8; font-size:.54rem; letter-spacing:.045em; text-transform:uppercase; line-height:1.15; border:1px solid rgba(91,122,150,.55); background:linear-gradient(180deg, rgba(31,46,64,.78), rgba(18,30,44,.82)); border-radius:999px; padding:.12rem .34rem; width:max-content; max-width:100%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .timeline-main { min-width:0; width:100%; display:grid; grid-template-columns:minmax(0, 1fr) auto; column-gap:.4rem; align-items:flex-start; border:1px solid rgba(92,129,162,.32); border-radius:12px; padding:.34rem .38rem; background:linear-gradient(180deg, rgba(20,33,49,.5), rgba(12,21,33,.3)); box-shadow:inset 0 1px 0 rgba(193,217,241,.08), 0 0 16px rgba(72,126,183,.12); }
        .timeline-main.without-media { grid-template-columns:minmax(0, 1fr); }
        .timeline-copy { min-width:0; width:100%; max-width:none; margin:0; padding:0; flex:1 1 auto; align-self:start; }
        .timeline-head { margin:0 0 .16rem 0; padding-bottom:.2rem; border-bottom:1px solid rgba(118,157,189,.28); }
        .timeline-title { color:#f7fbff; font-size:.9rem; font-weight:770; line-height:1.28; margin:0 0 .14rem 0; max-width:none; text-shadow:0 1px 0 rgba(0,0,0,.35), 0 0 10px rgba(116,176,229,.18); }
        .timeline-title.featured { font-size:.97rem; }
        .timeline-body { background:linear-gradient(180deg, rgba(15,25,38,.44), rgba(13,23,35,.12)); border:1px solid rgba(78,112,143,.26); border-radius:10px; padding:.3rem .38rem; margin:0 0 .18rem 0; }
        .timeline-details { color:#d6e4f2; font-size:.74rem; line-height:1.42; margin:0; max-width:none; }
        .timeline-meta-zone { margin-top:.14rem; display:flex; flex-direction:column; gap:.18rem; }
        .timeline-chips,
        .timeline-badges { display:flex; flex-wrap:wrap; gap:.32rem; margin:.08rem 0 0 0; width:100%; }
        .timeline-chip,
        .timeline-tag { border-radius:999px; font-size:.56rem; letter-spacing:.078em; text-transform:uppercase; color:#f1f8ff; padding:.22rem .6rem; background:linear-gradient(180deg, rgba(60,92,127,.97), rgba(28,48,69,.97)); border:1px solid #79a3cb; box-shadow:inset 0 1px 0 rgba(237,246,255,.23), 0 1px 0 rgba(7,13,21,.72), 0 0 0 1px rgba(8,16,24,.54), 0 0 14px rgba(95,156,214,.24); white-space:nowrap; font-weight:700; }
        .timeline-chip.chip-identity { border-color:rgba(173,203,235,.74); color:#f0f8ff; background:linear-gradient(180deg, rgba(58,84,112,.88), rgba(32,53,75,.94)); }
        .timeline-chip.chip-identity-soft { border-color:rgba(113,147,182,.64); color:#dbeaf9; background:linear-gradient(180deg, rgba(42,64,86,.86), rgba(24,41,60,.92)); }
        .timeline-chip.chip-priority { border-color:rgba(247,208,130,.88); color:#fff3d0; background:linear-gradient(180deg, rgba(97,72,24,.95), rgba(64,46,14,.98)); }
        .timeline-chip.chip-tone { border-color:rgba(151,185,224,.78); color:#eaf5ff; background:linear-gradient(180deg, rgba(44,69,96,.88), rgba(22,42,64,.95)); }
        .timeline-chip.chip-competition { border-color:rgba(130,219,255,.84); color:#e8f9ff; background:linear-gradient(180deg, rgba(30,88,118,.94), rgba(20,62,86,.98)); }
        .timeline-chip.chip-placement { border-color:rgba(251,215,131,.9); color:#fff3d4; background:linear-gradient(180deg, rgba(102,76,26,.93), rgba(72,52,18,.97)); }
        .timeline-chip.chip-result { border-color:rgba(157,231,171,.85); color:#e7ffeb; background:linear-gradient(180deg, rgba(32,91,44,.9), rgba(21,63,30,.95)); }
        .timeline-chip.chip-opponent { border-color:rgba(255,154,196,.82); color:#ffeaf4; background:linear-gradient(180deg, rgba(117,49,87,.9), rgba(82,36,62,.95)); }
        .timeline-chip.chip-movement { border-color:rgba(115,238,224,.85); color:#d9fffa; background:linear-gradient(180deg, rgba(18,81,77,.9), rgba(12,58,55,.95)); }
        .timeline-chip.chip-fee { border-color:rgba(245,196,134,.86); color:#ffeace; background:linear-gradient(180deg, rgba(108,62,24,.93), rgba(74,42,16,.97)); }
        .timeline-chip.chip-ranking { border-color:rgba(194,162,255,.9); color:#f2e8ff; background:linear-gradient(180deg, rgba(73,50,118,.93), rgba(51,36,86,.97)); }
        .timeline-notes { margin-top:.08rem; color:#a9c3dc; font-size:.64rem; line-height:1.37; max-width:none; padding:.18rem .2rem 0 .2rem; border-top:1px dashed rgba(109,145,179,.4); }
        .timeline-media { display:flex; flex-direction:column; gap:.16rem; width:clamp(34px, 2.6vw, 50px); max-width:50px; flex:0 0 auto; }
        .timeline-main.layout-roster .timeline-media,
        .timeline-main.layout-story .timeline-media { width:clamp(36px, 2.9vw, 56px); max-width:56px; }
        .timeline-main.layout-competition .timeline-media { width:clamp(40px, 3.1vw, 62px); max-width:62px; }
        .timeline-media-card { border:1px solid #425d79; border-radius:10px; overflow:hidden; background:linear-gradient(180deg, rgba(14,24,36,.98), rgba(10,18,28,.99)); box-shadow:0 6px 12px rgba(0,0,0,.34), inset 0 1px 0 rgba(217,232,247,.08); }
        .timeline-media-card img { width:100%; height:54px; object-fit:contain; object-position:center; display:block; background:radial-gradient(circle at center, #111f2f 0%, #0b1521 100%); }
        .timeline-media-card .label { display:none !important; }
        .timeline-media.media-2 .timeline-media-card img { height:46px; }
        .timeline-media-caption { color:#7f97af; font-size:.52rem; line-height:1.28; margin-top:-.08rem; }
        .timeline-event-row { display:grid; grid-template-columns:minmax(0, 1fr); gap:.38rem; align-items:stretch; }
        .timeline-event-row.has-event-photo { grid-template-columns:minmax(0, 1fr) clamp(150px, 22%, 220px); }
        .timeline-event-photo-block { border:1px solid #32465c; border-radius:12px; overflow:hidden; background:linear-gradient(160deg, rgba(15,26,39,.96), rgba(9,16,26,.98)); display:flex; flex-direction:column; min-width:0; }
        .timeline-event-photo-block img { width:100%; height:100%; min-height:122px; object-fit:cover; object-position:center; display:block; }
        .timeline-event-photo-caption { color:#9db3c9; font-size:.56rem; line-height:1.3; padding:.34rem .42rem .38rem .42rem; border-top:1px solid rgba(63,88,112,.5); }

        .timeline-event.tone-competition { border-left-color:#e1b457; background:radial-gradient(126% 84% at 8% -18%, rgba(239,192,98,.34) 0%, rgba(239,192,98,0) 50%), linear-gradient(162deg, rgba(49,38,20,.66), rgba(12,20,30,.98) 62%); box-shadow:0 18px 30px rgba(27,18,4,.45), 0 0 0 1px rgba(208,166,89,.25), 0 0 20px rgba(217,164,74,.16); }
        .timeline-event.tone-transfer { border-left-color:#45cfcb; background:radial-gradient(126% 84% at 8% -18%, rgba(82,221,214,.34) 0%, rgba(82,221,214,0) 50%), linear-gradient(162deg, rgba(12,41,40,.66), rgba(12,20,30,.98) 62%); box-shadow:0 18px 30px rgba(4,26,24,.43), 0 0 0 1px rgba(86,200,196,.24), 0 0 20px rgba(71,199,194,.14); }
        .timeline-event.tone-ranking { border-left-color:#b18dff; background:radial-gradient(120% 80% at 8% -18%, rgba(174,138,255,.3) 0%, rgba(174,138,255,0) 48%), linear-gradient(162deg, rgba(36,23,59,.67), rgba(12,20,30,.98) 62%); box-shadow:0 16px 28px rgba(17,9,34,.45), 0 0 0 1px rgba(169,136,244,.22); }
        .timeline-event.tone-organisation { border-left-color:#7bb3ff; background:radial-gradient(120% 80% at 8% -18%, rgba(122,179,255,.3) 0%, rgba(122,179,255,0) 48%), linear-gradient(162deg, rgba(18,35,62,.66), rgba(12,20,30,.98) 62%); box-shadow:0 16px 28px rgba(8,14,34,.43), 0 0 0 1px rgba(125,173,240,.22); }
        .timeline-event.tone-milestone { border-left-color:#88d98a; background:radial-gradient(120% 80% at 8% -18%, rgba(131,214,134,.3) 0%, rgba(131,214,134,0) 48%), linear-gradient(162deg, rgba(18,44,22,.64), rgba(12,20,30,.98) 62%); box-shadow:0 16px 28px rgba(8,26,10,.41), 0 0 0 1px rgba(124,207,128,.2); }
        .timeline-event.tone-general { border-left-color:#96b0ca; background:radial-gradient(120% 80% at 8% -18%, rgba(146,173,204,.26) 0%, rgba(146,173,204,0) 46%), linear-gradient(162deg, rgba(20,33,48,.64), rgba(12,20,30,.98) 62%); }
        .timeline-event-shell.tone-competition .timeline-event-node { border-color:#dfb160; box-shadow:0 0 0 3px rgba(52,35,10,.62), 0 0 14px rgba(217,169,77,.45); }
        .timeline-event-shell.tone-transfer .timeline-event-node { border-color:#49cdc8; box-shadow:0 0 0 3px rgba(10,43,40,.62), 0 0 14px rgba(74,205,200,.43); }
        .timeline-event-shell.tone-ranking .timeline-event-node { border-color:#b295ff; box-shadow:0 0 0 3px rgba(35,20,60,.62), 0 0 14px rgba(161,132,236,.46); }
        .timeline-event-shell.tone-organisation .timeline-event-node { border-color:#7bb1ff; box-shadow:0 0 0 3px rgba(18,28,58,.62), 0 0 14px rgba(123,177,255,.44); }
        .timeline-event-shell.tone-milestone .timeline-event-node { border-color:#86d98d; box-shadow:0 0 0 3px rgba(16,44,21,.62), 0 0 14px rgba(122,201,130,.45); }
        .timeline-event-shell.tone-general .timeline-event-node { border-color:#90abc8; box-shadow:0 0 0 3px rgba(17,32,48,.62), 0 0 14px rgba(130,161,193,.35); }
        .timeline-event.tone-competition .timeline-chip.chip-tone { border-color:rgba(245,203,124,.94); background:linear-gradient(180deg, rgba(118,86,33,.96), rgba(82,60,22,.98)); color:#fff3d8; box-shadow:inset 0 1px 0 rgba(255,233,180,.22), 0 0 12px rgba(219,170,80,.3); }
        .timeline-event.tone-transfer .timeline-chip.chip-tone { border-color:rgba(125,246,236,.92); background:linear-gradient(180deg, rgba(23,99,94,.95), rgba(13,70,67,.98)); color:#ddfffb; box-shadow:inset 0 1px 0 rgba(177,255,244,.2), 0 0 12px rgba(72,207,201,.28); }
        .timeline-event.tone-ranking .timeline-chip.chip-tone { border-color:rgba(198,170,255,.94); background:linear-gradient(180deg, rgba(73,52,121,.95), rgba(52,37,88,.98)); color:#f2eaff; box-shadow:inset 0 1px 0 rgba(227,203,255,.2), 0 0 12px rgba(171,136,245,.28); }
        .timeline-event.tone-organisation .timeline-chip.chip-tone { border-color:rgba(151,201,255,.93); background:linear-gradient(180deg, rgba(34,75,131,.95), rgba(22,56,99,.98)); color:#edf5ff; box-shadow:inset 0 1px 0 rgba(205,226,255,.2), 0 0 12px rgba(117,172,245,.28); }
        .timeline-event.tone-milestone .timeline-chip.chip-tone { border-color:rgba(160,236,165,.93); background:linear-gradient(180deg, rgba(34,100,45,.95), rgba(22,72,32,.98)); color:#eaffec; box-shadow:inset 0 1px 0 rgba(203,255,206,.2), 0 0 12px rgba(116,212,124,.28); }

        @media (max-width: 980px) {
            .timeline-wrap { gap:.84rem; }
            .timeline-season-block { padding:.72rem .72rem .76rem .72rem; }
            .timeline-season-flow { display:flex; flex-direction:column; row-gap:0; padding-left:1.58rem; }
            .timeline-season-flow::before { left:.62rem; transform:none; }
            .timeline-event-shell,
            .timeline-event-shell.width-expanded,
            .timeline-event-shell.width-regular,
            .timeline-event-shell.width-compact { width:100% !important; max-width:100% !important; min-width:0 !important; margin-left:0 !important; margin-right:0 !important; align-self:stretch !important; padding-left:0 !important; padding-right:0 !important; }
            .timeline-event-shell.lane-right { margin-top:.42rem !important; }
            .timeline-event-shell::before { left:-.92rem !important; right:auto !important; width:.92rem !important; background:linear-gradient(90deg, rgba(118,145,170,.72) 0%, rgba(118,145,170,.2) 100%) !important; }
            .timeline-event-shell::after { display:none !important; }
            .timeline-event-node,
            .timeline-event-shell.lane-left .timeline-event-node,
            .timeline-event-shell.lane-right .timeline-event-node { left:-1.28rem; right:auto; top:.82rem; width:.62rem; height:.62rem; }
            .timeline-event-shell.stagger-none,
            .timeline-event-shell.stagger-sm,
            .timeline-event-shell.stagger-md,
            .timeline-event-shell.stagger-lg { margin-top:.42rem !important; }
            .timeline-event-grid { grid-template-columns:1fr; gap:.42rem; padding:.52rem; }
            .timeline-main { display:block; }
            .timeline-event-shell.lane-left .timeline-main,
            .timeline-event-shell.lane-left.width-compact .timeline-main,
            .timeline-event-shell.lane-left.width-expanded .timeline-main { display:block; }
            .timeline-event-shell.lane-left .timeline-copy,
            .timeline-event-shell.lane-left .timeline-media { order:initial; }
            .timeline-rail::after { left:-.18rem; }
            .timeline-media { display:grid; grid-template-columns:repeat(2, minmax(0, 120px)); gap:.3rem; }
            .timeline-event-row,
            .timeline-event-row.has-event-photo { grid-template-columns:1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if filtered.empty:
        st.info("No timeline events match the selected filters.")
        return

    season_order = sorted(
        {_to_int_text(season, fallback="N/A") for season in filtered["season"]},
        key=lambda value: float("-inf") if value == "N/A" else int(value),
        reverse=not ascending,
    )

    timeline_html_parts: list[str] = ["<div class='timeline-wrap'>"]
    for season_key in season_order:
        if season_key == "N/A":
            season_events = filtered[filtered["season"].isna()]
        else:
            season_events = filtered[filtered["season"].map(lambda v: _to_int_text(v, fallback="N/A")) == season_key]
        if season_events.empty:
            continue

        season_html_parts: list[str] = [
            "<div class='timeline-season-block'>",
            "<div class='timeline-season-header'>",
            f"<div class='timeline-season-title'>Season {_safe_html(season_key)}</div>",
            f"<div class='timeline-season-count'>{len(season_events)} events</div>",
            "</div>",
        ]

        season_html_parts.append("<div class='timeline-season-flow'>")

        for event_index, (_, row) in enumerate(season_events.iterrows()):
            date_value = row.get("date")
            date_text = date_value.strftime("%Y-%m-%d") if pd.notna(date_value) else "Date TBD"
            title = _display_value(row.get("title")) or "Untitled event"
            details = _display_value(row.get("details"))
            meta_line = _timeline_meta_line(row)
            notes = _display_value(row.get("notes"))
            highlights = _timeline_highlights(row)
            tone, tone_label = _event_tone(row)
            priority = _event_priority(row)

            _, player_path = _resolve_player_visual(row, player_photo_index)
            _, competition_logo_path, trophy_path = _resolve_tournament_visual(
                row,
                known_competitions,
                competition_logo_index,
                achievement_reference,
            )
            event_photo = _resolve_event_photo(row)
            event_photo_uri = _image_uri_with_fallback(
                event_photo["path"] if event_photo else None,
                max_width=220,
                max_height=220,
            )
            player_uri = _image_uri_with_fallback(player_path, max_width=140, max_height=140)
            competition_uri = _image_uri_with_fallback(competition_logo_path, max_width=140, max_height=140)
            trophy_uri = _image_uri_with_fallback(trophy_path, max_width=140, max_height=140)
            visuals = _visual_priority(row, player_uri, competition_uri, trophy_uri)
            layout_variant = _event_layout_variant(
                row,
                visuals_count=len(visuals),
                highlights_count=len(highlights),
                details=details,
                notes=notes,
                priority=priority,
            )
            media_limit = _event_media_limit(layout_variant)
            if media_limit <= 0:
                visuals = []
            elif len(visuals) > media_limit:
                visuals = visuals[:media_limit]

            chips = _timeline_identity_chips(row, tone_label=tone_label, priority=priority)
            chips.extend(highlights)
            # Keep chip rows focused and avoid visual clutter from excessive bubbles.
            chips = chips[:6]
            should_render_details = _should_render_timeline_details(
                row=row,
                title=title,
                layout_variant=layout_variant,
                details=details,
                notes=notes,
                chips=chips,
                priority=priority,
            )

            meta_html = f"<div class='timeline-meta'>{_safe_html(meta_line)}</div>" if meta_line else ""
            details_html = f"<p class='timeline-details'>{_safe_html(details)}</p>" if should_render_details else ""
            media_html = ""
            if visuals:
                media_cards = "".join(
                    (
                        "<div class='timeline-media-card'>"
                        f"<img src='{uri}' alt='{label} visual' loading='lazy' />"
                        "</div>"
                    )
                    for label, uri in visuals
                )
                media_html = f"<div class='timeline-media media-{len(visuals)}'>{media_cards}</div>"

            chips_html = ""
            if chips:
                chips_html = "".join(
                    f"<span class='timeline-chip chip-{_safe_html(kind)}'>{_safe_html(chip)}</span>"
                    for kind, chip in chips
                )
                chips_html = f"<div class='timeline-chips'>{chips_html}</div>"
            notes_html = f"<div class='timeline-notes'>Notes: {_safe_html(notes)}</div>" if notes else ""
            meta_zone_html = f"<div class='timeline-meta-zone'>{chips_html}{notes_html}</div>" if (chips_html or notes_html) else ""
            details_block_html = f"<div class='timeline-body'>{details_html}</div>" if details_html else ""
            width_class = _event_width_class(
                row,
                visuals_count=len(visuals),
                highlights_count=len(highlights),
                priority=priority,
            )
            lane_class = "lane-right" if event_index % 2 else "lane-left"
            stagger_cycle = ["stagger-none", "stagger-md", "stagger-lg", "stagger-sm"]
            stagger_class = stagger_cycle[event_index % len(stagger_cycle)]
            media_presence_class = "with-media" if media_html else "without-media"
            main_class = f"timeline-main {media_presence_class} layout-{layout_variant}"
            event_photo_html = ""
            if event_photo and event_photo_uri:
                caption = _display_value(event_photo.get("caption"))
                caption_html = (
                    f"<div class='timeline-event-photo-caption'>{_safe_html(caption)}</div>"
                    if caption
                    else ""
                )
                event_photo_html = (
                    "<aside class='timeline-event-photo-block'>"
                    f"<img src='{event_photo_uri}' alt='Event photo for {_safe_html(title)}' loading='lazy' />"
                    f"{caption_html}"
                    "</aside>"
                )
            event_row_class = "timeline-event-row has-event-photo" if event_photo_html else "timeline-event-row"

            title_class = "timeline-title featured" if priority == "featured" else "timeline-title"
            season_html_parts.append(
                (
                    f"<div class='timeline-event-shell {lane_class} {stagger_class} "
                    f"width-{_safe_html(width_class)} tone-{_safe_html(tone)}'>"
                    "<div class='timeline-event-node'></div>"
                    f"<div class='{event_row_class}'>"
                    f"<div class='timeline-event tone-{_safe_html(tone)} {_safe_html(priority)}'>"
                    "<div class='timeline-event-grid'>"
                    f"<div class='{main_class}'>"
                    "<div class='timeline-copy'>"
                    "<div class='timeline-head'>"
                    "<div class='timeline-head-top'>"
                    f"<div class='timeline-date'>{_safe_html(date_text)}</div>"
                    f"{meta_html}"
                    "</div>"
                    f"<div class='{title_class}'>{_safe_html(title)}</div>"
                    "</div>"
                    f"{details_block_html}{meta_zone_html}"
                    "</div>"
                    f"{media_html}"
                    "</div>"
                    "</div>"
                    "</div>"
                    f"{event_photo_html}"
                    "</div>"
                    "</div>"
                )
            )

        season_html_parts.append("</div>")

        season_html_parts.append("</div>")
        timeline_html_parts.append("".join(season_html_parts))
    timeline_html_parts.append("</div>")
    st.markdown("".join(timeline_html_parts), unsafe_allow_html=True)
