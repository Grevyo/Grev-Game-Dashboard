import streamlit as st
from datetime import datetime, timezone

from app.data_loader import detect_our_team, load_data, reload_data, validate_columns
from app.filters import apply_filters, build_global_filters, filter_panel_toggle, global_filters_from_state
from app.image_helpers import find_team_logo, image_data_uri
from app.pages import (
    medisports_timeline,
    overview,
    player_viewer,
    recent_tactics_breakdown,
    tactic_set_recommendations,
    tactics_breakdown,
    tactics_overview,
    testing_tactics,
    vs_team,
    vs_teams,
    vs_tournaments,
)
from app.styles import inject_styles
from app.transforms import with_player_metrics


PAGE_REGISTRY = [
    ("Overview", overview.render),
    ("Medisports Timeline", medisports_timeline.render),
    ("Player Stats Viewer", player_viewer.render),
    ("Medisports vs Teams", vs_teams.render),
    ("Medisports vs Team", vs_team.render),
    ("Medisports vs Tournaments", vs_tournaments.render),
    ("Tactics Breakdown", tactics_breakdown.render),
    ("Recent Tactics Breakdown", recent_tactics_breakdown.render),
    ("Tactics Overview", tactics_overview.render),
    ("Testing Tactics", testing_tactics.render),
    ("Tactical Set Recommendation", tactic_set_recommendations.render),
]

PAGES = dict(PAGE_REGISTRY)
TEAM_PAGE_PREFERENCE = [
    "Overview",
    "Medisports Timeline",
    "Player Stats Viewer",
    "Medisports vs Teams",
    "Medisports vs Team",
    "Medisports vs Tournaments",
]


def _grouped_navigation_options() -> tuple[list[str], list[str]]:
    options = list(PAGES.keys())
    team_group = [page_name for page_name in TEAM_PAGE_PREFERENCE if page_name in options]
    tactics_group = [page_name for page_name in options if page_name not in team_group]
    return team_group, tactics_group


def _render_nav_group(title: str, subtitle: str, options: list[str], selected: str, key_prefix: str, columns_per_row: int = 5) -> str:
    st.markdown(f"<div class='page-nav-group-title'>{title}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='page-nav-group-subtitle'>{subtitle}</div>", unsafe_allow_html=True)

    for start in range(0, len(options), columns_per_row):
        cols = st.columns(columns_per_row, gap="small")
        row_options = options[start : start + columns_per_row]
        for col_idx, option in enumerate(row_options):
            with cols[col_idx]:
                if st.button(
                    option,
                    key=f"{key_prefix}_{start + col_idx}",
                    type="primary" if option == selected else "secondary",
                    use_container_width=True,
                ):
                    selected = option
    return selected


def _render_page_navigation() -> str:
    team_group, tactics_group = _grouped_navigation_options()
    options = [*team_group, *tactics_group]
    current = st.session_state.get("page_nav", options[0])
    if current not in options:
        current = options[0]
        st.session_state["page_nav"] = current

    nav_shell = st.container()
    selected = current

    with nav_shell:
        st.markdown("<div class='page-nav-anchor'></div>", unsafe_allow_html=True)
        st.markdown(
            (
                "<div class='page-nav-shell'>"
                "<div class='page-nav-title'>Page Navigation</div>"
                "<div class='page-nav-subtitle'>Choose a dashboard surface by Team or Tactics.</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        selected = _render_nav_group(
            title="Team",
            subtitle="Core roster, overview, and matchup pages.",
            options=team_group,
            selected=selected,
            key_prefix="page_nav_team_btn",
        )
        st.markdown("<div class='page-nav-group-gap'></div>", unsafe_allow_html=True)
        selected = _render_nav_group(
            title="Tactics",
            subtitle="Tactical analysis, testing, and recommendation pages.",
            options=tactics_group,
            selected=selected,
            key_prefix="page_nav_tactics_btn",
        )


    st.session_state["page_nav"] = selected
    return selected


def run_app():
    st.set_page_config(page_title="Medisports Analytics", page_icon="🎮", layout="wide")

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

    reload_col, reload_meta_col = st.columns([0.2, 0.8], gap="small")
    with reload_col:
        if st.button("Reload Data", key="reload_data_button", use_container_width=True):
            with st.spinner("Reloading data files..."):
                reload_data()
            st.session_state["last_data_reload"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            st.rerun()
    with reload_meta_col:
        if st.session_state.get("last_data_reload"):
            st.markdown(
                f"<div class='muted' style='padding-top:.45rem;'>Last manual reload: {st.session_state['last_data_reload']}</div>",
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
        "medisports_timeline": data.get("medisports_timeline"),
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

    PAGES[page](filtered)
