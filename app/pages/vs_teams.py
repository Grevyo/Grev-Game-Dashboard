import streamlit as st
import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

from app.components import insight_card, section_header
from app.descriptions import matchup_insight
from app.filters import filter_panel_toggle
from app.metrics import confidence_from_sample


def render(ctx):
    tdf = ctx["tactics"]
    st.title("Medisports vs Teams")
    st.caption("Vs Teams Refresh ✓")
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
            maps_played=("map", "nunique"),
            round_wins=("round_wins", "sum"),
            round_losses=("round_losses", "sum"),
            round_diff=("match_diff", "sum"),
            rounds=("rounds", "sum"),
        )
        .reset_index()
    )
    grp["win_rate"] = (grp["wins"] / grp["matches_played"].clip(lower=1) * 100).fillna(0)
    grp["avg_round_diff_match"] = (grp["round_diff"] / grp["matches_played"].clip(lower=1)).fillna(0.0)
    grp["record"] = grp["wins"].astype(int).astype(str) + "-" + grp["losses"].astype(int).astype(str)
    grp["round_record"] = grp["round_wins"].astype(int).astype(str) + "-" + grp["round_losses"].astype(int).astype(str)
    grp["confidence"] = grp["rounds"].map(confidence_from_sample)
    latest = (
        match_level.sort_values("match_ts")
        .groupby("opponent_team", dropna=False)
        .tail(1)[["opponent_team", "latest_result", "date", "map"]]
        .rename(columns={"date": "latest_date", "map": "latest_map"})
    )
    grp = grp.merge(latest, on="opponent_team", how="left")
    grp["latest"] = (
        grp["latest_result"].fillna("-")
        + " • "
        + grp["latest_date"].fillna("n/a")
        + " • "
        + grp["latest_map"].fillna("n/a")
    )

    overall = {
        "opponents": int(grp["opponent_team"].nunique()),
        "matches": int(grp["matches_played"].sum()),
        "wins": int(grp["wins"].sum()),
        "losses": int(grp["losses"].sum()),
        "rounds": int(grp["rounds"].sum()),
        "win_rate": float((grp["wins"].sum() / max(1, grp["matches_played"].sum())) * 100) if not grp.empty else 0.0,
    }

    st.subheader("Vs Teams Refresh ✓")
    k1, k2, k3, k4, k5 = st.columns(5, gap="small")
    with k1:
        st.metric("Opponents", int(overall["opponents"]))
    with k2:
        st.metric("Match W-L", f"{overall['wins']}-{overall['losses']}")
    with k3:
        st.metric("Matches", int(overall["matches"]))
    with k4:
        st.metric("Match Win %", f"{overall['win_rate']:.1f}%")
    with k5:
        st.metric("Tracked Rounds", int(overall["rounds"]))

    opponent_options = ["All"] + sorted(grp["opponent_team"].astype(str).unique().tolist())
    if st.session_state.get("vs_teams_opponent") not in opponent_options:
        st.session_state["vs_teams_opponent"] = "All"

    if filter_panel_toggle("vs_teams"):
        st.selectbox("Drill into opponent", opponent_options, key="vs_teams_opponent")

    opp = st.session_state.get("vs_teams_opponent", "All")
    view = grp if opp == "All" else grp[grp["opponent_team"] == opp].copy()
    view = view.sort_values(["win_rate", "round_diff", "matches_played"], ascending=[False, False, False]).copy()

    section_header("Match Record vs Teams ✓", "Primary view: full match wins/losses versus each opponent.")
    with st.container(border=True):
        st.dataframe(
            view[
                [
                    "opponent_team",
                    "matches_played",
                    "wins",
                    "losses",
                    "draws",
                    "win_rate",
                    "latest",
                    "maps_played",
                    "round_diff",
                    "avg_round_diff_match",
                    "confidence",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "opponent_team": st.column_config.TextColumn("Opponent"),
                "matches_played": st.column_config.NumberColumn("Matches", format="%d"),
                "wins": st.column_config.NumberColumn("Wins", format="%d"),
                "losses": st.column_config.NumberColumn("Losses", format="%d"),
                "draws": st.column_config.NumberColumn("Draws", format="%d"),
                "win_rate": st.column_config.ProgressColumn("Win %", min_value=0, max_value=100, format="%.1f%%"),
                "latest": st.column_config.TextColumn("Latest Result"),
                "maps_played": st.column_config.NumberColumn("Maps", format="%d"),
                "round_diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
                "avg_round_diff_match": st.column_config.NumberColumn("Avg Rd Diff/Match", format="%+.2f"),
                "confidence": st.column_config.TextColumn("Confidence"),
            },
        )

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        st.markdown("##### Full-Match Priority Charts")
        chart_col1, chart_col2 = st.columns(2, gap="medium")
        with chart_col1:
            wl_long = view.melt(
                id_vars=["opponent_team"],
                value_vars=["wins", "losses"],
                var_name="Result",
                value_name="Matches",
            )
            fig = px.bar(
                wl_long.sort_values(["opponent_team", "Result"]),
                x="opponent_team",
                y="Matches",
                color="Result",
                barmode="group",
                color_discrete_map={"wins": "#36CFC9", "losses": "#FF7875"},
                title="Wins vs Losses by Team",
                labels={"opponent_team": "Opponent"},
            )
            fig.update_layout(template="plotly_dark", height=420, margin=dict(l=8, r=8, t=56, b=8), xaxis_tickangle=-25)
            st.plotly_chart(fig, use_container_width=True)

        with chart_col2:
            win_fig = px.bar(
                view.sort_values("win_rate", ascending=False),
                x="opponent_team",
                y="win_rate",
                color="matches_played",
                color_continuous_scale="Blues",
                text="record",
                title="Match Win % by Team",
                labels={"opponent_team": "Opponent", "win_rate": "Match Win %", "matches_played": "Matches"},
            )
            win_fig.update_layout(template="plotly_dark", height=420, margin=dict(l=8, r=8, t=56, b=8), xaxis_tickangle=-25)
            win_fig.update_yaxes(range=[0, 100], ticksuffix="%")
            win_fig.update_traces(textposition="outside", cliponaxis=False)
            st.plotly_chart(win_fig, use_container_width=True)

        bubble = px.scatter(
            view,
            x="rounds",
            y="win_rate",
            size="matches_played",
            color="round_diff",
            hover_name="opponent_team",
            text="opponent_team",
            color_continuous_scale="RdYlGn",
            title="Sample Depth vs Win Efficiency",
            labels={
                "rounds": "Tracked Rounds",
                "win_rate": "Match Win %",
                "matches_played": "Matches",
                "round_diff": "Round Diff",
            },
        )
        bubble.update_layout(template="plotly_dark", height=420, margin=dict(l=8, r=8, t=56, b=8))
        bubble.update_traces(textposition="top center")
        bubble.update_yaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(bubble, use_container_width=True)

        with st.container(border=True):
            section_header("Round-Based Breakdown (Support)", "Secondary details kept below full match record.")
            map_team = (
                match_level.groupby(["opponent_team", "map"], dropna=False)
                .agg(round_wins=("round_wins", "sum"), round_losses=("round_losses", "sum"))
                .reset_index()
            )
            map_team["win_rate"] = (map_team["round_wins"] / (map_team["round_wins"] + map_team["round_losses"]).clip(lower=1) * 100).fillna(0)
            pivot = (
                map_team.pivot(index="opponent_team", columns="map", values="win_rate")
                .sort_index()
                .fillna(0)
            )
            if not pivot.empty:
                heat = px.imshow(
                    pivot,
                    aspect="auto",
                    color_continuous_scale="RdYlGn",
                    zmin=0,
                    zmax=100,
                    text_auto=".0f",
                    labels={"x": "Map", "y": "Opponent", "color": "Round Win %"},
                    title="Round Win % by Team and Map",
                )
                heat.update_layout(template="plotly_dark", height=max(360, 52 + 28 * len(pivot.index)), margin=dict(l=8, r=8, t=56, b=8))
                st.plotly_chart(heat, use_container_width=True)

            st.dataframe(
                view[
                    [
                        "opponent_team",
                        "round_record",
                        "round_diff",
                        "avg_round_diff_match",
                        "rounds",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "opponent_team": st.column_config.TextColumn("Opponent"),
                    "round_record": st.column_config.TextColumn("Round Record"),
                    "round_diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
                    "avg_round_diff_match": st.column_config.NumberColumn("Avg Rd Diff/Match", format="%+.2f"),
                    "rounds": st.column_config.NumberColumn("Tracked Rounds", format="%d"),
                },
            )

    if opp != "All" and not view.empty:
        r = view.iloc[0]
        insight_card("Matchup Insight", matchup_insight(opp, r["wins"], r["losses"], r["win_rate"], r["matches_played"]), "info")
        if r["rounds"] < 20:
            insight_card("Low sample warning", "Interpret this matchup with caution due to low round volume.", "warn")

    weak = grp.nsmallest(3, "win_rate")
    strong = grp.nlargest(3, "win_rate")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Strongest Matchups")
        st.dataframe(
            strong[["opponent_team", "matches_played", "record", "win_rate", "latest", "confidence"]],
            use_container_width=True,
            hide_index=True,
        )
    with c2:
        st.subheader("Needs Fixing")
        st.dataframe(
            weak[["opponent_team", "matches_played", "record", "win_rate", "latest", "confidence"]],
            use_container_width=True,
            hide_index=True,
        )
