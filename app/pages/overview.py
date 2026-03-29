import re

import streamlit as st
import pandas as pd

from app.components import insight_card, player_card, section_header, stat_card
from app.achievements import achievements_for_player
from app.data_loader import get_medisports_player_names, get_medisports_roster_df
from app.descriptions import player_description
from app.roster_split import split_roster_active_benched_streamer_transferred
from app.filters import get_current_season
from app.image_helpers import find_team_logo, image_data_uri, resolve_player_photo
from app.metrics import trend_label
from app.transforms import best_contexts, summarize_player, with_resolved_season


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


def _player_key(name: str) -> str:
    text = str(name or "").strip()
    text = re.sub(r"^ⓜ\s*\|\s*", "", text, flags=re.IGNORECASE)
    return text.casefold()


def _tier_grevscores(df_context: pd.DataFrame, player_name: str) -> dict[str, float]:
    if df_context.empty or "player" not in df_context.columns or "tier" not in df_context.columns or "grevscore" not in df_context.columns:
        return {}
    tier_summary = (
        df_context[df_context["player"].astype(str) == str(player_name)]
        .groupby("tier", dropna=False)["grevscore"]
        .mean()
    )
    return {str(tier).upper(): float(score) for tier, score in tier_summary.items()}


def _render_roster_cards(
    summary: pd.DataFrame,
    df_context: pd.DataFrame,
    players_meta: pd.DataFrame,
    player_match_counts: pd.DataFrame,
    team_logo: str | None,
    achievements_df,
    card_variant: str = "default",
):
    rows = list(summary.iterrows())
    for i in range(0, len(rows), 5):
        cols = st.columns(5, gap="small")
        for c_idx, item in enumerate(rows[i : i + 5]):
            _, row = item
            merged = row.to_dict()
            key = _player_key(str(row["player"]))
            meta_source = players_meta.get("player_clean", players_meta.get("player", players_meta.get("name", ""))).astype(str).map(_player_key)
            meta = players_meta[meta_source == key]
            if not meta.empty:
                m = meta.iloc[0].to_dict()
                merged.update(
                    {
                        "country": m.get("country", ""),
                        "nationality": m.get("nationality", ""),
                        "role": m.get("role", ""),
                        "fame": m.get("fame", ""),
                    }
                )
            usage_row = player_match_counts[player_match_counts["player"].astype(str) == str(row["player"])]
            merged["appearance_share"] = float(usage_row.iloc[0]["appearance_share"]) if not usage_row.empty else 0.0

            merged["team_tag"] = "Medisports"
            merged["card_variant"] = card_variant
            merged["desc"] = player_description(merged)
            merged["best_map"] = _context_for_player(df_context, str(row["player"]), "map")
            merged["best_side"] = _context_for_player(df_context, str(row["player"]), "side")
            merged["trend"] = _trend_for_player(df_context, str(row["player"]))
            merged["tier_grevscores"] = _tier_grevscores(df_context, str(row["player"]))
            photo = resolve_player_photo(str(row["player"]))
            merged["photo_uri"] = image_data_uri(photo.get("path"))
            merged["team_logo_uri"] = team_logo
            merged["photo_missing_reason"] = photo.get("reason")
            ach_list, ach_hidden = achievements_for_player(achievements_df, str(row["player"]), cap=4)
            merged["achievements"] = ach_list
            merged["achievements_hidden"] = ach_hidden

            with cols[c_idx]:
                player_card(merged)


def render(ctx):
    full_df = with_resolved_season(ctx["player_matches"], date_col="date")
    full_history_df = with_resolved_season(ctx.get("player_matches_full", full_df), date_col="date")
    players_meta = ctx["players"]
    team_name = ctx["team_name"]
    filters = ctx.get("filters", {})
    achievements_df = ctx.get("achievements")

    # IMPORTANT: Overview must render from the already-filtered dataframe passed in ctx.
    df_base = get_medisports_roster_df(full_df, player_col="player")
    selected_seasons = filters.get("season") or []
    auto_current_season = None
    if not selected_seasons:
        auto_current_season = get_current_season(df_base, "resolved_season")
        season_col = "resolved_season"
        if auto_current_season and season_col in df_base.columns:
            df_base = df_base[df_base[season_col].astype(str) == auto_current_season].copy()

    if auto_current_season:
        st.markdown(f"<span class='chip chip-mid'>Defaulted to Season {auto_current_season}</span>", unsafe_allow_html=True)

    total_matches = int(df_base["match_id"].nunique()) if "match_id" in df_base.columns else 0
    player_match_counts = (
        df_base.groupby("player", dropna=False)["match_id"].nunique().rename("matches_played").reset_index()
        if total_matches > 0 and "player" in df_base.columns and "match_id" in df_base.columns
        else pd.DataFrame(columns=["player", "matches_played"])
    )
    if total_matches > 0 and not player_match_counts.empty:
        player_match_counts["appearance_share"] = player_match_counts["matches_played"] / total_matches
    else:
        player_match_counts["appearance_share"] = 0.0

    df = df_base.copy()

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

    full_medisports_matches = get_medisports_roster_df(full_history_df, player_col="player")
    selected_medisports_matches = get_medisports_roster_df(df, player_col="player")
    active_summary, benched_summary, streamer_summary, transferred_summary, roster_bucket_debug = split_roster_active_benched_streamer_transferred(
        summary=summary,
        player_match_counts=player_match_counts,
        selected_medisports_matches=selected_medisports_matches,
        full_medisports_matches=full_medisports_matches,
        players_meta=players_meta,
        active_threshold=0.10,
    )

    seasons = filters.get("season") or ([f"Season {auto_current_season}"] if auto_current_season else ["All seasons"])
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
                <span class='chip chip-good'>Active: {active_summary['player'].nunique()}</span>
                <span class='chip chip-poor'>Benched/Academy: {benched_summary['player'].nunique()}</span>
                <span class='chip chip-mid'>Streamer: {streamer_summary['player'].nunique()}</span>
                <span class='chip chip-bad'>Transferred: {transferred_summary['player'].nunique()}</span>
              </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        stat_card("Squad Avg GrevScore", f"{summary['grevscore'].mean():.2f}", "Current output index")
    with k2:
        stat_card("Squad Avg Rating", f"{summary['rating'].mean():.2f}", "Form-normalized")
    with k3:
        stat_card("Avg Impact", f"{summary['impact'].mean():.1f}", "Kills + clutch value")
    with k4:
        stat_card("Tracked Matches", int(df["match_id"].nunique()), "Selected context window")

    insight_pool = active_summary if not active_summary.empty else summary
    top_player = insight_pool.sort_values("grevscore", ascending=False).iloc[0]
    improved = insight_pool.sort_values("form", ascending=False).iloc[0]
    coldest = insight_pool.sort_values("form", ascending=True).iloc[0]

    section_header("Team Pulse", "High-signal summary strip")
    p1, p2, p3, p4 = st.columns(4, gap="small")
    with p1:
        insight_card("Strongest Player", f"{top_player['player']} leads at {top_player['grevscore']:.2f} GrevScore.", "good")
    with p2:
        insight_card("Hottest Form", f"{improved['player']} currently shows the strongest rolling form.", "info")
    with p3:
        insight_card("Biggest Concern", f"{coldest['player']} is in the coldest form window and needs stabilization.", "bad")
    with p4:
        insight_card("Avg Team Impact", f"Team baseline is {summary['impact'].mean():.1f} impact per match sample.", "warn")

    section_header("Active Roster", "Primary five-man usage core (>10% match appearance share in current context)")
    if active_summary.empty:
        st.info("No players currently qualify for Active Roster in this filter context.")
    else:
        st.markdown("<div class='roster-section roster-section-main'>", unsafe_allow_html=True)
        _render_roster_cards(active_summary, df, players_meta, player_match_counts, team_logo, achievements_df)
        st.markdown("</div>", unsafe_allow_html=True)

    section_header("Benched / Academy", "Secondary squad view — lower-usage players in the current filtered context")
    if benched_summary.empty:
        st.info("No Benched / Academy players in this filtered context.")
    else:
        st.markdown("<div class='roster-section roster-section-academy'>", unsafe_allow_html=True)
        _render_roster_cards(benched_summary, df, players_meta, player_match_counts, team_logo, achievements_df)
        st.markdown("</div>", unsafe_allow_html=True)

    if not streamer_summary.empty:
        section_header("Streamer", "Rostered Medisports members with no historical match data in the dataset")
        st.markdown("<div class='roster-section roster-section-streamer'>", unsafe_allow_html=True)
        _render_roster_cards(streamer_summary, df, players_meta, player_match_counts, team_logo, achievements_df, card_variant="subdued")
        st.markdown("</div>", unsafe_allow_html=True)

    if not transferred_summary.empty:
        section_header("Transferred", "Historical Medisports players absent for more than two seasons")
        st.markdown("<div class='roster-section roster-section-transferred'>", unsafe_allow_html=True)
        _render_roster_cards(transferred_summary, df, players_meta, player_match_counts, team_logo, achievements_df, card_variant="subdued")
        st.markdown("</div>", unsafe_allow_html=True)

    # Temporary debug tables: prove season filter + roster bucket classification.
    with st.expander("Temporary Debug — Season + Roster Pipeline", expanded=False):
        season_debug = (
            df[["player", "date", "raw_competition_name", "resolved_season"]]
            .sort_values("date", ascending=False)
            .head(50)
            if {"player", "date", "raw_competition_name", "resolved_season"}.issubset(df.columns)
            else pd.DataFrame()
        )
        st.caption("Selected-context rows (top 50) with resolved_season from date windows.")
        st.dataframe(season_debug, use_container_width=True, hide_index=True)
        st.caption("Roster bucket debug built from full-history resolved seasons + selected-season presence.")
        st.dataframe(roster_bucket_debug, use_container_width=True, hide_index=True)

    section_header("Bottom Insights", "Compact coaching cues")
    w1, w2, w3 = st.columns(3, gap="small")
    with w1:
        insight_card("Setup Note", "Anchor early rounds around current high-form duo to preserve conversion rate.", "good")
    with w2:
        insight_card("Risk Note", "Review low-yield side starts where entry impact is trending below baseline.", "warn")
    with w3:
        insight_card("Focus Note", "Use map veto prep to prioritize strongest map clusters from current filter scope.", "info")
