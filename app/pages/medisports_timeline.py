import pandas as pd
import streamlit as st

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

    st.markdown(
        """
        <style>
        .timeline-wrap { display:flex; flex-direction:column; gap:.6rem; margin-top:.35rem; }
        .timeline-item { border:1px solid #2a3848; border-radius:10px; padding:.72rem .8rem; background:linear-gradient(180deg, #111a26 0%, #0d141d 100%); }
        .timeline-head { display:flex; flex-wrap:wrap; align-items:center; gap:.45rem .72rem; justify-content:space-between; }
        .timeline-date { color:#d9e9f8; font-size:.82rem; letter-spacing:.06em; text-transform:uppercase; font-weight:750; }
        .timeline-season { color:#9fb7cc; font-size:.66rem; text-transform:uppercase; letter-spacing:.12em; border:1px solid #39516a; padding:.18rem .42rem; border-radius:999px; }
        .timeline-title { color:#f2f8ff; font-size:1rem; font-weight:760; margin:.45rem 0 .2rem 0; }
        .timeline-meta { color:#9cb0c5; font-size:.71rem; margin-bottom:.25rem; letter-spacing:.04em; text-transform:uppercase; }
        .timeline-details { color:#c9d8e8; font-size:.83rem; line-height:1.45; margin:0 0 .42rem 0; }
        .timeline-chips { display:flex; flex-wrap:wrap; gap:.35rem; margin-top:.2rem; }
        .timeline-chip { border:1px solid #36516b; border-radius:4px; font-size:.62rem; letter-spacing:.08em; text-transform:uppercase; color:#d0e2f5; padding:.2rem .44rem; background:#132131; }
        .timeline-notes { margin-top:.35rem; color:#8ea9c1; font-size:.74rem; }
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
        meta_html = f"<div class='timeline-meta'>{meta_line}</div>" if meta_line else ""
        details_html = f"<p class='timeline-details'>{details}</p>" if details else ""

        st.markdown(
            (
                "<div class='timeline-item'>"
                "<div class='timeline-head'>"
                f"<div class='timeline-date'>{date_text}</div>"
                f"<div class='timeline-season'>Season {season_text}</div>"
                "</div>"
                f"<div class='timeline-title'>{title}</div>"
                f"{meta_html}"
                f"{details_html}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        if highlights:
            chips_html = "".join(f"<span class='timeline-chip'>{chip}</span>" for chip in highlights)
            st.markdown(f"<div class='timeline-chips'>{chips_html}</div>", unsafe_allow_html=True)
        if notes:
            st.markdown(f"<div class='timeline-notes'>Notes: {notes}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
