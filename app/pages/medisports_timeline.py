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
            "tokens_any": ("bonk",),
            "event_types": ("transfer_in", "transfer_out"),
            "categories": ("roster",),
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
    tokens = [token for token in [event_type, category] if token]
    return " • ".join(tokens)


def _timeline_highlights(row: pd.Series) -> list[str]:
    chips: list[str] = []

    competition = _display_value(row.get("competition"))
    placement = _display_value(row.get("placement"))
    record = _display_value(row.get("record"))
    opponent = _display_value(row.get("opponent_or_org"))
    from_entity = _display_value(row.get("from_entity"))
    to_entity = _display_value(row.get("to_entity"))
    fee_text = _to_int_text(row.get("fee_cpl"))
    rank_from = _to_int_text(row.get("ranking_from"))
    rank_to = _to_int_text(row.get("ranking_to"))

    if competition:
        chips.append(f"Competition: {competition}")
    if placement:
        chips.append(f"Placement: {placement}")
    if record:
        chips.append(f"Record: {record}")
    if opponent:
        chips.append(f"Org/Opponent: {opponent}")
    if from_entity or to_entity:
        flow = " → ".join([part for part in [from_entity, to_entity] if part])
        if flow:
            chips.append(f"Movement: {flow}")
    if fee_text:
        chips.append(f"Fee: {fee_text} CPL")
    if rank_from or rank_to:
        rank_flow = " → ".join([part for part in [rank_from, rank_to] if part])
        if rank_flow:
            chips.append(f"Ranking: {rank_flow}")
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

    haystack = _text_for_entity_detection(row)

    for key, path in player_photo_index.items():
        if not key:
            continue
        normalized_key = _normalize_for_match(key)
        if normalized_key and f" {normalized_key} " in haystack:
            return key, path
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


def _keyword_overlap_score(left: str, right: str) -> int:
    left_tokens = {token for token in left.split() if token and len(token) > 2}
    right_tokens = {token for token in right.split() if token and len(token) > 2}
    overlap = len(left_tokens & right_tokens)
    if overlap >= 3:
        return 5
    if overlap == 2:
        return 4
    if overlap == 1:
        return 1
    return 0


def _resolve_trophy_from_achievement_reference(
    row: pd.Series,
    competition: str,
    placement: str,
    achievement_reference: list[dict[str, object]],
) -> str | None:
    if not achievement_reference or not _is_trophy_relevant_row(row):
        return None

    row_title_blob = _normalize_for_match(
        " ".join(_display_value(row.get(field)) for field in ["title", "details", "competition", "notes"])
    )
    competition_norm = _normalize_for_match(competition)
    placement_rank = _placement_rank_text(placement)
    timeline_season = _to_int_text(row.get("season"))

    best: tuple[int, int, str] | None = None
    for record in achievement_reference:
        name_norm = str(record.get("name_norm") or "")
        if not name_norm:
            continue

        score = 0
        if competition_norm:
            if competition_norm == name_norm:
                score += 9
            elif competition_norm in name_norm or name_norm in competition_norm:
                score += 7
            score += _keyword_overlap_score(competition_norm, name_norm)
        if row_title_blob and (name_norm in row_title_blob or row_title_blob in name_norm):
            score += 3

        record_placement = str(record.get("placement_rank") or "")
        if placement_rank and record_placement:
            if placement_rank == record_placement:
                score += 4
            else:
                score -= 5
        elif placement_rank and not record_placement:
            score -= 2

        record_season = str(record.get("season_text") or "")
        if timeline_season and record_season and timeline_season == record_season:
            score += 1

        if score < 8:
            continue

        image_path = str(record.get("image_path") or "")
        if not image_path:
            continue

        specificity = len(name_norm)
        candidate = (score, specificity, image_path)
        if best is None or candidate > best:
            best = candidate

    return best[2] if best else None


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

    if not competition_text:
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
        placement_rank = _placement_rank_text(placement_text)
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

        path = photos_dir / override["asset"]
        if not path.exists() or not path.is_file():
            continue

        return {
            "label": override["label"],
            "caption": override["caption"],
            "path": str(path),
        }
    return None




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
    event_photo_visual: tuple[str, str] | None,
    player_image_uri: str | None,
    competition_image_uri: str | None,
    trophy_image_uri: str | None,
) -> list[tuple[str, str]]:
    if event_photo_visual:
        return [event_photo_visual]

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

    filter_cols = st.columns(4, gap="small")
    selected_seasons = filter_cols[0].multiselect("Season", options=seasons, default=[])
    selected_event_types = filter_cols[1].multiselect("Event Type", options=event_types, default=[])
    selected_categories = filter_cols[2].multiselect("Category", options=categories, default=[])
    sort_order = filter_cols[3].segmented_control("Order", ["Newest first", "Oldest first"], default="Newest first")

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
        .timeline-wrap { display:flex; flex-direction:column; gap:1rem; margin-top:.45rem; max-width:2100px; width:min(98vw, 2100px); margin-inline:auto; }
        .timeline-season-block { border:1px solid #223246; border-radius:18px; padding:.8rem 1.15rem .9rem 1.15rem; background:linear-gradient(180deg, rgba(10,16,24,.86) 0%, rgba(9,14,22,.98) 100%); }
        .timeline-season-header { display:flex; align-items:baseline; justify-content:space-between; gap:.4rem; border-bottom:1px solid rgba(81,106,132,.35); padding-bottom:.42rem; margin-bottom:.68rem; }
        .timeline-season-title { color:#e5f2ff; font-size:.88rem; font-weight:780; letter-spacing:.08em; text-transform:uppercase; }
        .timeline-season-count { color:#9ab1c8; font-size:.6rem; letter-spacing:.09em; text-transform:uppercase; }
        .timeline-season-flow { position:relative; display:grid; grid-template-columns:repeat(12, minmax(0, 1fr)); row-gap:.44rem; column-gap:.72rem; padding:0 .08rem; }
        .timeline-season-flow::before { content:""; position:absolute; left:50%; transform:translateX(-50%); top:.2rem; bottom:.18rem; width:4px; border-radius:10px; background:linear-gradient(180deg, rgba(118,152,184,.95) 0%, rgba(97,129,159,.58) 36%, rgba(76,101,126,.24) 100%); box-shadow:0 0 0 1px rgba(15,29,44,.72), 0 0 20px rgba(86,116,145,.28); }
        .timeline-event-shell { --meta-col:clamp(26px, 2.2vw, 34px); --media-col:clamp(44px, 4vw, 70px); position:relative; min-width:0; width:100%; }
        .timeline-event-shell.lane-left { grid-column:1 / span 6; justify-self:stretch; padding-right:1.35rem; }
        .timeline-event-shell.lane-right { grid-column:7 / span 6; justify-self:stretch; padding-left:1.35rem; margin-top:1.7rem; }
        .timeline-event-shell.width-expanded,
        .timeline-event-shell.width-regular,
        .timeline-event-shell.width-compact { max-width:none; width:100%; }
        .timeline-event-shell.width-expanded { --meta-col:clamp(27px, 2.3vw, 36px); --media-col:clamp(50px, 4.6vw, 80px); }
        .timeline-event-shell.width-compact { --meta-col:clamp(24px, 2vw, 32px); --media-col:clamp(40px, 3.2vw, 60px); }
        .timeline-event-shell::before { content:""; position:absolute; top:1.2rem; height:2px; z-index:1; }
        .timeline-event-shell.lane-left::before { right:-2.08rem; width:2.08rem; background:linear-gradient(90deg, rgba(118,145,170,.15) 0%, rgba(118,145,170,.9) 85%, rgba(118,145,170,.95) 100%); }
        .timeline-event-shell.lane-right::before { left:-2.08rem; width:2.08rem; background:linear-gradient(90deg, rgba(118,145,170,.95) 0%, rgba(118,145,170,.86) 18%, rgba(118,145,170,.16) 100%); }
        .timeline-event-shell::after { content:""; position:absolute; top:.76rem; width:1.02rem; height:.9rem; border-top:2px solid rgba(118,145,170,.42); z-index:1; }
        .timeline-event-shell.lane-left::after { right:-2.18rem; border-right:2px solid rgba(118,145,170,.45); border-top-right-radius:.88rem; }
        .timeline-event-shell.lane-right::after { left:-2.18rem; border-left:2px solid rgba(118,145,170,.45); border-top-left-radius:.88rem; }
        .timeline-event-node { position:absolute; top:.81rem; width:.74rem; height:.74rem; border-radius:999px; border:2px solid #6685a5; background:#0e1825; box-shadow:0 0 0 3px rgba(20,33,47,.65); z-index:2; }
        .timeline-event-shell.lane-left .timeline-event-node { right:-2.53rem; }
        .timeline-event-shell.lane-right .timeline-event-node { left:-2.53rem; }
        .timeline-event-shell.stagger-none { margin-top:.2rem; }
        .timeline-event-shell.stagger-sm { margin-top:1.6rem; }
        .timeline-event-shell.stagger-md { margin-top:3.1rem; }
        .timeline-event-shell.stagger-lg { margin-top:4.6rem; }
        .timeline-event { border:1px solid #2b3b4e; border-left-width:3px; border-radius:14px; background:linear-gradient(165deg, rgba(19,28,40,.9) 0%, rgba(12,19,28,.98) 58%); box-shadow:0 8px 18px rgba(0,0,0,.22); overflow:hidden; }
        .timeline-event.featured { border-left-width:4px; box-shadow:0 12px 24px rgba(0,0,0,.28); }
        .timeline-event-grid { display:grid; grid-template-columns:minmax(24px, var(--meta-col)) minmax(0, 1fr); gap:.48rem; padding:.5rem .48rem; }
        .timeline-rail { border-right:1px solid rgba(95,121,146,.3); padding-right:.14rem; display:flex; flex-direction:column; gap:.14rem; }
        .timeline-date { color:#e8f4ff; font-size:.6rem; letter-spacing:.11em; text-transform:uppercase; font-weight:780; line-height:1.2; }
        .timeline-meta { color:#88a2ba; font-size:.55rem; letter-spacing:.08em; text-transform:uppercase; line-height:1.25; }
        .timeline-badges { display:flex; flex-direction:column; align-items:flex-start; gap:.22rem; }
        .timeline-tag { font-size:.52rem; letter-spacing:.09em; text-transform:uppercase; border-radius:999px; padding:.12rem .36rem; border:1px solid rgba(152,176,199,.36); color:#c5dbf1; }
        .timeline-main { min-width:0; width:100%; display:flex; gap:.34rem; align-items:flex-start; justify-content:space-between; }
        .timeline-main.without-media { display:block; }
        .timeline-event-shell.lane-left .timeline-copy { order:2; }
        .timeline-event-shell.lane-left .timeline-media { order:1; }
        .timeline-copy { min-width:0; width:100%; max-width:none; margin:0; padding:0; flex:1 1 auto; align-self:start; }
        .timeline-title { color:#f2f8ff; font-size:.89rem; font-weight:760; line-height:1.26; margin:0 0 .1rem 0; max-width:none; }
        .timeline-title.featured { font-size:.97rem; }
        .timeline-details { color:#c9d8e8; font-size:.73rem; line-height:1.37; margin:0 0 .12rem 0; max-width:none; }
        .timeline-chips { display:flex; flex-wrap:wrap; gap:.2rem; margin:0; width:100%; }
        .timeline-chip { border-radius:6px; font-size:.52rem; letter-spacing:.085em; text-transform:uppercase; color:#d3e4f6; padding:.12rem .32rem; background:#132233; border:1px solid #36506a; }
        .timeline-notes { margin-top:.12rem; color:#90a9c1; font-size:.64rem; line-height:1.32; max-width:none; }
        .timeline-media { display:flex; flex-direction:column; gap:.16rem; width:clamp(42px, 4.4vw, 80px); max-width:100%; flex:0 0 auto; }
        .timeline-main.layout-roster .timeline-media,
        .timeline-main.layout-story .timeline-media { width:clamp(50px, 4.8vw, 82px); }
        .timeline-main.layout-competition .timeline-media { width:clamp(54px, 5.2vw, 88px); }
        .timeline-media-card { border:1px solid #32465c; border-radius:9px; overflow:hidden; background:#0d1724; }
        .timeline-media-card img { width:100%; height:62px; object-fit:contain; object-position:center; display:block; background:radial-gradient(circle at center, #111f2f 0%, #0b1521 100%); }
        .timeline-media.media-2 .timeline-media-card img { height:54px; }
        .timeline-media-card .label { color:#90a9c1; font-size:.48rem; letter-spacing:.1em; text-transform:uppercase; text-align:center; padding:.1rem .16rem; border-top:1px solid #293d53; }
        .timeline-media-caption { color:#7f97af; font-size:.52rem; line-height:1.28; margin-top:-.08rem; }

        .timeline-event.tone-competition { border-left-color:#b89248; background:linear-gradient(162deg, rgba(184,146,72,.18), rgba(12,19,28,.98) 58%); }
        .timeline-event.tone-transfer { border-left-color:#3f9b99; background:linear-gradient(162deg, rgba(63,155,153,.18), rgba(12,19,28,.98) 58%); }
        .timeline-event.tone-ranking { border-left-color:#7f63b8; background:linear-gradient(162deg, rgba(127,99,184,.18), rgba(12,19,28,.98) 58%); }
        .timeline-event.tone-organisation { border-left-color:#4d79bd; background:linear-gradient(162deg, rgba(77,121,189,.18), rgba(12,19,28,.98) 58%); }
        .timeline-event.tone-milestone { border-left-color:#5c9d62; background:linear-gradient(162deg, rgba(92,157,98,.18), rgba(12,19,28,.98) 58%); }
        .timeline-event.tone-general { border-left-color:#5f738a; background:linear-gradient(162deg, rgba(95,115,138,.18), rgba(12,19,28,.98) 58%); }
        .timeline-event-shell.tone-competition .timeline-event-node { border-color:#c49d54; }
        .timeline-event-shell.tone-transfer .timeline-event-node { border-color:#4cb6b2; }
        .timeline-event-shell.tone-ranking .timeline-event-node { border-color:#9276ce; }
        .timeline-event-shell.tone-organisation .timeline-event-node { border-color:#6995db; }
        .timeline-event-shell.tone-milestone .timeline-event-node { border-color:#72bb79; }

        .timeline-event.tone-competition .timeline-tag { color:#f1deb8; border-color:rgba(184,146,72,.45); background:rgba(184,146,72,.12); }
        .timeline-event.tone-transfer .timeline-tag { color:#b9ece9; border-color:rgba(63,155,153,.45); background:rgba(63,155,153,.14); }
        .timeline-event.tone-ranking .timeline-tag { color:#d8c8ff; border-color:rgba(127,99,184,.44); background:rgba(127,99,184,.15); }
        .timeline-event.tone-organisation .timeline-tag { color:#cce0ff; border-color:rgba(77,121,189,.45); background:rgba(77,121,189,.14); }
        .timeline-event.tone-milestone .timeline-tag { color:#d5f0d8; border-color:rgba(92,157,98,.42); background:rgba(92,157,98,.15); }
        .timeline-event.tone-general .timeline-tag { color:#d2deea; border-color:rgba(95,115,138,.42); background:rgba(95,115,138,.13); }

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
            .timeline-rail { border-right:none; border-bottom:1px solid rgba(95,121,146,.3); padding-right:0; padding-bottom:.34rem; }
            .timeline-badges { flex-direction:row; flex-wrap:wrap; gap:.24rem; }
            .timeline-main { display:block; }
            .timeline-event-shell.lane-left .timeline-main,
            .timeline-event-shell.lane-left.width-compact .timeline-main,
            .timeline-event-shell.lane-left.width-expanded .timeline-main { display:block; }
            .timeline-event-shell.lane-left .timeline-copy,
            .timeline-event-shell.lane-left .timeline-media { order:initial; }
            .timeline-media { display:grid; grid-template-columns:repeat(2, minmax(0, 120px)); gap:.3rem; }
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
            event_override = _resolve_event_photo_override(row)
            event_photo_uri = _image_uri_with_fallback(
                event_override["path"] if event_override else None,
                max_width=220,
                max_height=220,
            )
            player_uri = _image_uri_with_fallback(player_path, max_width=140, max_height=140)
            competition_uri = _image_uri_with_fallback(competition_logo_path, max_width=140, max_height=140)
            trophy_uri = _image_uri_with_fallback(trophy_path, max_width=140, max_height=140)
            event_visual = (event_override["label"], event_photo_uri) if event_photo_uri and event_override else None
            visuals = _visual_priority(row, event_visual, player_uri, competition_uri, trophy_uri)
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

            meta_html = f"<div class='timeline-meta'>{_safe_html(meta_line)}</div>" if meta_line else ""
            details_html = f"<p class='timeline-details'>{_safe_html(details)}</p>" if details else ""
            media_html = ""
            if visuals:
                media_cards = "".join(
                    (
                        "<div class='timeline-media-card'>"
                        f"<img src='{uri}' alt='{label} visual' loading='lazy' />"
                        f"<div class='label'>{label}</div>"
                        "</div>"
                    )
                    for label, uri in visuals
                )
                caption_html = ""
                if event_override and event_photo_uri:
                    caption_html = f"<div class='timeline-media-caption'>{_safe_html(event_override['caption'])}</div>"
                media_html = f"<div class='timeline-media media-{len(visuals)}'>{media_cards}{caption_html}</div>"

            chips_html = ""
            if highlights:
                chips_html = "".join(f"<span class='timeline-chip'>{_safe_html(chip)}</span>" for chip in highlights)
                chips_html = f"<div class='timeline-chips'>{chips_html}</div>"
            notes_html = f"<div class='timeline-notes'>Notes: {_safe_html(notes)}</div>" if notes else ""
            footer_html = f"{chips_html}{notes_html}" if (chips_html or notes_html) else ""
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

            title_class = "timeline-title featured" if priority == "featured" else "timeline-title"
            season_html_parts.append(
                (
                    f"<div class='timeline-event-shell {lane_class} {stagger_class} "
                    f"width-{_safe_html(width_class)} tone-{_safe_html(tone)}'>"
                    "<div class='timeline-event-node'></div>"
                    f"<div class='timeline-event tone-{_safe_html(tone)} {_safe_html(priority)}'>"
                    "<div class='timeline-event-grid'>"
                    "<div class='timeline-rail'>"
                    f"<div class='timeline-date'>{_safe_html(date_text)}</div>"
                    f"{meta_html}"
                    "<div class='timeline-badges'>"
                    f"<span class='timeline-tag'>{_safe_html(tone_label)}</span>"
                    f"<span class='timeline-tag'>{_safe_html('Major' if priority == 'featured' else 'Standard')}</span>"
                    "</div>"
                    "</div>"
                    f"<div class='{main_class}'>"
                    "<div class='timeline-copy'>"
                    f"<div class='{title_class}'>{_safe_html(title)}</div>"
                    f"{details_html}{footer_html}"
                    "</div>"
                    f"{media_html}"
                    "</div>"
                    "</div>"
                    "</div>"
                    "</div>"
                )
            )

        season_html_parts.append("</div>")

        season_html_parts.append("</div>")
        timeline_html_parts.append("".join(season_html_parts))
    timeline_html_parts.append("</div>")
    st.markdown("".join(timeline_html_parts), unsafe_allow_html=True)
