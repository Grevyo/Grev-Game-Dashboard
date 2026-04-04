import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.datetime_utils import build_match_timestamp, normalize_time_series
from app.page_layout import is_mobile_view


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _fmt_signed(value: float) -> str:
    return f"{int(round(float(value))):+d}"


def _result_label(diff: float) -> str:
    if diff > 0:
        return "Win"
    if diff < 0:
        return "Loss"
    return "Draw"


def _result_short(diff: float) -> str:
    if diff > 0:
        return "W"
    if diff < 0:
        return "L"
    return "D"


def _hero(team_name: str, match_count: int, rounds_count: int) -> None:
    st.markdown(
        f"""
        <div class='hero-band teams-hero'>
            <div class='teams-hero-grid'>
                <div>
                    <div class='section-title teams-hero-kicker'>Single Opponent Dossier</div>
                    <h1 class='teams-hero-title'>Medisports vs Team</h1>
                    <p class='section-subtitle teams-hero-subtitle'>
                        Match-level rivalry intelligence focused on one opponent: series flow, map tendencies, and momentum shifts over time.
                    </p>
                </div>
                <div class='teams-hero-meta'>
                    <span class='chip chip-good'>{team_name}</span>
                    <span class='chip chip-mid'>{match_count} matches</span>
                    <span class='chip'>{rounds_count} rounds tracked</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _kpi_card(title: str, primary: str, secondary: str, accent: str = "good") -> None:
    st.markdown(
        f"""
        <div class='panel panel-tight stat-widget teams-kpi accent-{accent}'>
            <div class='metric-title'>{title}</div>
            <div class='metric-value teams-kpi-value'>{primary}</div>
            <div class='muted'>{secondary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _frame(title: str, subtitle: str = "") -> None:
    st.markdown("<div class='analytics-frame teams-chart-frame'>", unsafe_allow_html=True)
    st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='section-subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def _frame_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def _build_match_level(df: pd.DataFrame) -> pd.DataFrame:
    match_df = (
        df.groupby(["match_id"], dropna=False)
        .agg(
            match_ts=("match_ts", "max"),
            date=("date", "first"),
            time=("time", "first"),
            competition=("competition", "first"),
            map=("map", lambda s: ", ".join(sorted(set(v for v in s.dropna().astype(str) if v))) or "Unknown Map"),
            opponent_team=("opponent_team", "first"),
            tier=("tier", "first"),
            team_score=("wins", "sum"),
            opponent_score=("losses", "sum"),
            rounds=("total_rounds", "sum"),
        )
        .reset_index()
        .sort_values(["match_ts", "match_id"])
    )
    match_df["round_diff"] = match_df["team_score"] - match_df["opponent_score"]
    match_df["result"] = match_df["round_diff"].apply(_result_label)
    match_df["result_short"] = match_df["round_diff"].apply(_result_short)
    match_df["match_no"] = np.arange(1, len(match_df) + 1)
    match_df["cumulative_wins"] = (match_df["result"] == "Win").cumsum()
    match_df["cumulative_losses"] = (match_df["result"] == "Loss").cumsum()
    match_df["cumulative_draws"] = (match_df["result"] == "Draw").cumsum()
    match_df["cumulative_wr"] = match_df["cumulative_wins"] / match_df["match_no"] * 100
    return match_df


def render(ctx):
    tdf = ctx["tactics"]
    mobile_view = is_mobile_view()

    if tdf.empty:
        st.warning("No tactics/opponent data after filters.")
        return

    base = tdf.copy()
    base["opponent_team"] = base.get("opponent_team", "").astype(str).str.strip().replace("", "Unknown Opponent")
    base["map"] = base.get("map", "").astype(str).str.strip().replace("", "Unknown Map")
    base["competition"] = base.get("competition", "").astype(str).str.strip().replace("", "Unknown Event")
    base["tier"] = base.get("tier", "").astype(str).str.strip().replace("", "-")
    base["date"] = base.get("date", "").astype(str).str.strip()
    base["time"] = normalize_time_series(base.get("time", pd.Series([None] * len(base), index=base.index)))
    base["match_ts"] = build_match_timestamp(base["date"], base["time"]).fillna(build_match_timestamp(base["date"]))

    opponents = sorted(base["opponent_team"].dropna().unique().tolist())
    if not opponents:
        st.warning("No opponents available in the current filter context.")
        return

    st.markdown("<div class='panel teams-command-zone'>", unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns([1.3, 1.0, 1.0, 0.9], gap="small")
    with s1:
        selected_team = st.selectbox("Opponent Team", options=opponents, index=0)
    team_scope = base[base["opponent_team"] == selected_team].copy()

    with s2:
        map_options = sorted(team_scope["map"].dropna().unique().tolist())
        selected_maps = st.multiselect("Map Filter", options=map_options, default=map_options)
    with s3:
        competition_options = sorted(team_scope["competition"].dropna().unique().tolist())
        selected_competitions = st.multiselect("Competition Filter", options=competition_options, default=competition_options)
    with s4:
        sort_order = st.selectbox("Match Order", options=["Oldest → Newest", "Newest → Oldest"], index=0)
    st.markdown("</div>", unsafe_allow_html=True)

    scoped = team_scope.copy()
    if selected_maps:
        scoped = scoped[scoped["map"].isin(selected_maps)]
    if selected_competitions:
        scoped = scoped[scoped["competition"].isin(selected_competitions)]

    if scoped.empty:
        st.warning("No matches found for this team with the current filters.")
        return

    matches = _build_match_level(scoped)
    if sort_order == "Newest → Oldest":
        matches = matches.sort_values(["match_ts", "match_id"], ascending=[False, False]).reset_index(drop=True)
    else:
        matches = matches.sort_values(["match_ts", "match_id"], ascending=[True, True]).reset_index(drop=True)

    _hero(selected_team, int(matches["match_id"].nunique()), int(matches["rounds"].sum()))

    wins = int((matches["result"] == "Win").sum())
    losses = int((matches["result"] == "Loss").sum())
    draws = int((matches["result"] == "Draw").sum())
    total_matches = len(matches)
    total_round_won = int(matches["team_score"].sum())
    total_round_lost = int(matches["opponent_score"].sum())
    round_diff = total_round_won - total_round_lost
    win_rate = wins / max(total_matches, 1) * 100

    map_counts = scoped.groupby("map", dropna=False)["match_id"].nunique().sort_values(ascending=False)
    most_played_map = map_counts.index[0] if not map_counts.empty else "-"
    latest_match = matches.sort_values("match_ts", ascending=True).iloc[-1]
    last_result = f"{latest_match['result_short']} • {latest_match['date']} • {latest_match['map']}"
    recent_form = "".join(matches.sort_values("match_ts")["result_short"].tail(6).tolist()) or "-"

    k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8, gap="small")
    with k1:
        _kpi_card("Matches vs Team", str(total_matches), f"{selected_team}", "mid")
    with k2:
        _kpi_card("Wins", str(wins), f"Losses {losses} • Draws {draws}", "good")
    with k3:
        _kpi_card("Match Win Rate", _fmt_pct(win_rate), "Match-level result", "good" if win_rate >= 50 else "bad")
    with k4:
        _kpi_card("Round Differential", _fmt_signed(round_diff), f"{total_round_won}-{total_round_lost}", "good" if round_diff >= 0 else "bad")
    with k5:
        _kpi_card("Most Played Map", most_played_map, f"{int(map_counts.iloc[0]) if not map_counts.empty else 0} matches", "mid")
    with k6:
        _kpi_card("Last Result", latest_match["result_short"], last_result, "mid")
    with k7:
        _kpi_card("Recent Form", recent_form, "Last 6 matches", "mid")
    with k8:
        _kpi_card("Avg Round Diff", f"{matches['round_diff'].mean():+.2f}", "Per match", "mid")

    left, right = st.columns([1.05, 1.0], gap="small")
    with left:
        _frame("Match-by-Match Round Differential", "Each point is one match against the selected opponent.")
        timeline_df = matches.sort_values("match_ts").copy()
        fig_timeline = px.bar(
            timeline_df,
            x="match_no",
            y="round_diff",
            color="result",
            color_discrete_map={"Win": "#9FE870", "Loss": "#ff4d5e", "Draw": "#d3a85c"},
            hover_data={"date": True, "competition": True, "map": True, "team_score": True, "opponent_score": True, "match_id": True, "match_no": False},
            labels={"match_no": "Match Sequence", "round_diff": "Round Differential"},
        )
        fig_timeline.update_layout(template="plotly_dark", height=360 if not mobile_view else 300, margin=dict(l=12, r=12, t=8, b=24), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig_timeline.add_hline(y=0, line_width=1, line_dash="dot", line_color="rgba(159,184,202,0.65)")
        st.plotly_chart(fig_timeline, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()

    with right:
        _frame("Rivalry Flow: Cumulative Win Rate", "Trendline across the match sequence vs this opponent.")
        flow_df = matches.sort_values("match_ts").copy()
        fig_flow = go.Figure()
        fig_flow.add_trace(
            go.Scatter(
                x=flow_df["match_no"],
                y=flow_df["cumulative_wr"],
                mode="lines+markers",
                line=dict(color="#9FE870", width=3),
                marker=dict(size=8, color="#9FE870"),
                customdata=np.stack([flow_df["result"], flow_df["date"], flow_df["map"], flow_df["competition"]], axis=-1),
                hovertemplate="Match %{x}<br>Cumulative WR: %{y:.1f}%<br>Result: %{customdata[0]}<br>Date: %{customdata[1]}<br>Map: %{customdata[2]}<br>Competition: %{customdata[3]}<extra></extra>",
            )
        )
        fig_flow.update_layout(template="plotly_dark", height=360 if not mobile_view else 300, margin=dict(l=12, r=12, t=8, b=24), yaxis_title="Cumulative Match Win Rate", xaxis_title="Match Sequence", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig_flow.update_yaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(fig_flow, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()

    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)

    _frame("Rounds Won vs Lost by Match", "Scoreline pressure per match against this team.")
    score_df = matches.sort_values("match_ts").copy()
    fig_score = go.Figure()
    fig_score.add_trace(go.Bar(name="Rounds Won", x=score_df["match_no"], y=score_df["team_score"], marker_color="#9FE870"))
    fig_score.add_trace(go.Bar(name="Rounds Lost", x=score_df["match_no"], y=score_df["opponent_score"], marker_color="#ff4d5e"))
    fig_score.update_layout(template="plotly_dark", barmode="group", height=330 if not mobile_view else 280, margin=dict(l=12, r=12, t=8, b=24), xaxis_title="Match Sequence", yaxis_title="Rounds", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_score, use_container_width=True, config={"responsive": True, "displayModeBar": True})
    _frame_end()

    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)

    map_stats = (
        scoped.groupby("map", dropna=False)
        .agg(matches=("match_id", "nunique"), rounds_won=("wins", "sum"), rounds_lost=("losses", "sum"))
        .reset_index()
    )
    map_stats["round_diff"] = map_stats["rounds_won"] - map_stats["rounds_lost"]
    map_stats["round_win_rate"] = map_stats["rounds_won"] / (map_stats["rounds_won"] + map_stats["rounds_lost"]).clip(lower=1) * 100
    map_stats = map_stats.sort_values(["matches", "round_diff"], ascending=[False, False])

    ml, mr = st.columns([1.0, 1.0], gap="small")
    with ml:
        _frame("Map Breakdown vs Selected Team", "Win rate by map for this rivalry.")
        fig_map = px.bar(
            map_stats.sort_values("round_win_rate", ascending=True),
            x="round_win_rate",
            y="map",
            orientation="h",
            color="round_diff",
            color_continuous_scale=[[0, "#ff4d5e"], [0.5, "#4c5968"], [1, "#9FE870"]],
            custom_data=["matches", "rounds_won", "rounds_lost", "round_diff"],
            labels={"round_win_rate": "Round Win Rate (%)", "map": "Map"},
        )
        fig_map.update_traces(
            hovertemplate="<b>%{y}</b><br>Round Win Rate: %{x:.1f}%<br>Matches: %{customdata[0]}<br>Rounds W-L: %{customdata[1]}-%{customdata[2]}<br>Round Diff: %{customdata[3]:+}<extra></extra>"
        )
        fig_map.update_layout(template="plotly_dark", height=340 if not mobile_view else 290, margin=dict(l=12, r=12, t=8, b=24), coloraxis_showscale=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig_map.update_xaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(fig_map, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()
    with mr:
        _frame("Recent Form / Skew Check", "Rolling 3-match average round differential to reveal momentum shifts.")
        trend_df = matches.sort_values("match_ts").copy()
        trend_df["rolling_rd_3"] = trend_df["round_diff"].rolling(window=3, min_periods=1).mean()
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(x=trend_df["match_no"], y=trend_df["round_diff"], mode="markers", marker=dict(size=10, color="#d3a85c"), name="Match RD"))
        fig_trend.add_trace(go.Scatter(x=trend_df["match_no"], y=trend_df["rolling_rd_3"], mode="lines", line=dict(width=3, color="#9FE870"), name="Rolling 3-match RD"))
        fig_trend.add_hline(y=0, line_dash="dot", line_color="rgba(159,184,202,0.65)")
        fig_trend.update_layout(template="plotly_dark", height=340 if not mobile_view else 290, margin=dict(l=12, r=12, t=8, b=24), xaxis_title="Match Sequence", yaxis_title="Round Diff", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_trend, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()

    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)

    _frame("Match History Table", "One row per match vs this opponent. Sort directly in-table by any column.")
    table_df = matches.copy()
    table_df["Date"] = pd.to_datetime(table_df["date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna(table_df["date"])
    table_df["Time"] = table_df["time"].fillna("-")
    table_df["Competition"] = table_df["competition"]
    table_df["Map"] = table_df["map"]
    table_df["Opponent"] = table_df["opponent_team"]
    table_df["Team Score"] = table_df["team_score"].astype(int)
    table_df["Opponent Score"] = table_df["opponent_score"].astype(int)
    table_df["Match Result"] = table_df["result_short"]
    table_df["Round Differential"] = table_df["round_diff"].astype(int)
    table_df["Tier"] = table_df["tier"]
    table_df["match_id"] = table_df["match_id"]
    display_cols = [
        "Date",
        "Time",
        "Competition",
        "Map",
        "Opponent",
        "Team Score",
        "Opponent Score",
        "Match Result",
        "Round Differential",
        "Tier",
        "match_id",
    ]
    st.dataframe(table_df[display_cols], use_container_width=True, hide_index=True)
    _frame_end()

    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)

    _frame("Optional Match Detail", "Select a single match for a focused breakdown.")
    selected_match_id = st.selectbox("Select Match", options=matches["match_id"].tolist(), key="vs_team_match_detail")
    selected_match = matches[matches["match_id"] == selected_match_id].iloc[0]
    d1, d2, d3, d4 = st.columns(4, gap="small")
    d1.metric("Result", selected_match["result"])
    d2.metric("Score", f"{int(selected_match['team_score'])}-{int(selected_match['opponent_score'])}")
    d3.metric("Round Diff", _fmt_signed(selected_match["round_diff"]))
    d4.metric("Map", str(selected_match["map"]))
    st.caption(
        f"Date: {selected_match['date']} • Time: {selected_match['time']} • Competition: {selected_match['competition']} • Tier: {selected_match['tier']}"
    )
    _frame_end()
