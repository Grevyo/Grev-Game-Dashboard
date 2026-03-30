import streamlit as st

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

    match_level = (
        base.groupby(["opponent_team", "match_id"], dropna=False)
        .agg(
            map=("map", "first"),
            round_wins=("wins", "sum"),
            round_losses=("losses", "sum"),
            rounds=("total_rounds", "sum"),
        )
        .reset_index()
    )
    match_level["match_diff"] = match_level["round_wins"] - match_level["round_losses"]

    grp = (
        match_level.groupby("opponent_team", dropna=False)
        .agg(
            matches_played=("match_id", "nunique"),
            maps_played=("map", "nunique"),
            round_wins=("round_wins", "sum"),
            round_losses=("round_losses", "sum"),
            round_diff=("match_diff", "sum"),
            rounds=("rounds", "sum"),
        )
        .reset_index()
    )
    grp["win_rate"] = (grp["round_wins"] / (grp["round_wins"] + grp["round_losses"]).clip(lower=1) * 100).fillna(0)
    grp["avg_round_diff_match"] = (grp["round_diff"] / grp["matches_played"].clip(lower=1)).fillna(0.0)
    grp["record"] = grp["round_wins"].astype(int).astype(str) + "-" + grp["round_losses"].astype(int).astype(str)
    grp["confidence"] = grp["rounds"].map(confidence_from_sample)

    overall = {
        "opponents": int(grp["opponent_team"].nunique()),
        "matches": int(grp["matches_played"].sum()),
        "rounds": int(grp["rounds"].sum()),
        "win_rate": float(grp["win_rate"].mean()) if not grp.empty else 0.0,
        "avg_diff": float(grp["avg_round_diff_match"].mean()) if not grp.empty else 0.0,
    }

    k1, k2, k3, k4, k5 = st.columns(5, gap="small")
    with k1:
        st.metric("Opponents", int(overall["opponents"]))
    with k2:
        st.metric("Matches", int(overall["matches"]))
    with k3:
        st.metric("Tracked Rounds", int(overall["rounds"]))
    with k4:
        st.metric("Avg Win %", f"{overall['win_rate']:.1f}%")
    with k5:
        st.metric("Avg Rd Diff / Match", f"{overall['avg_diff']:+.2f}")

    opponent_options = ["All"] + sorted(grp["opponent_team"].astype(str).unique().tolist())
    if st.session_state.get("vs_teams_opponent") not in opponent_options:
        st.session_state["vs_teams_opponent"] = "All"

    if filter_panel_toggle("vs_teams"):
        st.selectbox("Drill into opponent", opponent_options, key="vs_teams_opponent")

    opp = st.session_state.get("vs_teams_opponent", "All")
    view = grp if opp == "All" else grp[grp["opponent_team"] == opp].copy()
    view = view.sort_values(["win_rate", "round_diff", "matches_played"], ascending=[False, False, False]).copy()

    section_header("Matchup Overview", "Opponent-level snapshot with round record, efficiency, and sample depth.")
    st.dataframe(
        view[["opponent_team", "matches_played", "maps_played", "record", "win_rate", "round_diff", "avg_round_diff_match", "rounds", "confidence"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "opponent_team": st.column_config.TextColumn("Opponent"),
            "matches_played": st.column_config.NumberColumn("Matches", format="%d"),
            "maps_played": st.column_config.NumberColumn("Maps", format="%d"),
            "record": st.column_config.TextColumn("Round Record"),
            "win_rate": st.column_config.ProgressColumn("Win %", min_value=0, max_value=100, format="%.1f%%"),
            "round_diff": st.column_config.NumberColumn("Round Diff", format="%+d"),
            "avg_round_diff_match": st.column_config.NumberColumn("Avg Diff/Match", format="%+.2f"),
            "rounds": st.column_config.NumberColumn("Rounds", format="%d"),
            "confidence": st.column_config.TextColumn("Confidence"),
        },
    )

    if not PLOTLY_AVAILABLE:
        st.warning("Plotly is not installed in this environment. Interactive charts are unavailable.")
    else:
        fig = px.bar(
            view.sort_values("win_rate"),
            x="win_rate",
            y="opponent_team",
            orientation="h",
            color="avg_round_diff_match",
            color_continuous_scale="RdYlGn",
            text=view.sort_values("win_rate")["record"],
            title="Win % by Opponent",
            labels={
                "win_rate": "Win % (round-based)",
                "opponent_team": "Opponent",
                "avg_round_diff_match": "Avg Diff/Match",
            },
        )
        fig.update_layout(
            template="plotly_dark",
            height=430,
            margin=dict(l=10, r=10, t=56, b=12),
            legend_title_text="",
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_xaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

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
                "win_rate": "Win %",
                "matches_played": "Matches",
                "round_diff": "Round Diff",
            },
        )
        bubble.update_layout(template="plotly_dark", height=420, margin=dict(l=8, r=8, t=56, b=8))
        bubble.update_traces(textposition="top center")
        bubble.update_yaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(bubble, use_container_width=True)

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
                labels={"x": "Map", "y": "Opponent", "color": "Win %"},
                title="Vs Team by Map Heatmap (Round Win %)",
            )
            heat.update_layout(template="plotly_dark", height=max(360, 52 + 28 * len(pivot.index)), margin=dict(l=8, r=8, t=56, b=8))
            st.plotly_chart(heat, use_container_width=True)

    if opp != "All" and not view.empty:
        r = view.iloc[0]
        insight_card("Matchup Insight", matchup_insight(opp, r["round_wins"], r["round_losses"], r["win_rate"], r["rounds"]), "info")
        if r["rounds"] < 20:
            insight_card("Low sample warning", "Interpret this matchup with caution due to low round volume.", "warn")

    weak = grp.nsmallest(3, "win_rate")
    strong = grp.nlargest(3, "win_rate")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Strongest Matchups")
        st.dataframe(
            strong[["opponent_team", "matches_played", "record", "win_rate", "round_diff", "confidence"]],
            use_container_width=True,
            hide_index=True,
        )
    with c2:
        st.subheader("Needs Fixing")
        st.dataframe(
            weak[["opponent_team", "matches_played", "record", "win_rate", "round_diff", "confidence"]],
            use_container_width=True,
            hide_index=True,
        )
