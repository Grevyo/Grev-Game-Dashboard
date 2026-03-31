import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.metrics import confidence_from_sample
from app.page_layout import is_mobile_view


HEATMAP_RED_GREEN_SCALE = [
    [0.0, "#7f1d1d"],
    [0.5, "#3f4a3f"],
    [1.0, "#166534"],
]


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _fmt_signed(value: float) -> str:
    return f"{int(round(float(value))):+d}"


def _hero(total_opponents: int, total_matches: int, total_rounds: int) -> None:
    st.markdown(
        f"""
        <div class='hero-band teams-hero'>
            <div class='teams-hero-grid'>
                <div>
                    <div class='section-title teams-hero-kicker'>Opponent Intelligence Surface</div>
                    <h1 class='teams-hero-title'>Medisports vs Teams</h1>
                    <p class='section-subtitle teams-hero-subtitle'>
                        Premium matchup command board for opponent quality, map pressure points, and sample-backed confidence.
                    </p>
                </div>
                <div class='teams-hero-meta'>
                    <span class='chip chip-good'>{total_opponents} opponents tracked</span>
                    <span class='chip chip-mid'>{total_matches} matches</span>
                    <span class='chip'>{total_rounds} rounds logged</span>
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


def _build_views(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    match_level = (
        base.groupby(["opponent_team", "match_id"], dropna=False)
        .agg(
            match_ts=("match_ts", "max"),
            map_count=("map", "nunique"),
            round_wins=("wins", "sum"),
            round_losses=("losses", "sum"),
            rounds=("total_rounds", "sum"),
            primary_map=("map", lambda s: str(s.dropna().iloc[0]) if len(s.dropna()) else "Unknown Map"),
        )
        .reset_index()
    )
    match_level["match_diff"] = match_level["round_wins"] - match_level["round_losses"]
    match_level["match_win"] = (match_level["match_diff"] > 0).astype(int)
    match_level["match_loss"] = (match_level["match_diff"] < 0).astype(int)
    match_level["match_draw"] = (match_level["match_diff"] == 0).astype(int)
    match_level["result"] = match_level["match_diff"].apply(lambda x: "W" if x > 0 else "L" if x < 0 else "D")

    grp = (
        match_level.groupby("opponent_team", dropna=False)
        .agg(
            matches_played=("match_id", "nunique"),
            wins=("match_win", "sum"),
            losses=("match_loss", "sum"),
            draws=("match_draw", "sum"),
            round_wins=("round_wins", "sum"),
            round_losses=("round_losses", "sum"),
            round_diff=("match_diff", "sum"),
            rounds=("rounds", "sum"),
            volatility=("match_diff", "std"),
        )
        .reset_index()
    )
    grp["volatility"] = grp["volatility"].fillna(0)
    grp["win_rate_match"] = (grp["wins"] / grp["matches_played"].clip(lower=1) * 100).fillna(0)
    grp["win_rate_rounds"] = (grp["round_wins"] / (grp["round_wins"] + grp["round_losses"]).clip(lower=1) * 100).fillna(0)
    grp["confidence"] = grp["rounds"].map(confidence_from_sample)
    grp["danger_index"] = ((100 - grp["win_rate_match"]) * (1 + 2 / np.sqrt(grp["matches_played"].clip(lower=1)))).round(1)

    recent_form = (
        match_level.sort_values("match_ts")
        .groupby("opponent_team", dropna=False)
        .tail(5)[["opponent_team", "result", "match_ts"]]
    )

    def _form_line(sub: pd.DataFrame) -> str:
        return "".join(sub.sort_values("match_ts")["result"].tolist())[-5:] or "-"

    form_df = recent_form.groupby("opponent_team", dropna=False).apply(_form_line).rename("recent_form").reset_index()
    grp = grp.merge(form_df, on="opponent_team", how="left")

    latest = (
        match_level.sort_values("match_ts")
        .groupby("opponent_team", dropna=False)
        .tail(1)[["opponent_team", "result", "match_ts", "primary_map"]]
    )
    latest["latest_result_label"] = (
        latest["result"].fillna("-")
        + " • "
        + latest["match_ts"].dt.strftime("%Y-%m-%d").fillna("n/a")
        + " • "
        + latest["primary_map"].fillna("n/a")
    )
    grp = grp.merge(latest[["opponent_team", "latest_result_label", "match_ts"]], on="opponent_team", how="left")

    map_team = (
        base.groupby(["opponent_team", "map"], dropna=False)
        .agg(
            rounds_won=("wins", "sum"),
            rounds_lost=("losses", "sum"),
            match_wins=("wins", lambda s: 0),
            matches=("match_id", "nunique"),
        )
        .reset_index()
    )
    map_match = (
        match_level.groupby(["opponent_team", "primary_map"], dropna=False)
        .agg(match_wins=("match_win", "sum"), match_losses=("match_loss", "sum"), match_draws=("match_draw", "sum"), matches=("match_id", "nunique"))
        .reset_index()
        .rename(columns={"primary_map": "map"})
    )
    map_team = map_team.drop(columns=["match_wins", "matches"]).merge(map_match, on=["opponent_team", "map"], how="outer")
    for c in ["rounds_won", "rounds_lost", "match_wins", "match_losses", "match_draws", "matches"]:
        map_team[c] = map_team[c].fillna(0)

    map_team["round_diff"] = map_team["rounds_won"] - map_team["rounds_lost"]
    map_team["round_win_pct"] = (map_team["rounds_won"] / (map_team["rounds_won"] + map_team["rounds_lost"]).clip(lower=1) * 100).fillna(0)
    map_team["match_diff"] = map_team["match_wins"] - map_team["match_losses"]
    map_team["match_win_pct"] = (map_team["match_wins"] / map_team["matches"].clip(lower=1) * 100).fillna(0)

    map_rank = map_team.copy()
    map_rank["score"] = map_rank["match_win_pct"] + map_rank["round_diff"].clip(-20, 20) * 0.6
    most_played = (
        map_team.sort_values(["opponent_team", "matches", "round_diff"], ascending=[True, False, False])
        .groupby("opponent_team", dropna=False)
        .head(1)[["opponent_team", "map"]]
        .rename(columns={"map": "most_played_map"})
    )
    best_map = (
        map_rank.sort_values(["opponent_team", "score", "matches"], ascending=[True, False, False])
        .groupby("opponent_team", dropna=False)
        .head(1)[["opponent_team", "map"]]
        .rename(columns={"map": "best_map"})
    )
    worst_map = (
        map_rank.sort_values(["opponent_team", "score", "matches"], ascending=[True, True, False])
        .groupby("opponent_team", dropna=False)
        .head(1)[["opponent_team", "map"]]
        .rename(columns={"map": "worst_map"})
    )
    grp = grp.merge(most_played, on="opponent_team", how="left").merge(best_map, on="opponent_team", how="left").merge(worst_map, on="opponent_team", how="left")

    return grp, match_level, map_team


def _render_heatmap(pivot: pd.DataFrame, metric_label: str, mobile_view: bool, zmin=None, zmax=None, zmid=None) -> None:
    if pivot.empty:
        st.info("No heatmap data for current filters.")
        return
    team_count = len(pivot.index)
    map_count = len(pivot.columns)
    max_team_len = max((len(str(v)) for v in pivot.index), default=12)
    max_map_len = max((len(str(v)) for v in pivot.columns), default=8)
    left_margin = min(460, 94 + max_team_len * (7 if not mobile_view else 5))
    height = max(540 if not mobile_view else 440, min(3400, 280 + team_count * (40 if not mobile_view else 33)))

    fig = px.imshow(
        pivot.apply(pd.to_numeric, errors="coerce").fillna(0),
        aspect="auto",
        color_continuous_scale=HEATMAP_RED_GREEN_SCALE,
        labels={"x": "Map", "y": "Opponent", "color": metric_label},
        text_auto=".1f",
    )
    if zmin is not None and zmax is not None:
        fig.update_coloraxes(cmin=zmin, cmax=zmax)
    if zmid is not None:
        fig.update_coloraxes(cmid=zmid)

    fig.update_traces(textfont={"color": "#F2F6FF", "size": 9 if mobile_view else 11})
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(
            l=left_margin,
            r=12,
            t=16,
            b=max(94, 72 + max_map_len * 2),
        ),
        xaxis=dict(tickangle=-32 if map_count > 4 else 0, automargin=True, tickfont=dict(size=10 if mobile_view else 12)),
        yaxis=dict(automargin=True, tickfont=dict(size=10 if mobile_view else 12), categoryorder="array", categoryarray=list(pivot.index)),
        coloraxis_colorbar=dict(len=0.86, thickness=14),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    st.markdown("<div class='heatmap-stage'>", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
    st.markdown("</div>", unsafe_allow_html=True)


def render(ctx):
    tdf = ctx["tactics"]
    mobile_view = is_mobile_view()

    if tdf.empty:
        st.warning("No tactics/opponent data after filters.")
        return

    base = tdf.copy()
    base["opponent_team"] = base.get("opponent_team", "").astype(str).str.strip().replace("", "Unknown Opponent")
    base["map"] = base.get("map", "").astype(str).str.strip().replace("", "Unknown Map")
    base["date"] = base.get("date", "").astype(str).str.strip()
    base["time"] = base.get("time", "").astype(str).str.strip()
    base["match_ts"] = pd.to_datetime((base["date"] + " " + base["time"]).str.strip(), errors="coerce")

    _hero(
        total_opponents=int(base["opponent_team"].nunique()),
        total_matches=int(base["match_id"].nunique()),
        total_rounds=int(base["total_rounds"].sum()),
    )

    grp_all, _, _ = _build_views(base)

    st.markdown("<div class='panel teams-command-zone'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.15, 1.25, 1.2, 1.15], gap="small")
    with c1:
        min_matches = st.slider(
            "Minimum Matches",
            min_value=1,
            max_value=max(1, int(grp_all["matches_played"].max())),
            value=1,
            step=1,
            help="Filter out low-sample opponents.",
        )
    with c2:
        map_options = sorted(base["map"].dropna().unique().tolist())
        selected_maps = st.multiselect(
            "Map Context",
            options=map_options,
            default=map_options,
            help="Limit analysis to selected maps.",
        )
    with c3:
        focus_top_n = st.select_slider("Focus Window", options=[8, 10, 12, 16, 20, 30], value=12)
    with c4:
        primary_sort = st.selectbox(
            "Primary Sort",
            options=["Win Rate", "Round Differential", "Sample Size", "Volatility", "Danger Index"],
            index=0,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    if selected_maps:
        base = base[base["map"].isin(selected_maps)].copy()

    grp, match_level, map_team = _build_views(base)
    grp = grp[grp["matches_played"] >= int(min_matches)].copy()
    if grp.empty:
        st.warning("No opponents meet the current filter thresholds.")
        return

    sort_map = {
        "Win Rate": ["win_rate_match", "matches_played"],
        "Round Differential": ["round_diff", "matches_played"],
        "Sample Size": ["matches_played", "win_rate_match"],
        "Volatility": ["volatility", "matches_played"],
        "Danger Index": ["danger_index", "matches_played"],
    }
    scoped = grp.sort_values(sort_map[primary_sort], ascending=False).copy()
    top = scoped.head(int(focus_top_n)).copy()

    best_wr = scoped.sort_values(["win_rate_match", "matches_played"], ascending=[False, False]).head(1).iloc[0]
    worst_wr = scoped.sort_values(["win_rate_match", "matches_played"], ascending=[True, False]).head(1).iloc[0]
    most_played = scoped.sort_values("matches_played", ascending=False).head(1).iloc[0]
    best_rd = scoped.sort_values("round_diff", ascending=False).head(1).iloc[0]
    worst_rd = scoped.sort_values("round_diff", ascending=True).head(1).iloc[0]
    volatile = scoped.sort_values("volatility", ascending=False).head(1).iloc[0]
    high_sample = scoped.sort_values("rounds", ascending=False).head(1).iloc[0]

    k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8, gap="small")
    with k1:
        _kpi_card("Best Opponent WR", _fmt_pct(best_wr["win_rate_match"]), str(best_wr["opponent_team"]), "good")
    with k2:
        _kpi_card("Worst Opponent WR", _fmt_pct(worst_wr["win_rate_match"]), str(worst_wr["opponent_team"]), "bad")
    with k3:
        _kpi_card("Most Played", f"{int(most_played['matches_played'])}", str(most_played["opponent_team"]), "mid")
    with k4:
        _kpi_card("Best Round Diff", _fmt_signed(best_rd["round_diff"]), str(best_rd["opponent_team"]), "good")
    with k5:
        _kpi_card("Worst Round Diff", _fmt_signed(worst_rd["round_diff"]), str(worst_rd["opponent_team"]), "bad")
    with k6:
        _kpi_card("Most Volatile", f"{volatile['volatility']:.2f}", str(volatile["opponent_team"]), "poor")
    with k7:
        _kpi_card("Highest Sample", f"{int(high_sample['rounds'])} rds", str(high_sample["opponent_team"]), "mid")
    with k8:
        _kpi_card("Opponents Faced", f"{int(scoped['opponent_team'].nunique())}", "After filters", "mid")

    left, right = st.columns([1.15, 1], gap="small")
    with left:
        _frame("Win Rate by Opponent", f"Top {len(top)} opponents by {primary_sort.lower()}.")
        wr_fig = px.bar(
            top.sort_values("win_rate_match", ascending=True),
            x="win_rate_match",
            y="opponent_team",
            orientation="h",
            color="win_rate_match",
            text=top.sort_values("win_rate_match", ascending=True)["matches_played"].map(lambda x: f"{int(x)} m"),
            color_continuous_scale=["#ff4d5e", "#d3a85c", "#9FE870"],
        )
        wr_fig.update_layout(template="plotly_dark", height=560 if not mobile_view else 440, margin=dict(l=12, r=12, t=8, b=32), coloraxis_showscale=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        wr_fig.update_xaxes(range=[0, 100], ticksuffix="%", gridcolor="rgba(133,147,163,0.24)")
        wr_fig.update_yaxes(automargin=True)
        st.plotly_chart(wr_fig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()
    with right:
        _frame("Sample Size vs Win Rate vs Round Diff", "Bubble size = matches, color = round differential")
        scatter = px.scatter(
            scoped,
            x="rounds",
            y="win_rate_match",
            size="matches_played",
            color="round_diff",
            hover_name="opponent_team",
            text="opponent_team",
            color_continuous_scale=["#ff4d5e", "#d3a85c", "#9FE870"],
        )
        scatter.update_traces(textposition="top center", textfont=dict(size=10), marker=dict(line=dict(color="rgba(231,241,255,.8)", width=1.4), opacity=0.82))
        scatter.update_layout(template="plotly_dark", height=560 if not mobile_view else 440, margin=dict(l=12, r=12, t=8, b=32), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        scatter.update_yaxes(range=[0, 100], ticksuffix="%", gridcolor="rgba(133,147,163,0.24)")
        scatter.update_xaxes(gridcolor="rgba(133,147,163,0.24)")
        st.plotly_chart(scatter, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()

    row2_left, row2_right = st.columns(2, gap="small")
    with row2_left:
        _frame("Wins / Losses / Draws by Opponent", "Outcome stack across highest-sample opponents")
        stacked = scoped.sort_values("matches_played", ascending=False).head(12)
        fig_stack = go.Figure()
        fig_stack.add_trace(go.Bar(y=stacked["opponent_team"], x=stacked["wins"], name="Wins", orientation="h", marker_color="#9FE870"))
        fig_stack.add_trace(go.Bar(y=stacked["opponent_team"], x=stacked["losses"], name="Losses", orientation="h", marker_color="#ff4d5e"))
        fig_stack.add_trace(go.Bar(y=stacked["opponent_team"], x=stacked["draws"], name="Draws", orientation="h", marker_color="#9fb4ca"))
        fig_stack.update_layout(barmode="stack", template="plotly_dark", height=440 if not mobile_view else 360, margin=dict(l=12, r=12, t=8, b=32), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig_stack.update_yaxes(autorange="reversed", automargin=True)
        st.plotly_chart(fig_stack, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()
    with row2_right:
        _frame("Round Differential by Opponent", "Where scoreline margin disagrees with simple win rate")
        rd_df = top.sort_values("round_diff", ascending=True)
        rd_fig = px.bar(rd_df, x="round_diff", y="opponent_team", orientation="h", color="round_diff", color_continuous_scale=[[0, "#ff4d5e"], [0.48, "#4c5968"], [1, "#9FE870"]])
        rd_fig.update_layout(template="plotly_dark", height=440 if not mobile_view else 360, margin=dict(l=12, r=12, t=8, b=32), coloraxis_showscale=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        rd_fig.update_yaxes(automargin=True)
        rd_fig.update_xaxes(gridcolor="rgba(133,147,163,0.24)")
        st.plotly_chart(rd_fig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()

    st.markdown("<div class='section-title'>Opponent × Map Heatmap Lab</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Full-roster matchup matrix with dynamic height, readable labels, and analyst sorting controls.</div>", unsafe_allow_html=True)

    st.markdown("<div class='heatmap-stage--fullbleed'>", unsafe_allow_html=True)
    s1, s2 = st.columns([1.15, 1.1], gap="small")
    with s1:
        sort_choice = st.selectbox(
            "Team sort order",
            ["Alphabetical", "Matches played", "Win rate", "Round differential", "Total wins", "Selected heatmap metric"],
            key="vs_teams_heatmap_sort_order",
        )
    with s2:
        metric_choice = st.selectbox(
            "Heatmap metric",
            ["Round Win/Lose by Team and Map", "Round Win % by Team and Map", "Match Win/Lose by Team and Map", "Match Win % by Team and Map"],
            key="vs_teams_heatmap_metric_sort_target",
        )

    map_order = map_team.groupby("map", dropna=False)["matches"].sum().sort_values(ascending=False).index.tolist()
    base_index = grp.set_index("opponent_team")
    if sort_choice == "Alphabetical":
        team_order = sorted(base_index.index.tolist(), key=lambda x: str(x).lower())
    elif sort_choice == "Matches played":
        team_order = base_index.sort_values(["matches_played", "opponent_team"], ascending=[False, True]).index.tolist()
    elif sort_choice == "Win rate":
        team_order = base_index.sort_values(["win_rate_match", "opponent_team"], ascending=[False, True]).index.tolist()
    elif sort_choice == "Round differential":
        team_order = base_index.sort_values(["round_diff", "opponent_team"], ascending=[False, True]).index.tolist()
    elif sort_choice == "Total wins":
        team_order = base_index.sort_values(["wins", "opponent_team"], ascending=[False, True]).index.tolist()
    else:
        metric_map = {
            "Round Win/Lose by Team and Map": ("round_diff", "sum"),
            "Round Win % by Team and Map": ("round_win_pct", "mean"),
            "Match Win/Lose by Team and Map": ("match_diff", "sum"),
            "Match Win % by Team and Map": ("match_win_pct", "mean"),
        }
        mcol, magg = metric_map[metric_choice]
        g = map_team.groupby("opponent_team", dropna=False)[mcol]
        scores = g.sum() if magg == "sum" else g.mean()
        team_order = scores.reindex(base_index.index).fillna(0).sort_values(ascending=False).index.tolist()

    def _pivot(value_col: str) -> pd.DataFrame:
        return (
            map_team.pivot(index="opponent_team", columns="map", values=value_col)
            .reindex(index=team_order, columns=map_order)
            .fillna(0)
        )

    p_rd = _pivot("round_diff")
    p_rwp = _pivot("round_win_pct")
    p_md = _pivot("match_diff")
    p_mwp = _pivot("match_win_pct")

    metric_lookup = {
        "Round Win/Lose by Team and Map": (p_rd, "Round Diff", float(p_rd.abs().to_numpy().max()) if not p_rd.empty else 0.0, 0),
        "Round Win % by Team and Map": (p_rwp, "Round Win %", 100.0, 50),
        "Match Win/Lose by Team and Map": (p_md, "Match Diff", float(p_md.abs().to_numpy().max()) if not p_md.empty else 0.0, 0),
        "Match Win % by Team and Map": (p_mwp, "Match Win %", 100.0, 50),
    }
    pivot, label, upper, mid = metric_lookup[metric_choice]
    if mid == 0:
        _render_heatmap(pivot, label, mobile_view, zmin=-upper if upper else None, zmax=upper if upper else None, zmid=0)
    else:
        _render_heatmap(pivot, label, mobile_view, zmin=0, zmax=upper, zmid=mid)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Opponent Matchup Table</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Sortable scouting ledger with sample quality and map context per opponent.</div>", unsafe_allow_html=True)

    table = scoped.copy()
    table["Last Played"] = table["match_ts"].dt.strftime("%Y-%m-%d").fillna("-")
    st.markdown("<div class='table-frame teams-table-shell'>", unsafe_allow_html=True)
    st.dataframe(
        table[
            [
                "opponent_team",
                "matches_played",
                "wins",
                "losses",
                "draws",
                "win_rate_match",
                "round_diff",
                "round_wins",
                "round_losses",
                "most_played_map",
                "best_map",
                "worst_map",
                "recent_form",
                "confidence",
                "Last Played",
            ]
        ].rename(
            columns={
                "opponent_team": "Opponent",
                "matches_played": "Matches",
                "wins": "Wins",
                "losses": "Losses",
                "draws": "Draws",
                "win_rate_match": "Win Rate",
                "round_diff": "Round Diff",
                "round_wins": "Rounds Won",
                "round_losses": "Rounds Lost",
                "most_played_map": "Most Played Map",
                "best_map": "Best Map",
                "worst_map": "Worst Map",
                "recent_form": "Recent Form",
                "confidence": "Confidence",
            }
        ),
        hide_index=True,
        use_container_width=True,
        key="match_record_vs_teams_table",
        column_config={
            "Opponent": st.column_config.TextColumn("Opponent", width="large"),
            "Matches": st.column_config.NumberColumn("Matches", format="%d"),
            "Wins": st.column_config.NumberColumn("Wins", format="%d"),
            "Losses": st.column_config.NumberColumn("Losses", format="%d"),
            "Draws": st.column_config.NumberColumn("Draws", format="%d"),
            "Win Rate": st.column_config.ProgressColumn("Win Rate", min_value=0.0, max_value=100.0, format="%.1f%%"),
            "Round Diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
            "Rounds Won": st.column_config.NumberColumn("Rounds Won", format="%d"),
            "Rounds Lost": st.column_config.NumberColumn("Rounds Lost", format="%d"),
            "Most Played Map": st.column_config.TextColumn("Most Played Map"),
            "Best Map": st.column_config.TextColumn("Best Map"),
            "Worst Map": st.column_config.TextColumn("Worst Map"),
            "Recent Form": st.column_config.TextColumn("Recent Form"),
            "Confidence": st.column_config.TextColumn("Confidence"),
            "Last Played": st.column_config.TextColumn("Last Played"),
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Opponent Deep-Dive Scouting</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Investigate map-specific pressure points, recent results, and reliability for one selected matchup.</div>", unsafe_allow_html=True)

    opponent_options = scoped.sort_values(["matches_played", "win_rate_match"], ascending=[False, False])["opponent_team"].tolist()
    selected = st.selectbox("Select Opponent", options=opponent_options, index=0)

    s_grp = scoped[scoped["opponent_team"] == selected].head(1)
    s_match = match_level[match_level["opponent_team"] == selected].sort_values("match_ts", ascending=False).copy()
    s_map = map_team[map_team["opponent_team"] == selected].copy()

    if s_grp.empty:
        st.info("No deep-dive data available for the selected opponent.")
        return

    row = s_grp.iloc[0]
    d1, d2, d3, d4, d5 = st.columns(5, gap="small")
    with d1:
        _kpi_card("Selected Win Rate", _fmt_pct(row["win_rate_match"]), selected, "good")
    with d2:
        _kpi_card("Round Differential", _fmt_signed(row["round_diff"]), f"{int(row['matches_played'])} matches", "mid")
    with d3:
        _kpi_card("Sample Reliability", str(row["confidence"]), f"{int(row['rounds'])} rounds", "poor")
    with d4:
        _kpi_card("Recent Form", str(row["recent_form"] or "-"), f"Last played {row['match_ts'].strftime('%Y-%m-%d') if pd.notna(row['match_ts']) else '-'}", "mid")
    with d5:
        _kpi_card("Danger Index", f"{row['danger_index']:.1f}", "Higher = riskier", "bad")

    deep_l, deep_r = st.columns([1.1, 1], gap="small")
    with deep_l:
        _frame("Map-by-Map Round Win %", "Highlights where overall matchup hides map weakness")
        m = s_map.sort_values("round_win_pct", ascending=True).copy()
        mfig = px.bar(
            m,
            x="round_win_pct",
            y="map",
            orientation="h",
            color="round_win_pct",
            text=m["matches"].map(lambda x: f"{int(x)} m"),
            color_continuous_scale=["#ff4d5e", "#d3a85c", "#9FE870"],
        )
        mfig.update_layout(template="plotly_dark", height=400, margin=dict(l=12, r=10, t=8, b=28), coloraxis_showscale=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        mfig.update_xaxes(range=[0, 100], ticksuffix="%")
        mfig.update_yaxes(automargin=True)
        st.plotly_chart(mfig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
        _frame_end()
    with deep_r:
        _frame("Map Pressure Matrix", "Round differential and sample depth by map")
        map_tbl = s_map[["map", "matches", "round_diff", "match_win_pct", "round_win_pct"]].copy()
        map_tbl = map_tbl.sort_values(["matches", "round_diff"], ascending=[False, False])
        st.dataframe(
            map_tbl.rename(
                columns={
                    "map": "Map",
                    "matches": "Matches",
                    "round_diff": "Round Diff",
                    "match_win_pct": "Match Win %",
                    "round_win_pct": "Round Win %",
                }
            ),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Map": st.column_config.TextColumn("Map"),
                "Matches": st.column_config.NumberColumn("Matches", format="%d"),
                "Round Diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
                "Match Win %": st.column_config.ProgressColumn("Match Win %", min_value=0.0, max_value=100.0, format="%.1f%%"),
                "Round Win %": st.column_config.ProgressColumn("Round Win %", min_value=0.0, max_value=100.0, format="%.1f%%"),
            },
        )
        _frame_end()

    s_match["Date"] = s_match["match_ts"].dt.strftime("%Y-%m-%d").fillna("-")
    st.markdown("<div class='table-frame teams-table-shell'>", unsafe_allow_html=True)
    st.dataframe(
        s_match[["Date", "primary_map", "round_wins", "round_losses", "match_diff", "result"]]
        .rename(columns={"primary_map": "Map", "round_wins": "Rounds Won", "round_losses": "Rounds Lost", "match_diff": "Round Diff", "result": "Result"}),
        hide_index=True,
        use_container_width=True,
        key="vs_teams_recent_matches",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    weak_map = s_map.sort_values("round_win_pct", ascending=True).head(1)
    strong_map = s_map.sort_values("round_win_pct", ascending=False).head(1)
    if not weak_map.empty and not strong_map.empty:
        st.markdown(
            (
                "<div class='panel teams-scout-note'>"
                f"<div class='section-title'>Scouting Readout</div>"
                f"<div class='section-subtitle'>Pressure point: <b>{weak_map.iloc[0]['map']}</b> "
                f"({_fmt_pct(weak_map.iloc[0]['round_win_pct'])} round win, {int(weak_map.iloc[0]['matches'])} matches). "
                f"Best leverage: <b>{strong_map.iloc[0]['map']}</b> "
                f"({_fmt_pct(strong_map.iloc[0]['round_win_pct'])} round win)."
                "</div></div>"
            ),
            unsafe_allow_html=True,
        )
