import pandas as pd
import plotly.express as px
import streamlit as st

from app.components import section_header
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

    section_header("Match Record vs Teams", "Primary view focused on full match outcomes.")
    with st.container(border=True):
        st.dataframe(
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
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "opponent_team": st.column_config.TextColumn("Opponent", width="medium"),
                "matches_played": st.column_config.NumberColumn("Matches", format="%d"),
                "wins": st.column_config.NumberColumn("Wins", format="%d"),
                "losses": st.column_config.NumberColumn("Losses", format="%d"),
                "draws": st.column_config.NumberColumn("Draws", format="%d"),
                "win_rate_match": st.column_config.ProgressColumn("Win% (Match)", min_value=0, max_value=100, format="%.1f%%"),
                "win_rate_rounds": st.column_config.ProgressColumn("Win% (Rounds)", min_value=0, max_value=100, format="%.1f%%"),
                "round_diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
                "latest_result_label": st.column_config.TextColumn("Latest Result", width="large"),
                "confidence": st.column_config.TextColumn("Confidence"),
            },
        )

    if view.empty:
        st.info("No team matchup rows available for charting.")
        return

    st.markdown("### Full-Match Priority Charts")

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
        template="plotly_dark",
        height=470,
        margin=dict(l=70, r=35, t=70, b=140),
        legend_title_text="Result",
        xaxis=dict(tickangle=-35, automargin=True),
        yaxis=dict(automargin=True),
    )
    st.plotly_chart(fig_wl, use_container_width=True)

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
        template="plotly_dark",
        height=470,
        margin=dict(l=70, r=35, t=70, b=140),
        xaxis=dict(tickangle=-35, automargin=True),
        yaxis=dict(automargin=True),
        coloraxis_colorbar=dict(title="Matches"),
    )
    fig_wr.update_yaxes(range=[0, 100], ticksuffix="%")
    fig_wr.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_wr, use_container_width=True)

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
    bubble.update_layout(
        template="plotly_dark",
        height=520,
        margin=dict(l=80, r=40, t=80, b=90),
        xaxis=dict(automargin=True),
        yaxis=dict(automargin=True),
    )
    bubble.update_traces(textposition="top center", cliponaxis=False)
    bubble.update_yaxes(range=[0, 100], ticksuffix="%")
    st.plotly_chart(bubble, use_container_width=True)

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
