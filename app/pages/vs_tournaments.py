import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

from app.competition import get_active_competition_col, is_grouped_mode
from app.metrics import confidence_from_sample
from app.page_layout import is_mobile_view


def _mode_control_label(mode: str | None) -> str:
    if is_grouped_mode(mode):
        return "Grouped"
    return "Individual"


def _fmt_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def _fmt_signed(value: float) -> str:
    value = int(round(float(value)))
    return f"{value:+d}"


def _hero(mode_label: str, tournaments: int, matches: int, rounds: int):
    st.markdown(
        f"""
        <div class='hero-band tournaments-hero'>
            <div class='tournaments-hero-grid'>
                <div>
                    <div class='section-title tournaments-hero-kicker'>Tournament Intelligence Surface</div>
                    <h1 class='tournaments-hero-title'>Medisports vs Tournaments</h1>
                    <p class='section-subtitle tournaments-hero-subtitle'>
                        Competition-level performance command board for event quality, consistency, volatility, and sample-backed strength.
                    </p>
                </div>
                <div class='tournaments-hero-meta'>
                    <span class='chip chip-mid'>Mode: {mode_label}</span>
                    <span class='chip chip-good'>{tournaments} tournaments tracked</span>
                    <span class='chip chip-poor'>{matches} matches</span>
                    <span class='chip'>{rounds} rounds logged</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _kpi_card(title: str, primary: str, secondary: str, accent: str = "good"):
    st.markdown(
        f"""
        <div class='panel panel-tight stat-widget tournaments-kpi accent-{accent}'>
            <div class='metric-title'>{title}</div>
            <div class='metric-value tournaments-kpi-value'>{primary}</div>
            <div class='muted'>{secondary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _chart_frame(title: str, subtitle: str = ""):
    st.markdown("<div class='analytics-frame tournaments-chart-frame'>", unsafe_allow_html=True)
    st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='section-subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def _chart_frame_end():
    st.markdown("</div>", unsafe_allow_html=True)


def _build_tournament_views(tdf: pd.DataFrame, competition_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = tdf.copy()
    base[competition_col] = base[competition_col].astype(str).str.strip().replace("", "Unknown Event")
    base["map"] = base.get("map", "").astype(str).str.strip().replace("", "Unknown Map")
    base["opponent_team"] = base.get("opponent_team", "").astype(str).str.strip().replace("", "Unknown Opponent")

    date_series = base.get("date", "").astype(str).str.strip()
    time_series = base.get("time", "").astype(str).str.strip()
    base["match_ts"] = pd.to_datetime((date_series + " " + time_series).str.strip(), errors="coerce")

    match_level = (
        base.groupby([competition_col, "match_id"], dropna=False)
        .agg(
            match_ts=("match_ts", "max"),
            round_wins=("wins", "sum"),
            round_losses=("losses", "sum"),
            rounds=("total_rounds", "sum"),
            opponent_team=("opponent_team", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))[:120]),
            map_count=("map", "nunique"),
        )
        .reset_index()
        .rename(columns={competition_col: "competition"})
    )
    match_level["match_diff"] = match_level["round_wins"] - match_level["round_losses"]
    match_level["match_win"] = (match_level["match_diff"] > 0).astype(int)
    match_level["match_loss"] = (match_level["match_diff"] < 0).astype(int)
    match_level["match_draw"] = (match_level["match_diff"] == 0).astype(int)

    grouped = (
        match_level.groupby("competition", dropna=False)
        .agg(
            matches=("match_id", "nunique"),
            wins=("match_win", "sum"),
            losses=("match_loss", "sum"),
            draws=("match_draw", "sum"),
            round_wins=("round_wins", "sum"),
            round_losses=("round_losses", "sum"),
            rounds=("rounds", "sum"),
            unique_opponents=("opponent_team", "nunique"),
        )
        .reset_index()
    )

    map_count = (
        base.groupby(competition_col, dropna=False)["map"].nunique().reset_index().rename(columns={competition_col: "competition", "map": "maps_played"})
    )
    grouped = grouped.merge(map_count, on="competition", how="left")

    grouped["win_rate"] = (grouped["wins"] / grouped["matches"].clip(lower=1) * 100).fillna(0)
    grouped["round_diff"] = grouped["round_wins"] - grouped["round_losses"]
    grouped["round_win_rate"] = (
        grouped["round_wins"] / (grouped["round_wins"] + grouped["round_losses"]).clip(lower=1) * 100
    ).fillna(0)

    volatility = match_level.groupby("competition", dropna=False)["match_diff"].std().fillna(0).rename("volatility")
    avg_diff = match_level.groupby("competition", dropna=False)["match_diff"].mean().fillna(0).rename("avg_match_diff")
    grouped = grouped.merge(volatility, on="competition", how="left").merge(avg_diff, on="competition", how="left")
    grouped["consistency"] = (100 - (grouped["volatility"].clip(lower=0) * 6)).clip(lower=0, upper=100)
    grouped["hardness_index"] = (
        grouped["unique_opponents"].clip(lower=1)
        * (1 + (100 - grouped["win_rate"]) / 80)
        * (grouped["matches"].clip(lower=1) ** 0.45)
    )
    grouped["confidence"] = grouped["rounds"].map(confidence_from_sample)

    latest = (
        match_level.sort_values("match_ts")
        .groupby("competition", dropna=False)
        .tail(5)[["competition", "match_ts", "match_diff"]]
    )
    def _form_line(sub: pd.DataFrame) -> str:
        ordered = sub.sort_values("match_ts")
        tokens = ordered["match_diff"].apply(lambda x: "W" if x > 0 else "L" if x < 0 else "D").tolist()
        return "".join(tokens[-5:]) if tokens else "-"

    form = latest.groupby("competition", dropna=False).apply(_form_line).rename("recent_form").reset_index()
    grouped = grouped.merge(form, on="competition", how="left")

    last_result = (
        match_level.sort_values("match_ts")
        .groupby("competition", dropna=False)
        .tail(1)
        .assign(last_result=lambda d: d["match_diff"].apply(lambda x: "W" if x > 0 else "L" if x < 0 else "D"))
        [["competition", "last_result", "match_ts"]]
    )
    grouped = grouped.merge(last_result, on="competition", how="left")

    return grouped.sort_values(["matches", "win_rate"], ascending=[False, False]), match_level


def render(ctx):
    tdf = ctx["tactics"]
    filters = ctx["filters"]
    mobile_view = is_mobile_view()

    group_mode = is_grouped_mode(filters.get("competition_mode"))
    col = get_active_competition_col(group_mode)

    if tdf.empty or col not in tdf.columns:
        st.warning("Tournament data unavailable for current mode.")
        return

    grouped, match_level = _build_tournament_views(tdf, col)
    if grouped.empty:
        st.info("No tournament records available after current filters.")
        return

    mode_label = _mode_control_label(filters.get("competition_mode"))
    _hero(
        mode_label=mode_label,
        tournaments=int(grouped["competition"].nunique()),
        matches=int(grouped["matches"].sum()),
        rounds=int(grouped["rounds"].sum()),
    )

    st.markdown("<div class='panel tournaments-command-zone'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.2, 1.1, 1.2, 1.2], gap="small")
    with c1:
        st.markdown("<div class='metric-title'>Competition View</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='chip {'chip-good' if mode_label == 'Grouped' else 'chip-mid'}'>"
            f"{mode_label} {'Families' if mode_label == 'Grouped' else 'Exact Events'}</div>",
            unsafe_allow_html=True,
        )
    with c2:
        min_matches = st.slider(
            "Minimum Matches",
            min_value=1,
            max_value=max(1, int(grouped["matches"].max())),
            value=1,
            step=1,
            help="Filter tournaments below a sample-size floor.",
        )
    with c3:
        focus_limit = st.select_slider("Focus Window", options=[8, 10, 12, 16, 20, 30], value=12)
    with c4:
        sort_metric = st.selectbox(
            "Primary Sort",
            options=["Win Rate", "Round Differential", "Consistency", "Hardness", "Sample Size"],
            index=0,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    scoped = grouped[grouped["matches"] >= int(min_matches)].copy()
    if scoped.empty:
        st.warning("No tournaments meet the current minimum match threshold.")
        return

    best_wr = scoped.sort_values(["win_rate", "matches"], ascending=[False, False]).head(1).iloc[0]
    worst_wr = scoped.sort_values(["win_rate", "matches"], ascending=[True, False]).head(1).iloc[0]
    most_played = scoped.sort_values("matches", ascending=False).head(1).iloc[0]
    best_rd = scoped.sort_values("round_diff", ascending=False).head(1).iloc[0]
    hardest = scoped.sort_values("hardness_index", ascending=False).head(1).iloc[0]
    steadiest = scoped.sort_values(["consistency", "matches"], ascending=[False, False]).head(1).iloc[0]

    k1, k2, k3, k4, k5, k6, k7 = st.columns(7, gap="small")
    with k1:
        _kpi_card("Best Win Rate", _fmt_pct(best_wr["win_rate"]), str(best_wr["competition"]), "good")
    with k2:
        _kpi_card("Weakest Win Rate", _fmt_pct(worst_wr["win_rate"]), str(worst_wr["competition"]), "bad")
    with k3:
        _kpi_card("Most Played", f"{int(most_played['matches'])}", str(most_played["competition"]), "mid")
    with k4:
        _kpi_card("Best Round Diff", _fmt_signed(best_rd["round_diff"]), str(best_rd["competition"]), "good")
    with k5:
        _kpi_card("Toughest Event", f"{hardest['hardness_index']:.1f}", str(hardest["competition"]), "poor")
    with k6:
        _kpi_card("Highest Consistency", _fmt_pct(steadiest["consistency"]), str(steadiest["competition"]), "mid")
    with k7:
        _kpi_card("Tracked Events", f"{int(scoped['competition'].nunique())}", "After filters", "mid")

    sort_map = {
        "Win Rate": ["win_rate", "matches"],
        "Round Differential": ["round_diff", "matches"],
        "Consistency": ["consistency", "matches"],
        "Hardness": ["hardness_index", "matches"],
        "Sample Size": ["matches", "win_rate"],
    }
    top_events = scoped.sort_values(sort_map[sort_metric], ascending=False).head(int(focus_limit)).copy()

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        left, right = st.columns([1.2, 1], gap="small")
        with left:
            _chart_frame(
                "Win Rate by Tournament",
                f"Top {len(top_events)} tournaments by {sort_metric.lower()} in {mode_label.lower()} mode.",
            )
            wr_fig = px.bar(
                top_events.sort_values("win_rate", ascending=True),
                x="win_rate",
                y="competition",
                orientation="h",
                color="win_rate",
                color_continuous_scale=["#ff4d5e", "#d3a85c", "#9FE870"],
                text=top_events.sort_values("win_rate", ascending=True)["matches"].map(lambda x: f"{int(x)} m"),
            )
            wr_fig.update_layout(
                template="plotly_dark",
                height=540 if not mobile_view else 460,
                margin=dict(l=14, r=12, t=8, b=34),
                coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            wr_fig.update_xaxes(range=[0, 100], ticksuffix="%", gridcolor="rgba(133,147,163,0.26)")
            wr_fig.update_yaxes(automargin=True)
            st.plotly_chart(wr_fig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
            _chart_frame_end()

        with right:
            _chart_frame("Performance vs Field Hardness", "Bubble size = matches, color = consistency score")
            scatter = px.scatter(
                scoped,
                x="hardness_index",
                y="win_rate",
                size="matches",
                color="consistency",
                hover_name="competition",
                color_continuous_scale=[[0, "#ff4d5e"], [0.5, "#d3a85c"], [1, "#9FE870"]],
            )
            scatter.update_layout(
                template="plotly_dark",
                height=540 if not mobile_view else 460,
                margin=dict(l=14, r=12, t=8, b=34),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            scatter.update_yaxes(range=[0, 100], ticksuffix="%", gridcolor="rgba(133,147,163,0.26)")
            scatter.update_xaxes(gridcolor="rgba(133,147,163,0.26)")
            st.plotly_chart(scatter, use_container_width=True, config={"responsive": True, "displayModeBar": True})
            _chart_frame_end()

        secondary_left, secondary_right = st.columns(2, gap="small")
        with secondary_left:
            _chart_frame("Wins / Losses / Draws by Event", "Outcome stack for top sample-size tournaments")
            stacked_df = scoped.sort_values("matches", ascending=False).head(10)
            stack = go.Figure()
            stack.add_trace(go.Bar(y=stacked_df["competition"], x=stacked_df["wins"], name="Wins", orientation="h", marker_color="#9FE870"))
            stack.add_trace(go.Bar(y=stacked_df["competition"], x=stacked_df["losses"], name="Losses", orientation="h", marker_color="#ff4d5e"))
            stack.add_trace(go.Bar(y=stacked_df["competition"], x=stacked_df["draws"], name="Draws", orientation="h", marker_color="#9fb4ca"))
            stack.update_layout(
                barmode="stack",
                template="plotly_dark",
                height=420 if not mobile_view else 380,
                margin=dict(l=14, r=12, t=8, b=34),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            stack.update_yaxes(autorange="reversed", automargin=True)
            st.plotly_chart(stack, use_container_width=True, config={"responsive": True, "displayModeBar": True})
            _chart_frame_end()
        with secondary_right:
            _chart_frame("Round Differential by Event", "Positive margin surfaces sustainable event strength")
            rd_events = top_events.sort_values("round_diff", ascending=True)
            rd = px.bar(
                rd_events,
                x="round_diff",
                y="competition",
                orientation="h",
                color="round_diff",
                color_continuous_scale=[[0, "#ff4d5e"], [0.48, "#4c5968"], [1, "#9FE870"]],
            )
            rd.update_layout(
                template="plotly_dark",
                height=420 if not mobile_view else 380,
                margin=dict(l=14, r=12, t=8, b=34),
                coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            rd.update_yaxes(automargin=True)
            rd.update_xaxes(gridcolor="rgba(133,147,163,0.24)")
            st.plotly_chart(rd, use_container_width=True, config={"responsive": True, "displayModeBar": True})
            _chart_frame_end()

    st.markdown("<div class='section-title'>Tournament Analysis Grid</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Sortable event table with sample, quality, and consistency context.</div>", unsafe_allow_html=True)

    table = scoped.copy()
    table["recent_form"] = table["recent_form"].fillna("-")
    table["last_result"] = table["last_result"].fillna("-")
    table["last_played"] = table["match_ts"].dt.strftime("%Y-%m-%d").fillna("-")

    st.markdown("<div class='table-frame tournaments-table-shell'>", unsafe_allow_html=True)
    st.dataframe(
        table[
            [
                "competition",
                "matches",
                "wins",
                "losses",
                "draws",
                "win_rate",
                "round_diff",
                "unique_opponents",
                "consistency",
                "hardness_index",
                "confidence",
                "recent_form",
                "last_result",
                "last_played",
            ]
        ].rename(
            columns={
                "competition": "Tournament",
                "matches": "Matches",
                "wins": "Wins",
                "losses": "Losses",
                "draws": "Draws",
                "win_rate": "Win Rate",
                "round_diff": "Round Diff",
                "unique_opponents": "Opponents",
                "consistency": "Consistency",
                "hardness_index": "Hardness",
                "confidence": "Confidence",
                "recent_form": "Recent Form",
                "last_result": "Last Result",
                "last_played": "Last Played",
            }
        ),
        hide_index=True,
        use_container_width=True,
        key=f"vs_tournaments_table_{mode_label.lower()}",
        column_config={
            "Tournament": st.column_config.TextColumn("Tournament", width="large"),
            "Matches": st.column_config.NumberColumn("Matches", format="%d"),
            "Wins": st.column_config.NumberColumn("Wins", format="%d"),
            "Losses": st.column_config.NumberColumn("Losses", format="%d"),
            "Draws": st.column_config.NumberColumn("Draws", format="%d"),
            "Win Rate": st.column_config.ProgressColumn("Win Rate", format="%.1f%%", min_value=0.0, max_value=100.0),
            "Round Diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
            "Opponents": st.column_config.NumberColumn("Opponents", format="%d"),
            "Consistency": st.column_config.ProgressColumn("Consistency", format="%.1f%%", min_value=0.0, max_value=100.0),
            "Hardness": st.column_config.NumberColumn("Hardness", format="%.1f"),
            "Confidence": st.column_config.TextColumn("Confidence"),
            "Recent Form": st.column_config.TextColumn("Recent Form"),
            "Last Result": st.column_config.TextColumn("Last Result"),
            "Last Played": st.column_config.TextColumn("Last Played"),
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Tournament Deep Dive</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Inspect event-specific map profile, recent matches, and opposition concentration.</div>", unsafe_allow_html=True)

    event_options = scoped.sort_values(["matches", "win_rate"], ascending=[False, False])["competition"].tolist()
    selected_event = st.selectbox("Select Tournament", options=event_options, index=0)

    selected_summary = scoped[scoped["competition"] == selected_event].head(1)
    selected_match = match_level[match_level["competition"] == selected_event].copy()
    selected_base = tdf[tdf[col].astype(str).str.strip().replace("", "Unknown Event") == selected_event].copy()

    if selected_summary.empty or selected_match.empty:
        st.info("No deep-dive data available for selected tournament.")
        return

    summary_row = selected_summary.iloc[0]
    s1, s2, s3, s4 = st.columns(4, gap="small")
    with s1:
        _kpi_card("Selected Event Win Rate", _fmt_pct(summary_row["win_rate"]), selected_event, "good")
    with s2:
        _kpi_card("Selected Round Differential", _fmt_signed(summary_row["round_diff"]), f"{int(summary_row['matches'])} matches", "mid")
    with s3:
        _kpi_card("Opposition Breadth", f"{int(summary_row['unique_opponents'])}", "Unique opponents faced", "poor")
    with s4:
        _kpi_card("Volatility", f"{summary_row['volatility']:.2f}", f"Form {summary_row['recent_form']}", "mid")

    if PLOTLY_AVAILABLE:
        deep_left, deep_right = st.columns(2, gap="small")
        with deep_left:
            _chart_frame("Map Breakdown in Selected Event", "Round win-rate by map with sample labels")
            by_map = (
                selected_base.groupby("map", dropna=False)
                .agg(round_wins=("wins", "sum"), round_losses=("losses", "sum"), rounds=("total_rounds", "sum"))
                .reset_index()
            )
            by_map["win_rate"] = (by_map["round_wins"] / (by_map["round_wins"] + by_map["round_losses"]).clip(lower=1) * 100).fillna(0)
            by_map = by_map.sort_values("win_rate", ascending=True)
            mfig = px.bar(
                by_map,
                x="win_rate",
                y="map",
                orientation="h",
                color="win_rate",
                text=by_map["rounds"].map(lambda x: f"{int(x)} rds"),
                color_continuous_scale=["#ff4d5e", "#d3a85c", "#9FE870"],
            )
            mfig.update_layout(
                template="plotly_dark",
                height=380,
                margin=dict(l=12, r=10, t=8, b=30),
                coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            mfig.update_xaxes(range=[0, 100], ticksuffix="%")
            mfig.update_yaxes(automargin=True)
            st.plotly_chart(mfig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
            _chart_frame_end()

        with deep_right:
            _chart_frame("Opponent Concentration", "Most frequent opponents in this tournament")
            opp = (
                selected_base.assign(opponent_team=selected_base["opponent_team"].astype(str).str.strip().replace("", "Unknown Opponent"))
                .groupby("opponent_team", dropna=False)
                .agg(round_wins=("wins", "sum"), round_losses=("losses", "sum"), rounds=("total_rounds", "sum"))
                .reset_index()
            )
            opp["wr"] = (opp["round_wins"] / (opp["round_wins"] + opp["round_losses"]).clip(lower=1) * 100).fillna(0)
            opp = opp.sort_values("rounds", ascending=False).head(8)
            ofig = px.scatter(
                opp,
                x="rounds",
                y="wr",
                size="rounds",
                color="wr",
                hover_name="opponent_team",
                color_continuous_scale=["#ff4d5e", "#d3a85c", "#9FE870"],
            )
            ofig.update_layout(
                template="plotly_dark",
                height=380,
                margin=dict(l=12, r=10, t=8, b=30),
                coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            ofig.update_yaxes(range=[0, 100], ticksuffix="%")
            st.plotly_chart(ofig, use_container_width=True, config={"responsive": True, "displayModeBar": True})
            _chart_frame_end()

    recent_matches = selected_match.sort_values("match_ts", ascending=False).head(10).copy()
    recent_matches["Result"] = recent_matches["match_diff"].apply(lambda x: "W" if x > 0 else "L" if x < 0 else "D")
    recent_matches["Match Date"] = recent_matches["match_ts"].dt.strftime("%Y-%m-%d").fillna("-")
    recent_matches["Round Diff"] = recent_matches["match_diff"].astype(int)

    st.markdown("<div class='table-frame tournaments-table-shell'>", unsafe_allow_html=True)
    st.dataframe(
        recent_matches[["Match Date", "opponent_team", "round_wins", "round_losses", "Round Diff", "Result"]].rename(
            columns={
                "opponent_team": "Opponent",
                "round_wins": "Round Wins",
                "round_losses": "Round Losses",
            }
        ),
        hide_index=True,
        use_container_width=True,
        key=f"vs_tournaments_recent_{mode_label.lower()}",
    )
    st.markdown("</div>", unsafe_allow_html=True)
