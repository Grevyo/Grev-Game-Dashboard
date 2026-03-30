import pandas as pd
import plotly.express as px
import streamlit as st
from app.metrics import confidence_from_sample


def _summary_box(label: str, value: str, accent: str, bg: str) -> None:
    st.markdown(
        f"""
        <div style=\"background:{bg}; border:1px solid {accent}; border-left:6px solid {accent};
                    border-radius:12px; padding:10px 12px; min-height:82px;\">
            <div style=\"font-size:0.78rem; color:#b8c2d0; margin-bottom:4px;\">{label}</div>
            <div style=\"font-size:1.35rem; font-weight:700; color:#f5f7fa; line-height:1.2;\">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


HEATMAP_RED_GREEN_SCALE = [
    [0.0, "#7f1d1d"],   # deep red (poor)
    [0.5, "#3f4a3f"],   # muted dark midpoint (neutral)
    [1.0, "#166534"],   # deep green (strong)
]


def _apply_priority_chart_style(fig, *, height: int = 500):
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=56, r=24, t=64, b=84),
        title=dict(font=dict(size=17, color="#EAF2FF"), x=0.0, xanchor="left"),
        legend=dict(
            title_font=dict(size=12, color="#EAF2FF"),
            font=dict(size=11, color="#DCE7F5"),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(10,16,29,0.45)",
            bordercolor="rgba(123,144,168,0.26)",
            borderwidth=1,
        ),
        plot_bgcolor="rgba(9,13,22,0.82)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor="rgba(14,20,31,0.96)",
            bordercolor="rgba(123,144,168,0.65)",
            font=dict(color="#F5F8FF", size=12),
        ),
        font=dict(color="#D6DFEA"),
    )
    fig.update_xaxes(
        tickangle=-25,
        automargin=True,
        tickfont=dict(size=11),
        title_font=dict(size=13),
        ticklabelposition="outside",
        showgrid=False,
        zeroline=False,
    )
    fig.update_yaxes(
        automargin=True,
        tickfont=dict(size=11),
        title_font=dict(size=13),
        gridcolor="rgba(123,144,168,0.20)",
        griddash="dot",
        zeroline=False,
    )
    return fig


def _render_chart_panel(fig, heading: str, note: str = ""):
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    if heading:
        st.markdown(f"<div class='section-title' style='margin-bottom:4px'>{heading}</div>", unsafe_allow_html=True)
    if note:
        st.markdown(f"<div class='section-subtitle' style='margin-bottom:10px'>{note}</div>", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_match_record_table(view: pd.DataFrame) -> None:
    sortable_df = (
        view[
            [
                "opponent_team",
                "matches_played",
                "wins",
                "losses",
                "draws",
                "win_rate_match",
                "win_rate_rounds",
                "round_diff",
                "latest_result_label",
                "confidence",
            ]
        ]
        .copy()
        .rename(
            columns={
                "opponent_team": "Opponent",
                "matches_played": "Matches",
                "wins": "Wins",
                "losses": "Losses",
                "draws": "Draws",
                "win_rate_match": "Win% (Match)",
                "win_rate_rounds": "Win% (Rounds)",
                "round_diff": "Round Diff",
                "latest_result_label": "Latest Result",
                "confidence": "Confidence",
            }
        )
    )

    # Keep this rendered as a native Streamlit dataframe (not styled HTML)
    # so users can sort by clicking headers in the visible table.
    st.markdown(
        """
        <style>
          .match-record-premium-shell {
            margin-top: 8px;
            border: 1px solid rgba(141, 168, 200, 0.34);
            border-radius: 18px;
            padding: 12px;
            background:
              radial-gradient(1300px 220px at 50% -40%, rgba(110, 201, 255, 0.12), transparent 44%),
              linear-gradient(170deg, rgba(7, 13, 22, 0.97) 0%, rgba(12, 20, 33, 0.94) 100%);
            box-shadow:
              0 18px 42px rgba(0, 0, 0, 0.40),
              inset 0 1px 0 rgba(226, 237, 255, 0.07);
          }
          .match-record-premium-shell [data-testid="stDataFrame"] {
            border: 1px solid rgba(139, 165, 195, 0.38);
            border-radius: 14px;
            overflow: hidden;
            background: rgba(8, 14, 25, 0.72);
          }
          .match-record-premium-shell [data-testid="stDataFrame"] [data-testid="stElementToolbar"] {
            background: linear-gradient(180deg, rgba(16, 26, 41, 0.88), rgba(12, 21, 35, 0.82));
            border-bottom: 1px solid rgba(135, 161, 192, 0.34);
          }
          .match-record-premium-shell [data-testid="stDataFrame"] [data-testid="stDataFrameGlideDataEditor"] {
            padding: 4px;
            background: transparent;
          }
          .match-record-premium-shell [data-testid="stDataFrame"] canvas {
            border-radius: 10px;
          }
        </style>
        <div class='match-record-premium-shell'>
        """,
        unsafe_allow_html=True,
    )

    st.dataframe(
        sortable_df,
        hide_index=True,
        use_container_width=True,
        key="match_record_vs_teams_table",
        column_config={
            "Opponent": st.column_config.TextColumn("Opponent"),
            "Matches": st.column_config.NumberColumn("Matches", format="%d"),
            "Wins": st.column_config.NumberColumn("Wins", format="%d"),
            "Losses": st.column_config.NumberColumn("Losses", format="%d"),
            "Draws": st.column_config.NumberColumn("Draws", format="%d"),
            "Win% (Match)": st.column_config.ProgressColumn(
                "Win% (Match)",
                min_value=0.0,
                max_value=100.0,
                format="%.1f%%",
            ),
            "Win% (Rounds)": st.column_config.ProgressColumn(
                "Win% (Rounds)",
                min_value=0.0,
                max_value=100.0,
                format="%.1f%%",
            ),
            "Round Diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
            "Latest Result": st.column_config.TextColumn("Latest Result"),
            "Confidence": st.column_config.TextColumn("Confidence"),
        },
    )

    st.markdown("</div>", unsafe_allow_html=True)

def _render_heatmap(
    pivot: pd.DataFrame,
    title: str,
    color_label: str,
    zmin=None,
    zmax=None,
    zmid=None,
    scale=HEATMAP_RED_GREEN_SCALE,
) -> None:
    if pivot.empty:
        st.info(f"No data available for {title}.")
        return

    numeric_pivot = pivot.apply(pd.to_numeric, errors="coerce")
    if numeric_pivot.empty or numeric_pivot.notna().sum().sum() == 0:
        st.info(f"No numeric data available for {title}.")
        return

    imshow_kwargs = {
        "img": numeric_pivot,
        "aspect": "auto",
        "color_continuous_scale": scale,
        "labels": {"x": "Map", "y": "Team", "color": color_label},
        "text_auto": ".1f",
        "title": title,
    }

    if zmin is not None or zmax is not None:
        imshow_kwargs["range_color"] = [zmin, zmax]
    if zmid is not None:
        imshow_kwargs["color_continuous_midpoint"] = zmid

    heat = px.imshow(**imshow_kwargs)
    heat.update_traces(textfont={"color": "#F5F7FA"})
    heat.update_layout(
        template="plotly_dark",
        height=max(420, 120 + 34 * len(pivot.index)),
        margin=dict(l=130, r=30, t=70, b=120),
        xaxis=dict(tickangle=-35, automargin=True),
        yaxis=dict(automargin=True),
    )
    st.plotly_chart(heat, use_container_width=True)


def render(ctx):
    tdf = ctx["tactics"]
    st.title("Medisports vs Teams")

    if tdf.empty:
        st.warning("No tactics/opponent data after filters.")
        return

    base = tdf.copy()
    base["opponent_team"] = base["opponent_team"].astype(str).str.strip().replace("", "Unknown Opponent")
    base["map"] = base["map"].astype(str).str.strip().replace("", "Unknown Map")
    base["date"] = base["date"].astype(str).str.strip()
    base["time"] = base["time"].astype(str).str.strip()
    base["match_ts"] = pd.to_datetime((base["date"] + " " + base["time"]).str.strip(), errors="coerce")

    match_level = (
        base.groupby(["opponent_team", "match_id"], dropna=False)
        .agg(
            map=("map", "first"),
            date=("date", "first"),
            time=("time", "first"),
            match_ts=("match_ts", "max"),
            round_wins=("wins", "sum"),
            round_losses=("losses", "sum"),
            rounds=("total_rounds", "sum"),
        )
        .reset_index()
    )
    match_level["match_diff"] = match_level["round_wins"] - match_level["round_losses"]
    match_level["match_win"] = (match_level["match_diff"] > 0).astype(int)
    match_level["match_loss"] = (match_level["match_diff"] < 0).astype(int)
    match_level["match_draw"] = (match_level["match_diff"] == 0).astype(int)
    match_level["latest_result"] = match_level["match_diff"].apply(lambda x: "W" if x > 0 else "L" if x < 0 else "D")

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
        )
        .reset_index()
    )
    grp["win_rate_match"] = (grp["wins"] / grp["matches_played"].clip(lower=1) * 100).fillna(0)
    grp["win_rate_rounds"] = (
        grp["round_wins"] / (grp["round_wins"] + grp["round_losses"]).clip(lower=1) * 100
    ).fillna(0)
    grp["confidence"] = grp["rounds"].map(confidence_from_sample)

    latest = (
        match_level.sort_values("match_ts")
        .groupby("opponent_team", dropna=False)
        .tail(1)[["opponent_team", "latest_result", "date", "map"]]
        .rename(columns={"date": "latest_date", "map": "latest_map"})
    )
    grp = grp.merge(latest, on="opponent_team", how="left")
    grp["latest_result_label"] = (
        grp["latest_result"].fillna("-")
        + " • "
        + grp["latest_date"].fillna("n/a")
        + " • "
        + grp["latest_map"].fillna("n/a")
    )

    overall_matches = int(grp["matches_played"].sum())
    overall_wins = int(grp["wins"].sum())
    overall_losses = int(grp["losses"].sum())
    overall_draws = int(grp["draws"].sum())
    overall_rounds = int(grp["rounds"].sum())
    overall_win_rate = (overall_wins / max(1, overall_matches)) * 100

    st.subheader("Total Vs Teams")
    c1, c2, c3, c4, c5 = st.columns(5, gap="small")
    with c1:
        _summary_box("Opponents", f"{int(grp['opponent_team'].nunique())}", "#5BC0EB", "rgba(91,192,235,0.10)")
    with c2:
        _summary_box("Match W-L-D", f"{overall_wins}-{overall_losses}-{overall_draws}", "#95E06C", "rgba(149,224,108,0.10)")
    with c3:
        _summary_box("Matches", f"{overall_matches}", "#C29BFF", "rgba(194,155,255,0.10)")
    with c4:
        _summary_box("Match Win %", f"{overall_win_rate:.1f}%", "#FFB86C", "rgba(255,184,108,0.10)")
    with c5:
        _summary_box("Tracked Rounds", f"{overall_rounds}", "#7EE2D1", "rgba(126,226,209,0.10)")

    view = grp.sort_values(["win_rate_match", "round_diff", "matches_played"], ascending=[False, False, False]).copy()

    _render_match_record_table(view)

    if view.empty:
        st.info("No team matchup rows available for charting.")
        return

    wl_long = view.melt(
        id_vars=["opponent_team"],
        value_vars=["wins", "losses", "draws"],
        var_name="Result",
        value_name="Matches",
    )
    fig_wl = px.bar(
        wl_long.sort_values(["opponent_team", "Result"]),
        x="opponent_team",
        y="Matches",
        color="Result",
        barmode="group",
        color_discrete_map={"wins": "#3ECF8E", "losses": "#FF6B6B", "draws": "#7AA2FF"},
        title="Wins, Losses, and Draws by Team",
        labels={"opponent_team": "Opponent"},
    )
    fig_wl.update_layout(
        legend_title_text="Result",
        bargap=0.25,
        margin=dict(t=128, b=92, l=56, r=26),
        title=dict(pad=dict(t=22, b=18)),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="right",
            x=1.0,
            traceorder="normal",
            bgcolor="rgba(10,16,28,0.55)",
            bordercolor="rgba(125,150,180,0.28)",
            borderwidth=1,
        ),
    )
    fig_wl.update_traces(
        marker_line_color="rgba(240,245,255,0.20)",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>",
    )
    _render_chart_panel(
        _apply_priority_chart_style(fig_wl, height=520),
        "",
        "",
    )

    fig_wr = px.bar(
        view.sort_values("win_rate_match", ascending=False),
        x="opponent_team",
        y="win_rate_match",
        color="matches_played",
        color_continuous_scale="Tealgrn",
        text="matches_played",
        title="Match Win % by Team",
        labels={"opponent_team": "Opponent", "win_rate_match": "Match Win %", "matches_played": "Matches"},
    )
    fig_wr.update_layout(
        coloraxis_colorbar=dict(title="Matches"),
    )
    fig_wr.update_yaxes(range=[0, 100], ticksuffix="%")
    fig_wr.update_traces(
        textposition="outside",
        cliponaxis=False,
        textfont=dict(size=11, color="#ECF3FF"),
        marker_line_color="rgba(240,245,255,0.22)",
        marker_line_width=1,
        hovertemplate="<b>%{x}</b><br>Match Win %: %{y:.1f}%<br>Matches: %{marker.color}<extra></extra>",
    )
    _render_chart_panel(
        _apply_priority_chart_style(fig_wr, height=520),
        "",
        "",
    )

    bubble = px.scatter(
        view,
        x="rounds",
        y="win_rate_match",
        size="matches_played",
        color="round_diff",
        hover_name="opponent_team",
        text="opponent_team",
        color_continuous_scale="RdYlGn",
        title="Sample Depth Vs Win Efficiency",
        labels={
            "rounds": "Tracked Rounds",
            "win_rate_match": "Match Win %",
            "matches_played": "Matches",
            "round_diff": "Round Diff",
        },
    )
    bubble.update_traces(
        textposition="top center",
        cliponaxis=False,
        textfont=dict(size=10, color="#EAF2FF"),
        marker=dict(
            symbol="circle",
            line=dict(color="rgba(233,242,255,0.82)", width=1.9),
            opacity=0.82,
            sizemin=10,
        ),
        hovertemplate=(
            "<b>%{hovertext}</b><br>Tracked Rounds: %{x}<br>"
            "Match Win %: %{y:.1f}%<br>Matches: %{marker.size}<br>Round Diff: %{marker.color}<extra></extra>"
        ),
    )
    bubble.update_layout(
        margin=dict(l=72, r=44, t=120, b=98),
        title=dict(x=0.02, xanchor="left", font=dict(size=21, color="#F2F7FF"), pad=dict(t=14, b=20)),
        coloraxis_colorbar=dict(
            title="Round Diff",
            len=0.68,
            thickness=14,
            ticks="outside",
            tickfont=dict(size=11),
            y=0.5,
            yanchor="middle",
            x=1.02,
        ),
    )
    bubble.update_xaxes(
        title_text="Tracked Rounds",
        tickfont=dict(size=12),
        title_font=dict(size=14),
        showline=True,
        linewidth=1,
        linecolor="rgba(152,173,197,0.35)",
        gridcolor="rgba(152,173,197,0.16)",
    )
    bubble.update_yaxes(
        range=[0, 100],
        ticksuffix="%",
        tickfont=dict(size=12),
        title_font=dict(size=14),
        gridcolor="rgba(152,173,197,0.24)",
    )
    st.markdown(
        """
        <div style="padding:14px 16px 6px; border:1px solid rgba(120,145,172,0.30); border-radius:14px; 
                    background:linear-gradient(180deg, rgba(15,22,35,0.95) 0%, rgba(10,15,25,0.88) 100%);">
        """,
        unsafe_allow_html=True,
    )
    _render_chart_panel(
        _apply_priority_chart_style(bubble, height=590),
        "",
        "",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    map_team = (
        match_level.groupby(["opponent_team", "map"], dropna=False)
        .agg(
            rounds_won=("round_wins", "sum"),
            rounds_lost=("round_losses", "sum"),
            match_wins=("match_win", "sum"),
            match_losses=("match_loss", "sum"),
            matches=("match_id", "nunique"),
        )
        .reset_index()
    )
    map_team["round_diff"] = map_team["rounds_won"] - map_team["rounds_lost"]
    map_team["round_win_pct"] = (
        map_team["rounds_won"] / (map_team["rounds_won"] + map_team["rounds_lost"]).clip(lower=1) * 100
    ).fillna(0)
    map_team["match_diff"] = map_team["match_wins"] - map_team["match_losses"]
    map_team["match_win_pct"] = (map_team["match_wins"] / map_team["matches"].clip(lower=1) * 100).fillna(0)

    team_order = (
        grp.sort_values(["matches_played", "wins", "round_diff", "opponent_team"], ascending=[False, False, False, True])[
            "opponent_team"
        ]
        .tolist()
    )
    map_order = (
        map_team.groupby("map", dropna=False)["matches"]
        .sum()
        .sort_values(ascending=False)
        .index.tolist()
    )

    def _build_heatmap_pivot(value_col: str) -> pd.DataFrame:
        return (
            map_team.pivot(index="opponent_team", columns="map", values=value_col)
            .reindex(index=team_order, columns=map_order)
            .fillna(0)
        )

    round_diff_pivot = _build_heatmap_pivot("round_diff")
    round_win_pct_pivot = _build_heatmap_pivot("round_win_pct")
    match_diff_pivot = _build_heatmap_pivot("match_diff")
    match_win_pct_pivot = _build_heatmap_pivot("match_win_pct")

    round_diff_abs = float(round_diff_pivot.abs().to_numpy().max()) if not round_diff_pivot.empty else 0.0
    match_diff_abs = float(match_diff_pivot.abs().to_numpy().max()) if not match_diff_pivot.empty else 0.0

    st.markdown("### Heatmaps")
    st.caption(
        "Metrics: Round Win/Lose uses round differential (rounds won - rounds lost). "
        "Match Win/Lose uses match differential (wins - losses)."
    )

    _render_heatmap(
        round_diff_pivot,
        "Round Win/Lose by Team and Map",
        "Round Diff",
        zmin=-round_diff_abs if round_diff_abs else None,
        zmax=round_diff_abs if round_diff_abs else None,
        zmid=0,
    )
    _render_heatmap(
        round_win_pct_pivot,
        "Round Win % by Team and Map",
        "Round Win %",
        zmin=0,
        zmax=100,
        zmid=50,
    )
    _render_heatmap(
        match_diff_pivot,
        "Match Win/Lose by Team and Map",
        "Match Diff",
        zmin=-match_diff_abs if match_diff_abs else None,
        zmax=match_diff_abs if match_diff_abs else None,
        zmid=0,
    )
    _render_heatmap(
        match_win_pct_pivot,
        "Match Win % by Team and Map",
        "Match Win %",
        zmin=0,
        zmax=100,
        zmid=50,
    )

    weak = grp.nsmallest(3, "win_rate_match")
    strong = grp.nlargest(3, "win_rate_match")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Strongest Matchups")
        st.dataframe(
            strong[["opponent_team", "matches_played", "wins", "losses", "win_rate_match", "confidence"]],
            use_container_width=True,
            hide_index=True,
        )
    with c2:
        st.subheader("Needs Fixing")
        st.dataframe(
            weak[["opponent_team", "matches_played", "wins", "losses", "win_rate_match", "confidence"]],
            use_container_width=True,
            hide_index=True,
        )
