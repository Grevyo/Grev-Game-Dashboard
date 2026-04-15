import html
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
    filtered = filtered.sort_values(["date_sort", "season", "title"], ascending=[ascending, ascending, True], na_position="last")
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
        :root {
            --timeline-spine-rgb: 96, 152, 231;
            --timeline-spine-main: rgb(var(--timeline-spine-rgb));
            --timeline-spine-soft: rgba(var(--timeline-spine-rgb), .3);
            --timeline-spine-glow: rgba(var(--timeline-spine-rgb), .22);
        }
        .timeline-wrap { display:flex; flex-direction:column; gap:1.02rem; margin-top:.5rem; }
        .timeline-season-block { position:relative; margin-bottom:.2rem; padding:.9rem .84rem .68rem .84rem; border:1px solid #213042; border-radius:18px; background:linear-gradient(180deg, rgba(10,17,27,.82) 0%, rgba(9,14,22,.96) 100%); }
        .timeline-season-block::before { content:""; position:absolute; left:1.15rem; right:1.15rem; top:0; height:2px; border-radius:999px; background:linear-gradient(90deg, rgba(160,190,220,.06), rgba(160,190,220,.28), rgba(160,190,220,.06)); }
        .timeline-season-block::after { content:""; position:absolute; left:1.2rem; right:1.2rem; top:66px; border-top:1px dashed rgba(117,146,172,.26); }
        .timeline-season-header { display:flex; justify-content:space-between; align-items:center; gap:.5rem; margin-bottom:.74rem; padding:.1rem .16rem .54rem .16rem; border-bottom:1px solid #223446; }
        .timeline-season-title { color:#e1eefc; font-size:.92rem; font-weight:780; letter-spacing:.08em; text-transform:uppercase; }
        .timeline-season-count { color:#89a0b7; font-size:.62rem; letter-spacing:.1em; text-transform:uppercase; }
        .timeline-season-lanes { display:flex; flex-direction:column; gap:.62rem; position:relative; }
        .timeline-lane-row { position:relative; display:flex; flex-wrap:wrap; gap:.74rem .78rem; align-items:flex-start; align-content:flex-start; padding:0 .16rem; }
        .timeline-lane-row.dir-rtl { direction:rtl; }
        .timeline-lane-row.dir-rtl .timeline-event { direction:ltr; }
        .timeline-lane-row::before {
            content:"";
            position:absolute;
            left:.65rem;
            right:.65rem;
            top:23px;
            height:4px;
            border-radius:999px;
            background:linear-gradient(90deg, rgba(var(--timeline-spine-rgb), .38) 0%, rgba(var(--timeline-spine-rgb), .78) 28%, rgba(var(--timeline-spine-rgb), .78) 72%, rgba(var(--timeline-spine-rgb), .38) 100%);
            box-shadow:0 0 0 1px rgba(var(--timeline-spine-rgb), .16), 0 0 18px rgba(var(--timeline-spine-rgb), .26);
            pointer-events:none;
        }
        .timeline-bend { position:relative; height:24px; margin:-.12rem 0 .06rem 0; }
        .timeline-bend::before {
            content:"";
            position:absolute;
            top:0;
            bottom:0;
            width:30px;
            border:3px solid rgba(var(--timeline-spine-rgb), .7);
            border-top:none;
            filter:drop-shadow(0 0 8px rgba(var(--timeline-spine-rgb), .34));
        }
        .timeline-bend::after { content:"↓"; position:absolute; top:6px; color:#d9ecff; font-size:.68rem; font-weight:700; width:18px; height:18px; border-radius:999px; border:2px solid rgba(var(--timeline-spine-rgb), .72); background:rgba(10,20,33,.98); box-shadow:0 0 0 2px rgba(var(--timeline-spine-rgb), .22), 0 0 14px rgba(var(--timeline-spine-rgb), .28); display:flex; align-items:center; justify-content:center; }
        .timeline-bend.to-right::before { right:.45rem; border-left:none; border-bottom-right-radius:18px; }
        .timeline-bend.to-right::after { right:.28rem; }
        .timeline-bend.to-left::before { left:.45rem; border-right:none; border-bottom-left-radius:18px; }
        .timeline-bend.to-left::after { left:.28rem; }
        .timeline-event {
            position:relative;
            min-width:min(100%, 210px);
            max-width:100%;
            flex:1 1 290px;
            align-self:start;
            height:auto;
            display:flex;
            flex-direction:column;
        }
        .timeline-event::after {
            content:"";
            position:absolute;
            top:21px;
            width:14px;
            border-top:3px solid rgba(var(--timeline-spine-rgb), .74);
            box-shadow:0 0 8px rgba(var(--timeline-spine-rgb), .26);
            z-index:3;
            pointer-events:none;
        }
        .timeline-lane-row.dir-ltr .timeline-event::after { right:-.72rem; }
        .timeline-lane-row.dir-rtl .timeline-event::after { left:-.72rem; }
        .timeline-lane-row.dir-ltr .timeline-event:last-child::after,
        .timeline-lane-row.dir-rtl .timeline-event:last-child::after { display:none; }
        .timeline-event.compact { flex:0.8 1 220px; }
        .timeline-event.regular { flex:1 1 290px; }
        .timeline-event.expanded { flex:1.25 1 360px; }
        .timeline-event.featured { flex:1.45 1 430px; }
        .timeline-event.featured .timeline-item { border-left-width:3px; box-shadow:0 14px 28px rgba(0, 0, 0, .34); }
        .timeline-track { display:flex; align-items:center; gap:.42rem; padding:.01rem .14rem .3rem .14rem; }
        .timeline-track::after {
            content:"";
            flex:1;
            height:4px;
            border-radius:999px;
            background:linear-gradient(90deg, rgba(var(--timeline-spine-rgb), .35), rgba(var(--timeline-spine-rgb), .82));
            box-shadow:0 0 0 1px rgba(var(--timeline-spine-rgb), .16), 0 0 12px rgba(var(--timeline-spine-rgb), .25);
        }
        .timeline-anchor-index { color:#90a8c1; font-size:.52rem; letter-spacing:.09em; text-transform:uppercase; border:1px solid rgba(104,130,156,.32); border-radius:999px; padding:.13rem .35rem; background:rgba(11,20,30,.92); }
        .timeline-node {
            width:16px;
            height:16px;
            border-radius:50%;
            border:3px solid rgba(var(--timeline-spine-rgb), .88);
            background:radial-gradient(circle, rgba(224,239,255,.98) 0%, rgba(157,194,238,.96) 44%, rgba(20,34,52,.99) 100%);
            box-shadow:0 0 0 4px rgba(var(--timeline-spine-rgb), .2), 0 0 16px rgba(var(--timeline-spine-rgb), .34);
        }
        .timeline-node-date { color:#b7cee4; font-size:.54rem; letter-spacing:.1em; text-transform:uppercase; background:rgba(13,24,35,.76); border:1px solid rgba(95,124,151,.33); border-radius:999px; padding:.16rem .46rem; white-space:nowrap; }
        .timeline-event.featured .timeline-node { width:20px; height:20px; border-width:3px; box-shadow:0 0 0 5px rgba(189,153,75,.15), 0 0 16px rgba(189,153,75,.32); }
        .timeline-event.featured .timeline-node-date { color:#f4dfb8; border-color:rgba(184,146,72,.55); }
        .timeline-item { border:1px solid #2a3848; border-radius:16px; padding:.54rem .62rem .5rem .62rem; background:linear-gradient(180deg, #111a26 0%, #0d141d 100%); box-shadow:0 8px 18px rgba(0, 0, 0, .2); border-left-width:3px; overflow:hidden; width:100%; height:auto; align-self:start; }
        .timeline-item::before { content:""; display:block; height:2px; margin:-.54rem -.62rem .38rem -.62rem; background:linear-gradient(90deg, rgba(160,190,220,.02), rgba(160,190,220,.33), rgba(160,190,220,.02)); }
        .timeline-item.featured { padding:.62rem .72rem .56rem .72rem; border-width:1px; border-left-width:4px; box-shadow:0 12px 26px rgba(0, 0, 0, .3); }
        .timeline-item.featured::before { margin:-.62rem -.72rem .44rem -.72rem; height:3px; }
        .timeline-content { display:flex; gap:.48rem; align-items:flex-start; justify-content:space-between; }
        .timeline-main { flex:1 1 auto; min-width:0; }
        .timeline-head { display:flex; flex-wrap:wrap; align-items:center; gap:.28rem .44rem; justify-content:space-between; }
        .timeline-date { color:#e8f4ff; font-size:.7rem; letter-spacing:.11em; text-transform:uppercase; font-weight:780; padding:.14rem .4rem; border:1px solid rgba(160,185,210,.3); border-radius:999px; background:rgba(16,27,39,.58); }
        .timeline-badges { display:flex; flex-wrap:wrap; gap:.3rem; justify-content:flex-end; }
        .timeline-tag { font-size:.58rem; letter-spacing:.11em; text-transform:uppercase; border-radius:999px; padding:.16rem .42rem; border:1px solid rgba(152,176,199,.34); color:#bdd4ea; }
        .timeline-title { color:#f2f8ff; font-size:.91rem; font-weight:760; margin:.22rem 0 .1rem 0; line-height:1.23; }
        .timeline-title.featured { font-size:1.02rem; }
        .timeline-meta { color:#9cb0c5; font-size:.63rem; margin-bottom:.14rem; letter-spacing:.065em; text-transform:uppercase; }
        .timeline-details { color:#c9d8e8; font-size:.78rem; line-height:1.4; margin:0 0 .2rem 0; }
        .timeline-footer { border-top:1px solid rgba(85,108,130,.22); margin-top:.2rem; padding-top:.2rem; }
        .timeline-chips { display:flex; flex-wrap:wrap; gap:.24rem; margin-top:.05rem; }
        .timeline-chip { border-radius:5px; font-size:.57rem; letter-spacing:.09em; text-transform:uppercase; color:#d0e2f5; padding:.16rem .36rem; background:#132131; border:1px solid #36516b; }
        .timeline-notes { margin-top:.18rem; color:#8ea9c1; font-size:.68rem; line-height:1.34; }
        .timeline-media {
            display:flex;
            flex-direction:column;
            gap:.22rem;
            min-width:78px;
            max-width:110px;
            flex:0 1 30%;
            justify-content:flex-start;
            align-content:flex-start;
            align-self:start;
        }
        .timeline-media-card { width:100%; border:1px solid #2f4255; border-radius:10px; overflow:hidden; background:#0c1420; }
        .timeline-media-card img { width:100%; height:52px; object-fit:contain; object-position:center; display:block; background:radial-gradient(circle at center, #0f1d2b 0%, #09121c 100%); }
        .timeline-media.media-2 .timeline-media-card img { height:48px; }
        .timeline-media.media-3 .timeline-media-card img { height:42px; }
        .timeline-event.featured .timeline-media.media-1 .timeline-media-card img { height:56px; }
        .timeline-event.compact .timeline-content { gap:.4rem; }
        .timeline-event.compact .timeline-media { min-width:68px; max-width:88px; }
        .timeline-event.compact .timeline-media-card img { height:44px; }
        .timeline-event.expanded .timeline-media { min-width:88px; max-width:124px; }
        .timeline-event.expanded .timeline-media-card img { height:58px; }
        .timeline-event.featured .timeline-media { min-width:96px; max-width:132px; }
        .timeline-event.featured .timeline-media-card img { height:60px; }
        .timeline-media-card .label { color:#8ea8be; font-size:.49rem; letter-spacing:.11em; text-transform:uppercase; text-align:center; padding:.12rem .18rem; border-top:1px solid #23384e; }
        .timeline-item.tone-competition { border-left-color:#b89248; background:linear-gradient(162deg, rgba(184,146,72,.16), rgba(13,20,29,.95) 42%); }
        .timeline-item.tone-transfer { border-left-color:#3f9b99; background:linear-gradient(162deg, rgba(63,155,153,.16), rgba(13,20,29,.95) 42%); }
        .timeline-item.tone-ranking { border-left-color:#7f63b8; background:linear-gradient(162deg, rgba(127,99,184,.16), rgba(13,20,29,.95) 42%); }
        .timeline-item.tone-organisation { border-left-color:#4d79bd; background:linear-gradient(162deg, rgba(77,121,189,.16), rgba(13,20,29,.95) 42%); }
        .timeline-item.tone-milestone { border-left-color:#5c9d62; background:linear-gradient(162deg, rgba(92,157,98,.16), rgba(13,20,29,.95) 42%); }
        .timeline-item.tone-general { border-left-color:#5f738a; background:linear-gradient(162deg, rgba(95,115,138,.16), rgba(13,20,29,.95) 42%); }
        .timeline-item.tone-competition .timeline-tag { color:#f1deb8; border-color:rgba(184,146,72,.45); background:rgba(184,146,72,.12); }
        .timeline-item.tone-transfer .timeline-tag { color:#b9ece9; border-color:rgba(63,155,153,.45); background:rgba(63,155,153,.14); }
        .timeline-item.tone-ranking .timeline-tag { color:#d8c8ff; border-color:rgba(127,99,184,.44); background:rgba(127,99,184,.15); }
        .timeline-item.tone-organisation .timeline-tag { color:#cce0ff; border-color:rgba(77,121,189,.45); background:rgba(77,121,189,.14); }
        .timeline-item.tone-milestone .timeline-tag { color:#d5f0d8; border-color:rgba(92,157,98,.42); background:rgba(92,157,98,.15); }
        .timeline-item.tone-general .timeline-tag { color:#d2deea; border-color:rgba(95,115,138,.42); background:rgba(95,115,138,.13); }
        .timeline-item.tone-competition::before { background:linear-gradient(90deg, rgba(184,146,72,.08), rgba(184,146,72,.55), rgba(184,146,72,.08)); }
        .timeline-item.tone-transfer::before { background:linear-gradient(90deg, rgba(63,155,153,.08), rgba(63,155,153,.55), rgba(63,155,153,.08)); }
        .timeline-item.tone-ranking::before { background:linear-gradient(90deg, rgba(127,99,184,.08), rgba(127,99,184,.55), rgba(127,99,184,.08)); }
        .timeline-item.tone-organisation::before { background:linear-gradient(90deg, rgba(77,121,189,.08), rgba(77,121,189,.55), rgba(77,121,189,.08)); }
        .timeline-item.tone-milestone::before { background:linear-gradient(90deg, rgba(92,157,98,.08), rgba(92,157,98,.55), rgba(92,157,98,.08)); }
        .timeline-item.tone-general::before { background:linear-gradient(90deg, rgba(95,115,138,.08), rgba(95,115,138,.55), rgba(95,115,138,.08)); }
        @media (max-width: 1280px) {
            .timeline-lane-row { gap:.66rem .66rem; }
            .timeline-lane-row::before { left:.6rem; right:.6rem; top:22px; height:3px; }
            .timeline-event { flex:1 1 260px; min-width:min(100%, 200px); }
            .timeline-event.compact { flex:0.9 1 220px; }
            .timeline-event.expanded { flex:1.2 1 320px; }
            .timeline-event.featured { flex:1.35 1 360px; }
        }
        @media (max-width: 960px) {
            .timeline-wrap { gap:.86rem; }
            .timeline-season-block { padding:.74rem .68rem .56rem .68rem; border-radius:16px; }
            .timeline-season-header { margin-bottom:.58rem; padding:.08rem .1rem .42rem .1rem; }
            .timeline-season-lanes { gap:.48rem; padding-left:.3rem; }
            .timeline-lane-row {
                display:flex;
                flex-direction:column;
                gap:.54rem;
                padding:0 .06rem 0 .38rem;
            }
            .timeline-lane-row.dir-rtl { direction:ltr; }
            .timeline-lane-row::before {
                left:9px;
                right:auto;
                top:0;
                bottom:0;
                width:4px;
                height:auto;
                border-radius:999px;
                background:linear-gradient(180deg, rgba(var(--timeline-spine-rgb), .82), rgba(var(--timeline-spine-rgb), .46));
                box-shadow:0 0 0 1px rgba(var(--timeline-spine-rgb), .2), 0 0 14px rgba(var(--timeline-spine-rgb), .26);
            }
            .timeline-bend { display:none; }
            .timeline-event::after {
                top:22px;
                left:-.12rem;
                width:12px;
                border-top-width:3px;
                border-top-color:rgba(var(--timeline-spine-rgb), .74);
            }
            .timeline-lane-row.dir-ltr .timeline-event::after,
            .timeline-lane-row.dir-rtl .timeline-event::after { left:-.12rem; right:auto; }
            .timeline-event,
            .timeline-event.compact,
            .timeline-event.regular,
            .timeline-event.expanded,
            .timeline-event.featured { flex:1 1 auto; min-width:0; width:100%; }
            .timeline-track::after { height:3px; }
            .timeline-track { padding-bottom:.22rem; }
            .timeline-node { width:15px; height:15px; }
            .timeline-item { padding:.54rem .6rem .5rem .6rem; border-radius:14px; }
            .timeline-item::before { margin:-.54rem -.6rem .4rem -.6rem; }
            .timeline-content { display:flex; flex-direction:column; gap:.46rem; }
            .timeline-media { justify-content:start; min-width:0; max-width:180px; flex:0 1 auto; }
            .timeline-media-card img { height:52px; }
            .timeline-media.media-2 .timeline-media-card img { height:48px; }
            .timeline-media.media-3 .timeline-media-card img { height:44px; }
            .timeline-anchor-index { font-size:.49rem; padding:.11rem .28rem; }
            .timeline-node-date { font-size:.52rem; }
            .timeline-title { font-size:.86rem; margin:.22rem 0 .1rem 0; }
            .timeline-title.featured { font-size:.95rem; }
            .timeline-details { font-size:.75rem; margin:0 0 .22rem 0; }
            .timeline-footer { margin-top:.2rem; padding-top:.22rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if filtered.empty:
        st.info("No timeline events match the selected filters.")
        return

    season_values = filtered["season"].dropna().tolist()
    season_order = []
    seen = set()
    for season in season_values:
        season_key = _to_int_text(season, fallback="N/A")
        if season_key not in seen:
            seen.add(season_key)
            season_order.append(season_key)
    if filtered["season"].isna().any():
        season_order.append("N/A")

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
            "<div class='timeline-season-lanes'>",
        ]

        event_index = 0
        season_rows = list(season_events.iterrows())
        row_size = 3
        for chunk_index in range(0, len(season_rows), row_size):
            chunk = season_rows[chunk_index : chunk_index + row_size]
            lane_reverse = (chunk_index // row_size) % 2 == 1
            lane_class = "timeline-lane-row dir-rtl" if lane_reverse else "timeline-lane-row dir-ltr"
            row_html_parts: list[str] = [f"<div class='{lane_class}'>"]
            for _, row in chunk:
                event_index += 1
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
                player_uri = image_data_uri_thumbnail(player_path, max_width=140, max_height=140) if player_path else None
                competition_uri = (
                    image_data_uri_thumbnail(competition_logo_path, max_width=140, max_height=140) if competition_logo_path else None
                )
                trophy_uri = image_data_uri_thumbnail(trophy_path, max_width=140, max_height=140) if trophy_path else None
                visuals = _visual_priority(row, player_uri, competition_uri, trophy_uri)

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
                    media_html = f"<div class='timeline-media media-{len(visuals)}'>{media_cards}</div>"

                chips_html = ""
                if highlights:
                    chips_html = "".join(f"<span class='timeline-chip'>{_safe_html(chip)}</span>" for chip in highlights)
                    chips_html = f"<div class='timeline-chips'>{chips_html}</div>"
                notes_html = f"<div class='timeline-notes'>Notes: {_safe_html(notes)}</div>" if notes else ""
                footer_html = f"<div class='timeline-footer'>{chips_html}{notes_html}</div>" if (chips_html or notes_html) else ""

                title_class = "timeline-title featured" if priority == "featured" else "timeline-title"
                width_class = _event_width_class(
                    row,
                    visuals_count=len(visuals),
                    highlights_count=len(highlights),
                    priority=priority,
                )

                row_html_parts.append(
                    (
                        f"<div class='timeline-event {_safe_html(priority)} {_safe_html(width_class)} tone-{_safe_html(tone)}'>"
                        "<div class='timeline-track'>"
                        f"<span class='timeline-anchor-index'>#{event_index}</span>"
                        "<span class='timeline-node'></span>"
                        f"<span class='timeline-node-date'>{_safe_html(date_text)}</span>"
                        "</div>"
                        f"<div class='timeline-item tone-{_safe_html(tone)} {_safe_html(priority)}'>"
                        "<div class='timeline-content'>"
                        "<div class='timeline-main'>"
                        "<div class='timeline-head'>"
                        f"<div class='timeline-date'>{_safe_html(date_text)}</div>"
                        "<div class='timeline-badges'>"
                        f"<span class='timeline-tag'>{_safe_html(tone_label)}</span>"
                        f"<span class='timeline-tag'>{_safe_html('Major' if priority == 'featured' else 'Standard')}</span>"
                        "</div>"
                        "</div>"
                        f"<div class='{title_class}'>{_safe_html(title)}</div>"
                        f"{meta_html}{details_html}{footer_html}"
                        "</div>"
                        f"{media_html}"
                        "</div>"
                        "</div>"
                        "</div>"
                    )
                )
            row_html_parts.append("</div>")
            season_html_parts.append("".join(row_html_parts))
            if chunk_index + row_size < len(season_rows):
                bend_class = "timeline-bend to-left" if lane_reverse else "timeline-bend to-right"
                season_html_parts.append(f"<div class='{bend_class}'></div>")

        season_html_parts.extend(["</div>", "</div>"])
        timeline_html_parts.append("".join(season_html_parts))
    timeline_html_parts.append("</div>")
    st.markdown("".join(timeline_html_parts), unsafe_allow_html=True)
