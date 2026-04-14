import html
import re
import unicodedata

import pandas as pd
import streamlit as st

from app.config import IMAGES
from app.data_loader import get_medisports_player_names, normalize_player_key
from app.image_helpers import (
    find_achievement_image,
    find_competition_logo,
    image_data_uri_thumbnail,
    resolve_achievement_image,
    resolve_player_photo,
    SUPPORTED_EXTENSIONS,
)
from app.page_layout import section_header


def _display_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if not text else text


def _to_int_text(value: object, *, fallback: str = "") -> str:
    if value is None or pd.isna(value):
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


def _safe_html(value: object) -> str:
    return html.escape(_display_value(value))


def _normalize_for_match(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
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


def _resolve_tournament_visual(
    row: pd.Series,
    known_competitions: list[str],
    competition_logo_index: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    competition = _competition_from_row(row, known_competitions, competition_logo_index)
    if not competition:
        return None, None, None

    placement = _infer_gold_placement(row)
    resolved = resolve_achievement_image(
        link_or_name=competition,
        achievement_name=competition,
        placement=placement,
    )
    trophy_path = None
    final_path = resolved.get("final_path")
    if final_path:
        trophy_path = str(final_path)
    elif str(placement).strip().startswith("1"):
        gold_path = find_achievement_image(
            link_or_name=f"{competition} gold",
            achievement_name=competition,
            placement="1st",
        )
        if gold_path:
            trophy_path = gold_path

    competition_logo = competition_logo_index.get(_normalize_for_match(competition))
    return competition, competition_logo, trophy_path


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
    if tournament_centric and trophy_image_uri:
        visuals.append(("Achievement", trophy_image_uri))
    elif competition_image_uri:
        visuals.append(("Competition", competition_image_uri))
    elif trophy_image_uri:
        visuals.append(("Achievement", trophy_image_uri))

    if player_centric and len(visuals) > 1:
        visuals = sorted(visuals, key=lambda item: 0 if item[0] == "Player" else 1)
    elif tournament_centric and len(visuals) > 1:
        visuals = sorted(visuals, key=lambda item: 0 if item[0] in {"Achievement", "Competition"} else 1)

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

    st.markdown(
        """
        <style>
        .timeline-wrap { display:flex; flex-direction:column; gap:.6rem; margin-top:.35rem; }
        .timeline-item { border:1px solid #2a3848; border-radius:12px; padding:.76rem .84rem; background:linear-gradient(180deg, #111a26 0%, #0d141d 100%); box-shadow:0 8px 18px rgba(0, 0, 0, .22); }
        .timeline-content { display:grid; grid-template-columns: minmax(0, 1fr) auto; gap:.75rem; align-items:start; }
        .timeline-head { display:flex; flex-wrap:wrap; align-items:center; gap:.45rem .72rem; justify-content:space-between; }
        .timeline-date { color:#d9e9f8; font-size:.82rem; letter-spacing:.06em; text-transform:uppercase; font-weight:750; }
        .timeline-season { color:#9fb7cc; font-size:.66rem; text-transform:uppercase; letter-spacing:.12em; border:1px solid #39516a; padding:.18rem .42rem; border-radius:999px; }
        .timeline-title { color:#f2f8ff; font-size:1rem; font-weight:760; margin:.45rem 0 .2rem 0; }
        .timeline-meta { color:#9cb0c5; font-size:.71rem; margin-bottom:.25rem; letter-spacing:.04em; text-transform:uppercase; }
        .timeline-details { color:#c9d8e8; font-size:.83rem; line-height:1.45; margin:0 0 .42rem 0; }
        .timeline-chips { display:flex; flex-wrap:wrap; gap:.35rem; margin-top:.2rem; }
        .timeline-chip { border:1px solid #36516b; border-radius:4px; font-size:.62rem; letter-spacing:.08em; text-transform:uppercase; color:#d0e2f5; padding:.2rem .44rem; background:#132131; }
        .timeline-notes { margin-top:.35rem; color:#8ea9c1; font-size:.74rem; }
        .timeline-media { display:flex; flex-direction:column; gap:.34rem; min-width:90px; }
        .timeline-media-card { width:90px; border:1px solid #2f4255; border-radius:9px; overflow:hidden; background:#0c1420; }
        .timeline-media-card img { width:100%; height:72px; object-fit:cover; object-position:center; display:block; }
        .timeline-media-card .label { color:#8ea8be; font-size:.58rem; letter-spacing:.1em; text-transform:uppercase; text-align:center; padding:.16rem .2rem; border-top:1px solid #23384e; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if filtered.empty:
        st.info("No timeline events match the selected filters.")
        return

    st.markdown("<div class='timeline-wrap'>", unsafe_allow_html=True)
    for _, row in filtered.iterrows():
        date_value = row.get("date")
        date_text = date_value.strftime("%Y-%m-%d") if pd.notna(date_value) else "Date TBD"
        season_text = _to_int_text(row.get("season"), fallback="Season N/A")
        title = _display_value(row.get("title")) or "Untitled event"
        details = _display_value(row.get("details"))
        meta_line = _timeline_meta_line(row)
        notes = _display_value(row.get("notes"))
        highlights = _timeline_highlights(row)
        _, player_path = _resolve_player_visual(row, player_photo_index)
        _, competition_logo_path, trophy_path = _resolve_tournament_visual(
            row,
            known_competitions,
            competition_logo_index,
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
            media_html = f"<div class='timeline-media'>{media_cards}</div>"

        st.markdown(
            (
                "<div class='timeline-item'>"
                "<div class='timeline-content'>"
                "<div>"
                "<div class='timeline-head'>"
                f"<div class='timeline-date'>{_safe_html(date_text)}</div>"
                f"<div class='timeline-season'>Season {_safe_html(season_text)}</div>"
                "</div>"
                f"<div class='timeline-title'>{_safe_html(title)}</div>"
                f"{meta_html}{details_html}"
                "</div>"
                f"{media_html}"
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        if highlights:
            chips_html = "".join(f"<span class='timeline-chip'>{_safe_html(chip)}</span>" for chip in highlights)
            st.markdown(f"<div class='timeline-chips'>{chips_html}</div>", unsafe_allow_html=True)
        if notes:
            st.markdown(f"<div class='timeline-notes'>Notes: {_safe_html(notes)}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
