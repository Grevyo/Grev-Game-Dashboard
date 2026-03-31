import streamlit as st
import pandas as pd
import re

try:
    import plotly.express as px

    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    PLOTLY_AVAILABLE = False

from app.components import render_achievement_mini_tile, section_header, stat_card
from app.achievements import achievements_for_player
from app.data_loader import get_medisports_player_names, get_medisports_roster_df
from app.filters import filter_panel_toggle
from app.image_helpers import image_data_uri, find_team_logo, resolve_player_photo
from app.match_summaries import build_best_n_matches, build_last_n_matches, resolve_match_result
from app.presentation_helpers import is_mobile_view, nationality_label


def _player_key(name: str) -> str:
    return re.sub(r"^ⓜ\s*\|\s*", "", str(name or ""), flags=re.IGNORECASE).strip().casefold()


def _form_delta(p):
    if p.empty or "grevscore" not in p.columns:
        return 0.0
    tail = p.sort_values("date").tail(10)["grevscore"]
    if tail.empty:
        return 0.0
    half = max(1, len(tail) // 2)
    early = tail.head(half).mean()
    recent = tail.tail(half).mean()
    return float(recent - early)


def _true_record(df_scope: pd.DataFrame, tactics_scope: pd.DataFrame) -> tuple[int, int]:
    if df_scope.empty:
        return 0, 0

    wins = 0
    losses = 0
    per_match = df_scope.copy()
    if "match_id" in per_match.columns:
        per_match = per_match.sort_values([c for c in ["date", "time"] if c in per_match.columns]).drop_duplicates("match_id", keep="last")

    for _, row in per_match.iterrows():
        result = resolve_match_result(row, tactics_scope)
        if result == "Win":
            wins += 1
        elif result == "Loss":
            losses += 1
    return wins, losses


def _render_match_list(title: str, matches: list[dict], empty_text: str, block_variant: str = "last"):
    section_header(title)
    if not matches:
        st.markdown(f"<div class='panel panel-tight'><span class='muted'>{empty_text}</span></div>", unsafe_allow_html=True)
        return

    item_class = "match-list-item best" if block_variant == "best" else "match-list-item"
    rows = []
    for item in matches:
        result = str(item.get("result", "")).strip()
        result_key = result.casefold()
        result_tone = "win" if "win" in result_key or result_key == "w" else "loss" if "loss" in result_key or result_key == "l" else "neutral"
        date_label = str(item.get("date_played", "")).strip() or "Unknown date"
        opponent = str(item.get("opponent_team", "")).strip() or "Unknown opponent"
        tournament = str(item.get("tournament", "")).strip()
        rows.append(
            f"<div class='{item_class}'>"
            f"<div class='match-list-head'><span>Played: <strong>{date_label}</strong></span>"
            f"<span class='match-outcome {result_tone}'>{result or 'N/A'}</span></div>"
            f"<div class='match-list-line'>vs <strong>{opponent}</strong>{(' • ' + tournament) if tournament else ''}</div>"
            f"<div class='match-list-line'>KD: <strong>{float(item.get('kpd', 0)):.2f}</strong> • GrevScore: <strong class='match-grev'>{float(item.get('grevscore', 0)):.2f}</strong></div>"
            "</div>"
        )
    st.markdown(f"<div class='match-list-wrap'>{''.join(rows)}</div>", unsafe_allow_html=True)


def _metric_mean(df_scope: pd.DataFrame, column: str, decimals: int = 2) -> str:
    if column not in df_scope.columns:
        return "N/A"
    series = pd.to_numeric(df_scope[column], errors="coerce").dropna()
    if series.empty:
        return "N/A"
    return f"{series.mean():.{decimals}f}"


def _metric_sum(df_scope: pd.DataFrame, column: str) -> str:
    if column not in df_scope.columns:
        return "N/A"
    series = pd.to_numeric(df_scope[column], errors="coerce").dropna()
    if series.empty:
        return "N/A"
    return str(int(series.sum()))


def _render_map_performance_table(p: pd.DataFrame, tactics_scope: pd.DataFrame):
    section_header("Map Performance", "Merged per-map performance view")
    if "map" not in p.columns:
        st.markdown("<div class='panel panel-tight'><span class='muted'>No map column available in this scope.</span></div>", unsafe_allow_html=True)
        return

    maps = p.copy()
    maps["map"] = maps["map"].astype(str).str.strip()
    maps = maps[maps["map"] != ""]
    if maps.empty:
        st.markdown("<div class='panel panel-tight'><span class='muted'>No map data available in this scope.</span></div>", unsafe_allow_html=True)
        return

    include_kd = "kpd" in maps.columns
    include_grevscore = "grevscore" in maps.columns
    include_impact = "impact" in maps.columns
    include_damage = "damage" in maps.columns
    include_accuracy = "accuracy_pct" in maps.columns
    include_hs = "hs_pct" in maps.columns
    include_mvps = "mvps" in maps.columns
    include_adr = {"damage", "rounds_played"}.issubset(maps.columns)

    rows = []
    for map_name, map_df in maps.groupby("map", dropna=False):
        map_df = map_df.copy()
        map_df = map_df.sort_values("date") if "date" in map_df.columns else map_df
        map_tactics = tactics_scope
        if not tactics_scope.empty and "map" in tactics_scope.columns:
            map_tactics = tactics_scope[tactics_scope["map"].astype(str).str.strip() == str(map_name)]

        wins, losses = _true_record(map_df, map_tactics)
        matches = int(map_df["match_id"].nunique()) if "match_id" in map_df.columns else int(len(map_df))
        row = {
            "map": str(map_name),
            "matches": matches,
            "record": f"{wins}-{losses}" if (wins + losses) > 0 else "N/A",
            "kd": _metric_mean(map_df, "kpd", 2) if include_kd else "N/A",
            "grevscore": _metric_mean(map_df, "grevscore", 2) if include_grevscore else "N/A",
            "impact": _metric_mean(map_df, "impact", 1) if include_impact else "N/A",
            "damage": _metric_mean(map_df, "damage", 0) if include_damage else "N/A",
            "accuracy": _metric_mean(map_df, "accuracy_pct", 1) if include_accuracy else "N/A",
            "hs": _metric_mean(map_df, "hs_pct", 1) if include_hs else "N/A",
            "mvps": _metric_sum(map_df, "mvps") if include_mvps else "N/A",
            "adr": "N/A",
        }
        if include_adr:
            rounds_played = float(pd.to_numeric(map_df["rounds_played"], errors="coerce").fillna(0).sum())
            damage = float(pd.to_numeric(map_df["damage"], errors="coerce").fillna(0).sum())
            if rounds_played > 0:
                row["adr"] = f"{(damage / rounds_played):.1f}"
        rows.append(row)

    rows = sorted(rows, key=lambda item: (-item["matches"], item["map"].casefold()))
    headers = [("Map", "map"), ("Matches", "matches"), ("Record", "record")]
    if include_kd:
        headers.append(("KD", "kd"))
    if include_grevscore:
        headers.append(("GrevScore", "grevscore"))
    if include_impact:
        headers.append(("Impact", "impact"))
    if include_adr:
        headers.append(("ADR", "adr"))
    if include_damage:
        headers.append(("Damage", "damage"))
    if include_accuracy:
        headers.append(("Accuracy %", "accuracy"))
    if include_hs:
        headers.append(("HS %", "hs"))
    if include_mvps:
        headers.append(("MVPs", "mvps"))

    header_html = "".join(f"<th>{label}</th>" for label, _ in headers)
    row_html = "".join(
        "<tr class='breakdown-row {row_class}'>".format(row_class="even" if idx % 2 == 0 else "odd")
        + "".join(
            f"<td class='{'breakdown-key' if col_key == 'map' else 'breakdown-num'}'>{str(row.get(col_key, 'N/A'))}</td>"
            for _, col_key in headers
        )
        + "</tr>"
        for idx, row in enumerate(rows)
    )
    st.markdown(
        f"""
        <div class='map-performance-shell'>
          <div class='breakdown-table-wrap map-performance-table-wrap'>
            <table class='breakdown-table map-performance-table'>
              <thead><tr>{header_html}</tr></thead>
              <tbody>{row_html}</tbody>
            </table>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render(ctx):
    df = get_medisports_roster_df(ctx["player_matches"], player_col="player")
    achievements = ctx["achievements"]
    filters = ctx.get("filters", {})
    players = ctx["players"]
    team_name = ctx.get("team_name", "Medisports")
    mobile_view = is_mobile_view()

    if df.empty:
        st.warning("No player data found for current filters.")
        return

    medisports_roster = get_medisports_player_names(df, player_col="player")
    if not medisports_roster:
        st.warning("No Medisports players found in the filtered data yet. Try relaxing global filters.")
        return

    section_header("Player Stats Viewer", "Flagship profile layout for Medisports roster only")

    default_player = medisports_roster[0]
    if st.session_state.get("player_viewer_player") not in medisports_roster:
        st.session_state["player_viewer_player"] = default_player
    if "player_viewer_last_30" not in st.session_state:
        st.session_state["player_viewer_last_30"] = False
    if "player_viewer_expand_profile_filters" not in st.session_state:
        st.session_state["player_viewer_expand_profile_filters"] = False
    if "player_viewer_map_focus" not in st.session_state:
        st.session_state["player_viewer_map_focus"] = []
    if "player_viewer_side_focus" not in st.session_state:
        st.session_state["player_viewer_side_focus"] = []

    panel_visible = filter_panel_toggle("player_viewer")
    if panel_visible:
        with st.container():
            st.markdown("<div class='toolbar-shell'>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([2.3, 1.2, 1.2], gap="small")
            with c1:
                st.selectbox("Select Medisports player", medisports_roster, key="player_viewer_player")
            with c2:
                st.toggle("Last 30-day focus", key="player_viewer_last_30")
            with c3:
                st.toggle("Expand profile filters", key="player_viewer_expand_profile_filters")
            if st.session_state.get("player_viewer_expand_profile_filters", False):
                f1, f2 = st.columns(2, gap="small")
                with f1:
                    st.multiselect("Map focus", sorted(df["map"].dropna().unique().tolist()) if "map" in df.columns else [], key="player_viewer_map_focus")
                with f2:
                    st.multiselect("Side focus", sorted(df["side"].dropna().unique().tolist()) if "side" in df.columns else [], key="player_viewer_side_focus")
            st.markdown("</div>", unsafe_allow_html=True)

    player = st.session_state.get("player_viewer_player", default_player)
    show_recent = bool(st.session_state.get("player_viewer_last_30", False))
    map_focus = st.session_state.get("player_viewer_map_focus", []) if st.session_state.get("player_viewer_expand_profile_filters", False) else []
    side_focus = st.session_state.get("player_viewer_side_focus", []) if st.session_state.get("player_viewer_expand_profile_filters", False) else []

    mask = df["player"] == player
    if show_recent and "date" in df.columns:
        cutoff = df["date"].max() - pd.Timedelta(days=30)
        mask &= df["date"] >= cutoff
    if map_focus and "map" in df.columns:
        mask &= df["map"].isin(map_focus)
    if side_focus and "side" in df.columns:
        mask &= df["side"].isin(side_focus)

    p = df[mask].sort_values("date")
    if p.empty:
        st.warning("Selected player has no rows in current profile scope.")
        return

    meta_source = players.get("player_clean", players.get("player", players.get("name", ""))).astype(str).map(_player_key)
    meta = players[meta_source == _player_key(player)]
    country = str(meta.iloc[0].get("country", "")).strip() if not meta.empty else ""
    nationality = str(meta.iloc[0].get("nationality", "")).strip() if not meta.empty else ""
    nation_value = nationality or country
    nation_label = nationality_label(nation_value) or "Nationality N/A"
    role = str(meta.iloc[0].get("role", "")).strip() if not meta.empty else ""

    tactics_scope = ctx.get("tactics", pd.DataFrame())
    if not tactics_scope.empty and "match_id" in p.columns and "match_id" in tactics_scope.columns:
        match_ids = p["match_id"].dropna().astype(str).unique().tolist()
        tactics_scope = tactics_scope[tactics_scope["match_id"].astype(str).isin(match_ids)].copy()

    best_map_value = "N/A"
    if not tactics_scope.empty and {"map", "side", "wins"}.issubset(tactics_scope.columns):
        best_map_subset = tactics_scope.copy()
        best_map_subset["map"] = best_map_subset["map"].astype(str).str.strip()
        best_map_subset["side"] = best_map_subset["side"].astype(str).str.strip()
        best_map_subset["wins"] = pd.to_numeric(best_map_subset["wins"], errors="coerce").fillna(0)
        best_map_subset = best_map_subset[(best_map_subset["map"] != "") & (best_map_subset["side"].isin(["Red", "Blue"]))]
        if not best_map_subset.empty:
            best_map_grouped = (
                best_map_subset.groupby(["map", "side"], dropna=False)["wins"]
                .sum()
                .unstack(fill_value=0)
                .reindex(columns=["Red", "Blue"], fill_value=0)
            )
            best_map_grouped["total_wins"] = best_map_grouped["Red"] + best_map_grouped["Blue"]
            best_map_grouped = best_map_grouped[best_map_grouped["total_wins"] > 0]
            if not best_map_grouped.empty:
                best_map_value = str(best_map_grouped["total_wins"].idxmax()).strip() or "N/A"

    best_side_label = "N/A"
    if not tactics_scope.empty and {"side", "wins"}.issubset(tactics_scope.columns):
        best_side_subset = tactics_scope.copy()
        best_side_subset["side"] = best_side_subset["side"].astype(str).str.strip()
        best_side_subset["wins"] = pd.to_numeric(best_side_subset["wins"], errors="coerce").fillna(0)
        best_side_subset = best_side_subset[best_side_subset["side"].isin(["Red", "Blue"])]
        if not best_side_subset.empty:
            side_wins = (
                best_side_subset.groupby("side", dropna=False)["wins"]
                .sum()
                .reindex(["Red", "Blue"], fill_value=0)
            )
            red_wins = float(side_wins.get("Red", 0))
            blue_wins = float(side_wins.get("Blue", 0))
            if red_wins > blue_wins:
                best_side_label = "Red"
            elif blue_wins > red_wins:
                best_side_label = "Blue"
            elif red_wins > 0 or blue_wins > 0:
                best_side_label = "Even"

    delta_10 = _form_delta(p)
    trend = "Heating Up" if delta_10 > 2 else "Cooling" if delta_10 < -2 else "Stable"
    wins, losses = _true_record(p, tactics_scope)
    record_value = f"{wins}-{losses}"
    adr = p["damage"].sum() / p["rounds_played"].sum() if p["rounds_played"].sum() > 0 else 0.0
    grev_avg = float(p["grevscore"].mean())
    grev_pct = max(0.0, min((grev_avg / 2.0) * 100.0, 100.0))

    player_photo_match = resolve_player_photo(player)
    player_photo = image_data_uri(player_photo_match.get("path"))
    team_logo = image_data_uri(find_team_logo(team_name) or find_team_logo("Medisports"))
    hero_photo = (
        f"<div class='hero-player-photo-frame'><img class='hero-player-photo' src='{player_photo}' alt='Player photo'/></div>"
        if player_photo
        else f"<div class='hero-player-photo-frame'><div class='player-avatar fallback-avatar'>No Photo ({player_photo_match.get('reason', 'not found')})</div></div>"
    )
    hero_logo = f"<img class='hero-logo' src='{team_logo}' alt='Medisports logo'/>" if team_logo else ""

    st.markdown(
        f"""
        <div class='hero-band player-viewer-hero'>
          <div class='player-viewer-hero-grid'>
            <div class='player-viewer-head-main'>
              {hero_photo}
              <div class='player-viewer-head-body'>
                <div class='player-viewer-player-title'>{player}</div>
                <div class='player-viewer-player-meta'>{nation_label} • {role if role else 'Core Roster'} • {team_name}</div>
                <div class='player-viewer-chip-row'>
                  <span class='chip'>Role: {role if role else 'N/A'}</span>
                  <span class='chip'>Record: {record_value}</span>
                  <span class='chip chip-good'>Best Map: {best_map_value}</span>
                  <span class='chip chip-mid'>Best Side: {best_side_label}</span>
                </div>
                <div class='muted player-viewer-form-note'>Current form summary: {player} is {trend.lower()} with a {grev_avg:.1f} GrevScore baseline in this scope.</div>
              </div>
            </div>
            <div class='player-viewer-gauge-panel'>
              <div class='player-viewer-gauge-header'>
                <div class='section-title player-viewer-mini-title'>GrevScore Gauge</div>
                {hero_logo}
              </div>
              <div class='player-viewer-gauge-wrap'>
                <div class='grev-gauge' style="--gauge-pct:{grev_pct:.1f}%;">
                  <div class='grev-gauge-inner'>
                    <div class='metric-title'>GrevScore</div>
                    <div class='metric-value'>{grev_avg:.2f}</div>
                  </div>
                </div>
              </div>
              <div class='muted'>Bands: Super 1.20+ • Good 1.00–1.19 • Meh 0.76–0.99 • Bad ≤0.75</div>
            </div>
          </div>
          <div class='player-viewer-top-metrics'>
            <div class='panel panel-tight accent-good'><div class='metric-title'>Record</div><div class='metric-value'>{record_value}</div></div>
            <div class='panel panel-tight accent-mid'><div class='metric-title'>KD</div><div class='metric-value'>{p['kpd'].mean():.2f}</div></div>
            <div class='panel panel-tight accent-mid'><div class='metric-title'>GrevScore</div><div class='metric-value'>{grev_avg:.2f}</div></div>
            <div class='panel panel-tight accent-mid'><div class='metric-title'>Impact</div><div class='metric-value'>{p['impact'].mean():.1f}</div></div>
            <div class='panel panel-tight accent-mid'><div class='metric-title'>ADR</div><div class='metric-value'>{adr:.1f}</div></div>
            <div class='panel panel-tight accent-mid'><div class='metric-title'>KPR</div><div class='metric-value'>{p['kpr'].mean():.2f}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    section_header("Achievements", "Newest-to-oldest by season, aligned with overview card logic")
    ach_items, ach_hidden = achievements_for_player(achievements, player, cap=6, consumer="overview")
    if not ach_items:
        st.caption("No achievements linked for selected player.")
    else:
        ach_html = "".join(render_achievement_mini_tile(a, size_variant="viewer") for a in ach_items)
        st.markdown(f"<div class='achievement-strip achievement-strip-viewer'>{ach_html}</div>", unsafe_allow_html=True)
        if ach_hidden:
            st.markdown(f"<div class='muted'>+{ach_hidden} more achievements not shown here.</div>", unsafe_allow_html=True)

    section_header("Match Summary", "Expanded match context from the overview cards")
    last_five_matches = build_last_n_matches(df, ctx.get("tactics", pd.DataFrame()), player, n=5)
    best_five_matches = build_best_n_matches(df, ctx.get("tactics", pd.DataFrame()), player, n=5)
    m1, m2 = st.columns(2, gap="small")
    with m1:
        _render_match_list("Last 5 Matches", last_five_matches, "No recent matches in this scope", block_variant="last")
    with m2:
        _render_match_list("Best 5 Matches", best_five_matches, "No best matches in this scope", block_variant="best")

    section_header("Performance Core", "GrevScore feature and headline cards")
    left, right = st.columns([1.3, 1], gap="small")
    with left:
        stat_card("Signature GrevScore", f"{p['grevscore'].mean():.1f}", "Primary contribution signal", "good")
        if PLOTLY_AVAILABLE:
            fig = px.line(p, x="date", y="grevscore", title="GrevScore Trend", markers=True)
            fig.update_traces(line_color="#21c77a")
            fig.update_layout(
                height=280 if mobile_view else 320,
                margin=dict(l=12 if mobile_view else 16, r=12, t=56, b=40 if mobile_view else 44),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                hovermode="x unified",
                hoverlabel=dict(namelength=-1),
            )
            fig.update_xaxes(automargin=True, tickangle=0, tickfont=dict(size=10 if mobile_view else 11))
            fig.update_yaxes(automargin=True, tickfont=dict(size=10 if mobile_view else 11))
            st.plotly_chart(fig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        else:
            st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    with right:
        g1, g2 = st.columns(2, gap="small")
        with g1:
            stat_card("Rating", f"{p['rating'].mean():.2f}", "Composite consistency")
            stat_card("K/D", f"{p['kpd'].mean():.2f}", "Elimination efficiency")
        with g2:
            stat_card("Impact", f"{p['impact'].mean():.1f}", "Round influence")
            stat_card("Headshot %", f"{p['hs_pct'].mean():.1f}%", "Precision profile")

    section_header("Core Stats Grid", "Balanced compact stat matrix")
    s1, s2, s3, s4 = st.columns(4, gap="small")
    with s1:
        stat_card("Matches", int(p["match_id"].nunique()), "In current profile scope")
    with s2:
        stat_card("Avg Accuracy", f"{p['accuracy_pct'].mean():.1f}%", "Shot reliability")
    with s3:
        stat_card("Avg KPR", f"{p['kpr'].mean():.2f}", "Kills per round")
    with s4:
        stat_card("MVPs", int(p.get("mvps", 0).sum()), "Total MVPs captured")

    _render_map_performance_table(p, tactics_scope)
