import streamlit as st

from app.data_loader import detect_our_team, load_data, validate_columns
from app.filters import apply_filters, build_global_filters, filter_summary, global_filters_from_state
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


def run_app():
    st.set_page_config(page_title="Medisports Analytics", page_icon="🎮", layout="wide")

    data = load_data()
    p_df = with_player_metrics(data["player_matches"])
    t_df = data["tactics"]
    team_name = detect_our_team(p_df, t_df)

    validate_columns(p_df, ["match_id", "date", "map", "competition", "my_team", "opponent_team", "player"], "PlayerDataMatser.csv")
    validate_columns(t_df, ["map", "side", "tactic_name", "wins", "losses", "total_rounds"], "TacticsDataMaster.csv")

    inject_styles("Dark")
    team_logo_uri = image_data_uri(find_team_logo(team_name) or find_team_logo("Medisports"))
    logo_html = f"<img class='hero-logo' src='{team_logo_uri}' alt='Medisports logo'/>" if team_logo_uri else ""
    st.markdown(
        f"<div class='hero-band' style='margin-bottom:12px;'><div style='display:flex;align-items:center;gap:12px;'><div>{logo_html}</div><div><div class='section-title' style='margin-top:0;'>Medisports Analytics Dashboard</div><div class='section-subtitle' style='margin-bottom:0;'>Unified command layer with page-native controls and full-width layout.</div></div></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='top-nav'></div>", unsafe_allow_html=True)
    page = st.radio("Page", list(PAGES.keys()), horizontal=True, label_visibility="collapsed")

    show_filter_toggle = page == "Overview"
    if show_filter_toggle:
        if "overview_show_filters" not in st.session_state:
            st.session_state["overview_show_filters"] = True
        toggle_label = "Hide filters" if st.session_state["overview_show_filters"] else "Show filters"
        if st.button(toggle_label, key="overview_filter_toggle"):
            st.session_state["overview_show_filters"] = not st.session_state["overview_show_filters"]

    filters = build_global_filters(p_df, t_df) if (not show_filter_toggle or st.session_state.get("overview_show_filters", True)) else global_filters_from_state(p_df)
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

    filter_summary(filters)
    PAGES[page](filtered)
