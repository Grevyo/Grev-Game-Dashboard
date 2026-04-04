import streamlit as st
import pandas as pd
import os

from app.components import insight_card, player_card, stat_card
from app.achievements import achievements_for_player
from app.data_loader import get_medisports_player_names, get_medisports_roster_df, normalize_player_key, normalize_side_label
from app.descriptions import player_description
from app.roster_split import split_roster_active_benched_streamer_transferred
from app.filters import get_current_season
from app.image_helpers import find_team_logo, image_data_uri, resolve_player_photo, resolve_transferred_logo
from app.metrics import stat_tone, trend_label
from app.transforms import best_contexts, summarize_player
from app.match_summaries import build_best_match_summary, build_last_match_summary
from app.page_layout import section_header
from app.datetime_utils import build_match_timestamp, normalize_time_string


def _resolve_favourite_map(meta: pd.DataFrame, player_key: str, default: str = "N/A") -> str:
    if meta.empty or not player_key:
        return default
    favourite_map_candidates = [
        "map",
        "favourite_map",
        "favorite_map",
        "fav_map",
        "favourite",
        "favorite",
        "map_favourite",
        "map_favorite",
    ]
    favourite_col = next((col for col in favourite_map_candidates if col in meta.columns), None)
    if not favourite_col:
        return default
    if "player_clean" not in meta.columns:
        return default
    player_meta = meta[meta["player_clean"].astype(str) == str(player_key)]
    if player_meta.empty:
        return default
    raw_value = str(player_meta.iloc[0].get(favourite_col, "") or "").strip()
    return raw_value if raw_value else default


def _best_map_for_player(
    df_context: pd.DataFrame,
    player_name: str,
    default: str = "N/A",
    min_map_samples: int = 2,
) -> str:
    if df_context.empty or "player" not in df_context.columns or "map" not in df_context.columns:
        return default

    subset = df_context[df_context["player"].astype(str) == str(player_name)].copy()
    if subset.empty:
        return default
    subset["map"] = subset["map"].astype(str).str.strip()
    subset = subset[subset["map"] != ""]
    if subset.empty:
        return default

    metric_priority = ["grevscore", "rating", "impact", "kpd", "kpr"]
    metric_col = next((col for col in metric_priority if col in subset.columns), None)
    if metric_col is None:
        return default

    sample_col = "match_id" if "match_id" in subset.columns else None
    if sample_col is None:
        fallback_candidates = ["date", "opponent_team", "competition", "raw_competition_name"]
        sample_col = next((col for col in fallback_candidates if col in subset.columns), None)

    if sample_col:
        sample_agg = (sample_col, "nunique")
    else:
        sample_agg = ("map", "size")

    grouped = (
        subset.groupby("map", dropna=False)
        .agg(score=(metric_col, "mean"), samples=sample_agg)
        .query("samples > 0")
        .reset_index()
    )
    if grouped.empty:
        return default

    eligible = grouped[grouped["samples"] >= min_map_samples]
    if eligible.empty:
        max_samples = grouped["samples"].max()
        eligible = grouped[grouped["samples"] == max_samples]

    best = eligible.sort_values(["score", "samples"], ascending=[False, False]).head(1)
    if best.empty:
        return default
    value = str(best.iloc[0]["map"]).strip()
    return value if value else default


def _overview_best_map_payload(df_context: pd.DataFrame, player_name: str) -> dict[str, str]:
    best_map_value = _best_map_for_player(df_context, player_name)
    return {
        "best_map": best_map_value,
        "best_map_label": f"Best Map (Overview): {best_map_value}",
    }


def _overview_player_context(df_base: pd.DataFrame, filters: dict | None = None) -> tuple[pd.DataFrame, str | None]:
    df_context = df_base.copy()
    selected_seasons = (filters or {}).get("season") or []
    auto_current_season = None
    if not selected_seasons:
        auto_current_season = get_current_season(df_context, "resolved_season")
        season_col = "resolved_season"
        if auto_current_season and season_col in df_context.columns:
            df_context = df_context[df_context[season_col].astype(str) == auto_current_season].copy()
    return df_context, auto_current_season


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


def _best_side_for_player(
    df_context: pd.DataFrame,
    tactics_context: pd.DataFrame,
    player_name: str,
    default: str = "N/A",
) -> str:
    """Return the side with the highest aggregate GrevScore for a player."""
    if df_context.empty or "player" not in df_context.columns or "grevscore" not in df_context.columns:
        return default

    player_subset = df_context[df_context["player"].astype(str) == str(player_name)].copy()
    if player_subset.empty:
        return default

    side_candidates = ["side", "team_side", "player_side", "starting_side"]
    player_side_col = next((c for c in side_candidates if c in player_subset.columns), None)

    if player_side_col:
        side_rows = player_subset[["grevscore", player_side_col]].rename(columns={player_side_col: "side_raw"}).copy()
    else:
        if tactics_context.empty or "match_id" not in tactics_context.columns or "match_id" not in player_subset.columns:
            return default
        tactic_side_col = next((c for c in side_candidates if c in tactics_context.columns), None)
        if tactic_side_col is None:
            return default

        player_rows = player_subset[["match_id", "grevscore"]].copy()
        player_rows["match_id"] = player_rows["match_id"].astype(str)

        tactic_rows = tactics_context[["match_id", tactic_side_col]].copy()
        tactic_rows["match_id"] = tactic_rows["match_id"].astype(str)
        tactic_rows = tactic_rows.rename(columns={tactic_side_col: "side_raw"})

        side_rows = player_rows.merge(tactic_rows, on="match_id", how="inner")

    if side_rows.empty:
        return default

    side_rows["grevscore"] = pd.to_numeric(side_rows["grevscore"], errors="coerce")
    side_rows["side_raw"] = side_rows["side_raw"].astype(str).str.strip()
    side_rows = side_rows[(side_rows["side_raw"] != "") & side_rows["grevscore"].notna()].copy()
    if side_rows.empty:
        return default

    side_rows["side_norm"] = side_rows["side_raw"].map(normalize_side_label)
    side_rows = side_rows[side_rows["side_norm"].astype(str).str.strip() != ""].copy()
    if side_rows.empty:
        return default

    playable_sides = side_rows["side_norm"].value_counts().index.tolist()
    if len(playable_sides) < 2:
        return default
    playable_sides = playable_sides[:2]

    usable = side_rows[side_rows["side_norm"].isin(playable_sides)].copy()
    grouped = (
        usable.groupby("side_norm", dropna=False)
        .agg(grevscore=("grevscore", "mean"), rows=("side_norm", "size"))
        .reset_index()
    )
    if grouped.empty or grouped["side_norm"].nunique() < 2:
        return default

    best = grouped.sort_values(["grevscore", "rows"], ascending=[False, False]).head(1)
    if best.empty:
        return default

    return str(best.iloc[0]["side_norm"])


def _trend_for_player(df, player_name: str) -> str:
    if df.empty or "player" not in df.columns or "grevscore" not in df.columns:
        return "Stable"
    s = df[df["player"] == player_name].sort_values("date")["grevscore"]
    label = trend_label(s)
    return "Heating Up" if label == "Rising" else "Cooling" if label == "Falling" else "Stable"


def _player_key(name: str) -> str:
    return normalize_player_key(name)


def _tier_grevscores(df_context: pd.DataFrame, player_name: str) -> dict[str, float]:
    if df_context.empty or "player" not in df_context.columns or "tier" not in df_context.columns or "grevscore" not in df_context.columns:
        return {}
    tier_summary = (
        df_context[df_context["player"].astype(str) == str(player_name)]
        .groupby("tier", dropna=False)["grevscore"]
        .mean()
    )
    return {str(tier).upper(): float(score) for tier, score in tier_summary.items()}


def _build_recent_team_matches(player_matches: pd.DataFrame, tactics_df: pd.DataFrame, limit: int = 30) -> pd.DataFrame:
    if player_matches.empty:
        return pd.DataFrame()

    base_cols = ["match_id", "date", "time", "opponent_team", "competition", "map", "tier"]
    available_cols = [col for col in base_cols if col in player_matches.columns]
    if not {"date", "opponent_team"}.issubset(set(available_cols)):
        return pd.DataFrame()

    team_matches = player_matches[available_cols].copy()
    team_matches["date"] = pd.to_datetime(team_matches["date"], errors="coerce")
    if "time" not in team_matches.columns:
        team_matches["time"] = None
    team_matches["time"] = team_matches["time"].map(normalize_time_string)
    team_matches["match_ts"] = build_match_timestamp(team_matches["date"], team_matches["time"])
    team_matches = team_matches.dropna(subset=["date"]).copy()

    grouping_keys = [key for key in ["match_id", "date", "time", "opponent_team", "competition", "map", "tier", "match_ts"] if key in team_matches.columns]
    team_matches = team_matches.drop_duplicates(subset=grouping_keys, keep="first")

    if not tactics_df.empty and "date" in tactics_df.columns:
        score_cols = [c for c in ["match_id", "date", "time", "opponent_team", "competition", "map", "wins", "losses"] if c in tactics_df.columns]
        if {"wins", "losses"}.issubset(set(score_cols)):
            score_df = tactics_df[score_cols].copy()
            score_df["date"] = pd.to_datetime(score_df["date"], errors="coerce")
            if "time" not in score_df.columns:
                score_df["time"] = None
            score_df["time"] = score_df["time"].map(normalize_time_string)
            score_df["wins"] = pd.to_numeric(score_df["wins"], errors="coerce").fillna(0)
            score_df["losses"] = pd.to_numeric(score_df["losses"], errors="coerce").fillna(0)
            score_group_cols = [c for c in ["match_id", "date", "time", "opponent_team", "competition", "map"] if c in score_df.columns]
            if score_group_cols:
                score_summary = score_df.groupby(score_group_cols, dropna=False)[["wins", "losses"]].sum().reset_index()
                score_summary["result"] = score_summary.apply(
                    lambda row: "W" if row["wins"] > row["losses"] else "L" if row["wins"] < row["losses"] else "D",
                    axis=1,
                )
                score_summary["score"] = score_summary["wins"].astype(int).astype(str) + "-" + score_summary["losses"].astype(int).astype(str)
                merge_keys = [c for c in ["match_id", "date", "time", "opponent_team", "competition", "map"] if c in team_matches.columns and c in score_summary.columns]
                if merge_keys:
                    team_matches = team_matches.merge(score_summary[merge_keys + ["result", "score"]], on=merge_keys, how="left")

    if "result" not in team_matches.columns:
        team_matches["result"] = "—"
    if "score" not in team_matches.columns:
        team_matches["score"] = "—"

    team_matches = team_matches.sort_values("match_ts", ascending=False).head(limit).copy()
    team_matches["date_label"] = team_matches["date"].dt.strftime("%Y-%m-%d")
    team_matches["time_label"] = team_matches["time"].fillna("—").astype(str).str.slice(0, 5)
    team_matches["competition"] = team_matches.get("competition", pd.Series(["—"] * len(team_matches))).fillna("—")
    team_matches["map"] = team_matches.get("map", pd.Series(["—"] * len(team_matches))).fillna("—")
    team_matches["tier"] = team_matches.get("tier", pd.Series(["—"] * len(team_matches))).fillna("—")
    return team_matches.reset_index(drop=True)


def _render_recent_team_matches(matches: pd.DataFrame):
    section_header("Last 30 Games", "Newest first — team-level recent chronology")
    st.markdown("<div class='recent-matches-panel'>", unsafe_allow_html=True)
    if matches.empty:
        st.info("No recent team matches are available in the current filter scope.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.markdown(
        """
        <div class='recent-matches-head'>
          <span>Date</span><span>Time</span><span>Opponent</span><span>Competition</span><span>Map</span><span>Result</span><span>Score</span><span>Tier</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for _, row in matches.iterrows():
        result_value = str(row.get("result", "—")).strip().upper()
        result_class = "is-neutral"
        if result_value == "W":
            result_class = "is-win"
        elif result_value == "L":
            result_class = "is-loss"
        elif result_value == "D":
            result_class = "is-draw"

        st.markdown(
            f"""
            <div class='recent-match-row'>
              <span>{row.get("date_label", "—")}</span>
              <span>{row.get("time_label", "—")}</span>
              <span class='opponent'>{row.get("opponent_team", "—")}</span>
              <span>{row.get("competition", "—")}</span>
              <span>{row.get("map", "—")}</span>
              <span><span class='result-pill {result_class}'>{result_value or "—"}</span></span>
              <span>{row.get("score", "—")}</span>
              <span>{row.get("tier", "—")}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_roster_cards(
    summary: pd.DataFrame,
    df_context: pd.DataFrame,
    tactics_context: pd.DataFrame,
    players_meta: pd.DataFrame,
    player_match_counts: pd.DataFrame,
    team_logo: str | None,
    achievements_df,
    card_variant: str = "default",
    transferred_logo_fallback: bool = False,
):
    rows = list(summary.iterrows())
    for i in range(0, len(rows), 5):
        cols = st.columns(5, gap="small")
        for c_idx, item in enumerate(rows[i : i + 5]):
            _, row = item
            merged = row.to_dict()
            key = _player_key(str(row["player"]))
            meta_name_col = "player_clean" if "player_clean" in players_meta.columns else "player" if "player" in players_meta.columns else "name" if "name" in players_meta.columns else None
            meta = players_meta.iloc[0:0]
            if meta_name_col:
                meta_source = players_meta[meta_name_col].astype(str).map(_player_key)
                meta = players_meta[meta_source == key]
            if not meta.empty:
                m = meta.iloc[0].to_dict()
                merged.update(
                    {
                        "country": m.get("country", ""),
                        "nationality": m.get("nationality", ""),
                        "role": m.get("role", ""),
                        "fame": m.get("fame", ""),
                        "new_team": str(m.get("new_team", m.get("New_team", "")) or "").strip(),
                    }
                )
            merged["favourite_map"] = _resolve_favourite_map(players_meta, key)
            new_team = str(merged.get("new_team", merged.get("New_team", "")) or "").strip()
            usage_row = player_match_counts[player_match_counts["player"].astype(str) == str(row["player"])]
            merged["appearance_share"] = float(usage_row.iloc[0]["appearance_share"]) if not usage_row.empty else 0.0

            merged["card_variant"] = card_variant
            if card_variant == "streamer":
                merged["role"] = "Streamer"
                merged["desc"] = "Streamer profile — competitive stats not yet tracked."
                merged["roster_bucket"] = "streamer"
            else:
                merged["roster_bucket"] = ""
                merged["desc"] = player_description(merged)
            merged.update(_overview_best_map_payload(df_context, str(row["player"])))
            merged["best_side"] = _best_side_for_player(
                df_context,
                tactics_context,
                str(row["player"]),
            ) if card_variant != "streamer" else "N/A"
            merged["trend"] = _trend_for_player(df_context, str(row["player"])) if card_variant != "streamer" else ""
            merged["tier_grevscores"] = _tier_grevscores(df_context, str(row["player"])) if card_variant != "streamer" else {}
            merged["last_match"] = None if card_variant == "streamer" else build_last_match_summary(df_context, tactics_context, str(row["player"]))
            merged["best_match"] = None if card_variant == "streamer" else build_best_match_summary(df_context, tactics_context, str(row["player"]))
            photo = resolve_player_photo(str(row["player"]))
            merged["photo_uri"] = image_data_uri(photo.get("path"))
            if transferred_logo_fallback:
                destination = new_team if new_team else None
                merged["team_logo_uri"] = image_data_uri(resolve_transferred_logo(destination))
            else:
                merged["team_logo_uri"] = team_logo
            merged["photo_missing_reason"] = photo.get("reason")
            ach_list, ach_hidden = achievements_for_player(
                achievements_df,
                str(row["player"]),
                cap=4,
                consumer="overview",
            )
            merged["achievements"] = ach_list
            merged["achievements_hidden"] = ach_hidden

            with cols[c_idx]:
                player_card(merged)


def _build_streamer_metadata_rows(
    players_meta: pd.DataFrame,
    active_summary: pd.DataFrame,
    benched_summary: pd.DataFrame,
    transferred_summary: pd.DataFrame,
) -> pd.DataFrame:
    if players_meta.empty:
        return pd.DataFrame(columns=["player", "country", "nationality", "role", "fame", "new_team"])

    name_col = "player_clean" if "player_clean" in players_meta.columns else "player" if "player" in players_meta.columns else "name" if "name" in players_meta.columns else None
    if not name_col or "role" not in players_meta.columns:
        return pd.DataFrame(columns=["player", "country", "nationality", "role", "fame", "new_team"])

    meta = players_meta.copy()
    meta["role_key"] = meta["role"].astype(str).str.strip().str.casefold()
    meta["player_key"] = meta[name_col].astype(str).map(_player_key)

    medisports_mask = pd.Series([False] * len(meta), index=meta.index)
    if "player" in meta.columns:
        medisports_mask = medisports_mask | meta["player"].map(lambda v: "ⓜ" in str(v or ""))
    if "name" in meta.columns:
        medisports_mask = medisports_mask | meta["name"].map(lambda v: "ⓜ" in str(v or ""))

    streamer_meta = meta[medisports_mask & (meta["role_key"] == "streamer")].copy()
    if streamer_meta.empty:
        return pd.DataFrame(columns=["player", "country", "nationality", "role", "fame", "new_team"])

    excluded_keys: set[str] = set()
    for section_df in [active_summary, benched_summary, transferred_summary]:
        if not section_df.empty and "player" in section_df.columns:
            excluded_keys.update(section_df["player"].astype(str).map(_player_key).tolist())

    if excluded_keys:
        streamer_meta = streamer_meta[~streamer_meta["player_key"].isin(excluded_keys)]

    display_name_col = "player" if "player" in streamer_meta.columns else "name"
    streamer_meta = streamer_meta.rename(columns={display_name_col: "player"})
    if "nationality" not in streamer_meta.columns:
        streamer_meta["nationality"] = streamer_meta.get("country", "")
    return streamer_meta.drop_duplicates(subset=["player_key"], keep="first")


def render(ctx):
    full_df = ctx["player_matches"]
    full_history_df = ctx.get("player_matches_full", full_df)
    players_meta = ctx["players"]
    team_name = ctx["team_name"]
    filters = ctx.get("filters", {})
    achievements_df = ctx.get("achievements")

    df_base = get_medisports_roster_df(full_df, player_col="player")
    df_base, auto_current_season = _overview_player_context(df_base, filters)

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
        st.warning("No Medisports match rows available after filters. Showing metadata-driven roster cards where possible.")

    medisports_roster = get_medisports_player_names(df, player_col="player")
    summary = summarize_player(df) if not df.empty else pd.DataFrame(columns=["player", "matches", "grevscore", "rating", "impact", "form", "kpd", "kpr", "accuracy_pct", "hs_pct"])
    if not summary.empty and medisports_roster:
        summary = summary[summary["player"].isin(medisports_roster)]

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

    # Defensive rendering guard: keep each player in exactly one section using split output bucket assignment.
    def _ensure_bucket(df_bucket: pd.DataFrame, bucket_name: str) -> pd.DataFrame:
        if df_bucket.empty or "assigned_bucket" not in df_bucket.columns:
            return df_bucket
        return df_bucket[df_bucket["assigned_bucket"].astype(str) == bucket_name].copy()

    active_summary = _ensure_bucket(active_summary, "active")
    transferred_summary = _ensure_bucket(transferred_summary, "transferred")
    streamer_summary = _ensure_bucket(streamer_summary, "streamer")
    benched_summary = _ensure_bucket(benched_summary, "benched_academy")

    assigned_top_priority = set(active_summary.get("player", pd.Series(dtype=object)).astype(str).tolist())
    assigned_top_priority |= set(transferred_summary.get("player", pd.Series(dtype=object)).astype(str).tolist())
    assigned_top_priority |= set(streamer_summary.get("player", pd.Series(dtype=object)).astype(str).tolist())
    if not benched_summary.empty:
        benched_summary = benched_summary[~benched_summary["player"].astype(str).isin(assigned_top_priority)].copy()

    if not roster_bucket_debug.empty:
        with st.expander("Roster bucket debug", expanded=False):
            st.dataframe(roster_bucket_debug, use_container_width=True)

    seasons = filters.get("season") or ([f"Season {auto_current_season}"] if auto_current_season else ["All seasons"])
    maps = filters.get("map") or ["All maps"]

    team_logo = image_data_uri(find_team_logo(team_name) or find_team_logo("Medisports"))
    team_logo_html = f"<img class='hero-logo' src='{team_logo}' alt='Medisports logo'/>" if team_logo else ""

    st.markdown("<div class='overview-command-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='section-title overview-command-heading'>Squad Command Hub</div>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class='hero-band overview-hero'>
            <div class='overview-hero-row'>
              <div class='overview-hero-brand'>
                {team_logo_html}
                <div class='overview-hero-copy'>
                  <div class='overview-hero-title'>Live Medisports pulse across map, side, and form context.</div>
                  <div class='overview-hero-meta'>
                  <span class='chip'>Season: {', '.join(map(str, seasons[:2]))}{'…' if len(seasons) > 2 else ''}</span>
                  <span class='chip'>Map scope: {', '.join(map(str, maps[:2]))}{'…' if len(maps) > 2 else ''}</span>
                  </div>
                </div>
              </div>
              <div class='overview-hero-stats'>
                <span class='chip chip-good'>Active: {active_summary['player'].nunique()}</span>
                <span class='chip chip-poor'>Benched/Academy: {benched_summary['player'].nunique()}</span>
                <span class='chip chip-mid'>Streamer: {streamer_summary['player'].nunique()}</span>
                <span class='chip chip-bad'>Transferred Out: {transferred_summary['player'].nunique()}</span>
              </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4, gap="small")
    squad_avg_grev = float(summary["grevscore"].mean()) if not summary.empty else 0.0
    squad_avg_rating = float(summary["rating"].mean()) if not summary.empty else 0.0
    squad_avg_impact = float(summary["impact"].mean()) if not summary.empty else 0.0
    with k1:
        stat_card("Squad Avg GrevScore", f"{squad_avg_grev:.2f}", "Current output index", quality_override=stat_tone("grevscore", squad_avg_grev))
    with k2:
        stat_card("Squad Avg Rating", f"{squad_avg_rating:.2f}", "Form-normalized", quality_override=stat_tone("rating", squad_avg_rating))
    with k3:
        stat_card("Avg Impact", f"{squad_avg_impact:.1f}", "Kills + clutch value", quality_override=stat_tone("impact", squad_avg_impact))
    with k4:
        stat_card("Tracked Matches", int(df["match_id"].nunique()), "Selected context window")
    st.markdown("</div>", unsafe_allow_html=True)

    insight_pool = active_summary if not active_summary.empty else summary
    section_header("Team Pulse", "High-signal summary strip")
    p1, p2, p3, p4 = st.columns(4, gap="small")
    if insight_pool.empty:
        with p1:
            insight_card("Strongest Player", "No stat-tracked players in this filter scope yet.", "info")
        with p2:
            insight_card("Hottest Form", "No form trend data available in this scope.", "info")
        with p3:
            insight_card("Biggest Concern", "No volatility signal available until match stats are present.", "warn")
        with p4:
            insight_card("Avg Team Impact", "Impact summary will appear when match rows are available.", "warn")
    else:
        top_player = insight_pool.sort_values("grevscore", ascending=False).iloc[0]
        improved = insight_pool.sort_values("form", ascending=False).iloc[0]
        coldest = insight_pool.sort_values("form", ascending=True).iloc[0]
        with p1:
            insight_card("Strongest Player", f"{top_player['player']} leads at {top_player['grevscore']:.2f} GrevScore.", "good")
        with p2:
            insight_card("Hottest Form", f"{improved['player']} currently shows the strongest rolling form.", "info")
        with p3:
            insight_card("Biggest Concern", f"{coldest['player']} is in the coldest form window and needs stabilization.", "bad")
        with p4:
            insight_card("Avg Team Impact", f"Team baseline is {squad_avg_impact:.1f} impact per match sample.", "warn")

    section_header("Active Roster")
    if active_summary.empty:
        st.info("No players currently qualify for Active Roster in this filter context.")
    else:
        st.markdown("<div class='roster-section roster-section-main'>", unsafe_allow_html=True)
        _render_roster_cards(active_summary, df, ctx.get("tactics", pd.DataFrame()), players_meta, player_match_counts, team_logo, achievements_df)
        st.markdown("</div>", unsafe_allow_html=True)

    section_header("Benched / Academy")
    if benched_summary.empty:
        st.info("No Benched / Academy players in this filtered context.")
    else:
        st.markdown("<div class='roster-section roster-section-academy'>", unsafe_allow_html=True)
        _render_roster_cards(benched_summary, df, ctx.get("tactics", pd.DataFrame()), players_meta, player_match_counts, team_logo, achievements_df)
        st.markdown("</div>", unsafe_allow_html=True)

    section_header("Streamer")
    if streamer_summary.empty:
        st.info("No streamer players in this filtered context.")
    else:
        st.markdown("<div class='roster-section roster-section-streamer'>", unsafe_allow_html=True)
        _render_roster_cards(streamer_summary, df, ctx.get("tactics", pd.DataFrame()), players_meta, player_match_counts, team_logo, achievements_df, card_variant="streamer")
        st.markdown("</div>", unsafe_allow_html=True)

    if not transferred_summary.empty:
        section_header("Transferred Out")
        st.markdown("<div class='roster-section roster-section-transferred'>", unsafe_allow_html=True)
        _render_roster_cards(
            transferred_summary,
            df,
            ctx.get("tactics", pd.DataFrame()),
            players_meta,
            player_match_counts,
            team_logo,
            achievements_df,
            card_variant="subdued",
            transferred_logo_fallback=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    section_header("Bottom Insights", "Compact coaching cues")
    w1, w2, w3 = st.columns(3, gap="small")
    with w1:
        insight_card("Setup Note", "Anchor early rounds around current high-form duo to preserve conversion rate.", "good")
    with w2:
        insight_card("Risk Note", "Review low-yield side starts where entry impact is trending below baseline.", "warn")
    with w3:
        insight_card("Focus Note", "Use map veto prep to prioritize strongest map clusters from current filter scope.", "info")

    recent_team_matches = _build_recent_team_matches(full_medisports_matches, ctx.get("tactics", pd.DataFrame()), limit=30)
    _render_recent_team_matches(recent_team_matches)
