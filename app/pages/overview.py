import streamlit as st

from app.components import insight_card, player_card, section_header, stat_card
from app.achievements import achievements_for_player
from app.data_loader import get_medisports_player_names, get_medisports_roster_df
from app.descriptions import player_description
from app.image_helpers import find_team_logo, image_data_uri, resolve_player_photo
from app.metrics import trend_label
from app.transforms import best_contexts, summarize_player


def _context_for_player(df, player_name: str, by: str, default: str = "N/A") -> str:
    if df.empty or by not in df.columns or "player" not in df.columns:
        return default
    subset = df[df["player"] == player_name]
    if subset.empty:
        return default
    best = best_contexts(subset, by)
    if best.empty:
        return default
    return str(best.iloc[0][by])


def _trend_for_player(df, player_name: str) -> str:
    if df.empty or "player" not in df.columns or "grevscore" not in df.columns:
        return "Stable"
    s = df[df["player"] == player_name].sort_values("date")["grevscore"]
    label = trend_label(s)
    return "Heating Up" if label == "Rising" else "Cooling" if label == "Falling" else "Stable"


def render(ctx):
    full_df = ctx["player_matches"]
    players_meta = ctx["players"]
    team_name = ctx["team_name"]
    filters = ctx.get("filters", {})
    achievements_df = ctx.get("achievements")

    df = get_medisports_roster_df(full_df, player_col="player")

    if df.empty:
        st.warning("No Medisports rows available after filters.")
        return

    medisports_roster = get_medisports_player_names(df, player_col="player")
    if not medisports_roster:
        st.warning("No Medisports roster available for Overview.")
        return

    summary = summarize_player(df)
    if summary.empty:
        st.warning("No Medisports player summary available with current filters.")
        return

    summary = summary[summary["player"].isin(medisports_roster)]
    if summary.empty:
        st.warning("No Medisports roster available for Overview.")
        return

    seasons = filters.get("season") or ["All seasons"]
    maps = filters.get("map") or ["All maps"]

    team_logo = image_data_uri(find_team_logo(team_name) or find_team_logo("Medisports"))
    team_logo_html = f"<img class='hero-logo' src='{team_logo}' alt='Medisports logo'/>" if team_logo else ""

    st.markdown(
        f"""
        <div class='hero-band'>
            <div style='display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;'>
              <div style='display:flex;align-items:center;gap:14px;'>
                {team_logo_html}
                <div>
                  <div class='section-title' style='margin-top:0'>Squad Command Hub</div>
                  <div class='section-subtitle' style='margin-bottom:8px;'>Live Medisports pulse across map, side, and form context.</div>
                  <span class='chip'>Season: {', '.join(map(str, seasons[:2]))}{'…' if len(seasons) > 2 else ''}</span>
                  <span class='chip'>Map scope: {', '.join(map(str, maps[:2]))}{'…' if len(maps) > 2 else ''}</span>
                </div>
              </div>
              <div>
                <span class='chip chip-good'>Context: Active</span>
                <span class='chip'>Medisports Roster: {summary['player'].nunique()}</span>
              </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        stat_card("Squad Avg GrevScore", f"{summary['grevscore'].mean():.1f}", "Current output index")
    with k2:
        stat_card("Squad Avg Rating", f"{summary['rating'].mean():.2f}", "Form-normalized")
    with k3:
        stat_card("Avg Impact", f"{summary['impact'].mean():.1f}", "Kills + clutch value")
    with k4:
        stat_card("Tracked Matches", int(df["match_id"].nunique()), "Selected context window")

    top_player = summary.sort_values("grevscore", ascending=False).iloc[0]
    improved = summary.sort_values("form", ascending=False).iloc[0]
    coldest = summary.sort_values("form", ascending=True).iloc[0]

    section_header("Team Pulse", "High-signal summary strip")
    p1, p2, p3, p4 = st.columns(4, gap="small")
    with p1:
        insight_card("Strongest Player", f"{top_player['player']} leads at {top_player['grevscore']:.1f} GrevScore.", "good")
    with p2:
        insight_card("Hottest Form", f"{improved['player']} currently shows the strongest rolling form.", "info")
    with p3:
        insight_card("Biggest Concern", f"{coldest['player']} is in the coldest form window and needs stabilization.", "bad")
    with p4:
        insight_card("Avg Team Impact", f"Team baseline is {summary['impact'].mean():.1f} impact per match sample.", "warn")

    section_header("Main Roster Grid", "Compact equal-height profile cards")
    rows = list(summary.iterrows())
    for i in range(0, len(rows), 3):
        cols = st.columns(3, gap="small")
        for c_idx, item in enumerate(rows[i : i + 3]):
            _, row = item
            merged = row.to_dict()
            meta = players_meta[
                players_meta.get("player_clean", players_meta.get("name", "")).astype(str).str.contains(str(row["player"]), case=False, regex=False)
            ]
            if not meta.empty:
                m = meta.iloc[0].to_dict()
                merged.update({"country": m.get("country", ""), "role": m.get("role", "")})

            merged["team_tag"] = "Medisports"
            merged["desc"] = player_description(row)
            merged["best_map"] = _context_for_player(df, str(row["player"]), "map")
            merged["best_side"] = _context_for_player(df, str(row["player"]), "side")
            merged["trend"] = _trend_for_player(df, str(row["player"]))
            photo = resolve_player_photo(str(row["player"]))
            merged["photo_uri"] = image_data_uri(photo.get("path"))
            merged["team_logo_uri"] = team_logo
            merged["photo_missing_reason"] = photo.get("reason")
            ach_list, ach_hidden = achievements_for_player(achievements_df, str(row["player"]), cap=3)
            merged["achievements"] = ach_list
            merged["achievements_hidden"] = ach_hidden

            with cols[c_idx]:
                player_card(merged)

    section_header("Bottom Insights", "Compact coaching cues")
    w1, w2, w3 = st.columns(3, gap="small")
    with w1:
        insight_card("Setup Note", "Anchor early rounds around current high-form duo to preserve conversion rate.", "good")
    with w2:
        insight_card("Risk Note", "Review low-yield side starts where entry impact is trending below baseline.", "warn")
    with w3:
        insight_card("Focus Note", "Use map veto prep to prioritize strongest map clusters from current filter scope.", "info")
