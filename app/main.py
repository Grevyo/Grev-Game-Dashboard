import streamlit as st

from app.data_loader import detect_our_team, load_data, validate_columns
from app.filters import apply_filters, build_global_filters, filter_summary
from app.pages import overview, player_viewer, tactics_breakdown, tactic_set_recommendations, vs_teams, vs_tournaments
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
    theme = st.sidebar.selectbox("Theme", ["Dark", "Light"], index=0)
    inject_styles(theme)

    data = load_data()
    p_df = with_player_metrics(data["player_matches"])
    t_df = data["tactics"]
    team_name = detect_our_team(p_df, t_df)

    validate_columns(p_df, ["match_id", "date", "map", "competition", "my_team", "opponent_team", "player"], "PlayerDataMatser.csv")
    validate_columns(t_df, ["map", "side", "tactic_name", "wins", "losses", "total_rounds"], "TacticsDataMaster.csv")

    filters = build_global_filters(p_df, t_df)
    filtered = {
        "player_matches": apply_filters(p_df, filters),
        "tactics": apply_filters(t_df, filters),
        "players": data["players"],
        "achievements": data["achievements"],
        "team_name": team_name,
        "filters": filters,
    }

    st.sidebar.markdown("---")
    st.sidebar.caption(filter_summary(filters))
    page = st.sidebar.radio("Page", list(PAGES.keys()))
    PAGES[page](filtered)
