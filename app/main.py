import streamlit as st

from app.data_loader import detect_our_team, load_data, validate_columns
from app.filters import apply_filters, build_global_filters, filter_panel_toggle, filter_summary, global_filters_from_state
from app.image_helpers import find_team_logo, image_data_uri
from app.pages import overview, player_viewer, tactic_set_recommendations, tactics_breakdown, vs_teams, vs_tournaments
from app.styles import inject_styles
from app.transforms import with_player_metrics


PAGES = {
    "Overview": overview.render,
    "Player Stats Viewer": player_viewer.render,
    "Medisports vs Teams": vs_teams.render,
    "Medisports vs Tournaments": vs_tournaments.render,
    "Tactics Breakdown": tactics_breakdown.render,
    "Tactical Set Recommendations": tactic_set_recommendations.render,
}


def _render_page_navigation() -> str:
    options = list(PAGES.keys())
    current = st.session_state.get("page_nav", options[0])
    if current not in options:
        current = options[0]
        st.session_state["page_nav"] = current

    if hasattr(st, "pills"):
        return st.pills(
            "Page",
            options,
            selection_mode="single",
            default=current,
            label_visibility="collapsed",
            key="page_nav",
        )
    if hasattr(st, "segmented_control"):
        return st.segmented_control(
            "Page",
            options,
            default=current,
            selection_mode="single",
            label_visibility="collapsed",
            key="page_nav",
        )
    return st.radio(
        "Page",
        options,
        horizontal=True,
        label_visibility="collapsed",
        key="page_nav",
    )


def run_app():
    st.set_page_config(page_title="Medisports Analytics", page_icon="🎮", layout="wide")

    with st.sidebar:
        if st.button("Reload Data", use_container_width=True, help="Clear cached data and reload files from data/."):
            st.cache_data.clear()
            st.rerun()

    try:
        data = load_data()
    except FileNotFoundError as exc:
        st.error(f"Data loading failed.\n\n{exc}")
        st.stop()

    p_df = with_player_metrics(data["player_matches"])
    t_df = data["tactics"]
    team_name = detect_our_team(p_df, t_df)

    validate_columns(p_df, ["match_id", "date", "map", "competition", "my_team", "opponent_team", "player"], "PlayerDataMatser.csv")
    validate_columns(t_df, ["map", "side", "tactic_name", "wins", "losses", "total_rounds"], "TacticsDataMaster.csv")

    inject_styles("Dark")
    team_logo_uri = image_data_uri(find_team_logo(team_name) or find_team_logo("Medisports"))
    logo_html = f"<img class='hero-logo' src='{team_logo_uri}' alt='Medisports logo'/>" if team_logo_uri else ""
    st.markdown(
        (
            "<div class='hero-band app-topbar' style='margin-bottom:14px;'>"
            "<div class='app-topbar-row'>"
            "<div class='app-topbar-brand'>"
            f"<div class='app-topbar-logo-wrap'>{logo_html}</div>"
            "<div class='app-topbar-copy'>"
            "<div class='section-title app-topbar-kicker'>Medisports Command Surface</div>"
            "<div class='app-topbar-title'>Competitive Intelligence Studio</div>"
            "<div class='section-subtitle app-topbar-subtitle'>"
            "Esports analytics environment for roster, opponent, and tactical command decisions."
            "</div>"
            "</div>"
            "</div>"
            "<div class='app-topbar-chips'>"
            "<span class='chip chip-mid'>Live Data Ops</span>"
            "<span class='chip chip-good'>Tactical Intelligence</span>"
            "<span class='chip chip-poor'>Roster Context</span>"
            "</div>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    page = _render_page_navigation()

    page_scope = page.lower().replace(" ", "_")
    show_filters = filter_panel_toggle(f"global_{page_scope}")

    filters = build_global_filters(p_df, t_df) if show_filters else global_filters_from_state(p_df)
    inject_styles(filters.get("theme", "Dark"))

    filtered = {
        "player_matches": apply_filters(p_df, filters),
        "player_matches_full": p_df,
        "tactics": apply_filters(t_df, filters),
        "players": data["players"],
        "achievements": data["achievements"],
        "team_name": team_name,
        "filters": filters,
    }

    max_match_date = "N/A"
    if "date" in p_df.columns and not p_df.empty:
        max_date = p_df["date"].max()
        if hasattr(max_date, "strftime"):
            max_match_date = max_date.strftime("%Y-%m-%d")
        else:
            max_match_date = str(max_date)

    meta_1, meta_2, meta_3, meta_4 = st.columns(4, gap="small")
    meta_1.markdown(f"<div class='panel panel-tight accent-good'><div class='metric-title'>Matches Loaded</div><div class='metric-value'>{len(data['player_matches'])}</div></div>", unsafe_allow_html=True)
    meta_2.markdown(f"<div class='panel panel-tight accent-mid'><div class='metric-title'>Tactic Logs</div><div class='metric-value'>{len(data['tactics'])}</div></div>", unsafe_allow_html=True)
    meta_3.markdown(f"<div class='panel panel-tight accent-poor'><div class='metric-title'>Profiles</div><div class='metric-value'>{len(data['players'])}</div></div>", unsafe_allow_html=True)
    meta_4.markdown(f"<div class='panel panel-tight accent-good'><div class='metric-title'>Latest Match</div><div class='metric-value' style='font-size:1.1rem'>{max_match_date}</div></div>", unsafe_allow_html=True)

    filter_summary(filters)
    st.markdown("<div class='context-ribbon'><span class='section-title' style='margin-bottom:2px'>Active Workspace</span><span class='muted'>Analyst view: tactical and player intelligence surfaces are now tuned for a dense esports control-room layout.</span></div>", unsafe_allow_html=True)
    PAGES[page](filtered)
