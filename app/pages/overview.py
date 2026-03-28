import streamlit as st

from app.components import insight_card, player_card, section_header, stat_card
from app.descriptions import player_description
from app.metrics import trend_label
from app.transforms import best_contexts, summarize_player


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
        return "Flat"
    s = df[df["player"] == player_name].sort_values("date")["grevscore"]
    label = trend_label(s)
    return "Heating Up" if label == "Rising" else "Cooling" if label == "Falling" else "Stable"


def render(ctx):
    df = ctx["player_matches"]
    players_meta = ctx["players"]
    team_name = ctx["team_name"]
    filters = ctx.get("filters", {})

    if df.empty:
        st.warning("No rows available after filters.")
        return

    summary = summarize_player(df)
    if summary.empty:
        st.warning("No player summary available with current filters.")
        return

    seasons = filters.get("season") or ["All seasons"]
    maps = filters.get("map") or ["All maps"]

    st.markdown(
        f"""
        <div class='hero-band'>
            <div class='section-title' style='margin-top:0'>🏁 Squad Overview</div>
            <div class='muted'>Team focus: <strong>{team_name}</strong></div>
            <div style='margin-top:8px;'>
              <span class='chip'>Season: {', '.join(map(str, seasons[:2]))}{'…' if len(seasons) > 2 else ''}</span>
              <span class='chip'>Map scope: {', '.join(map(str, maps[:2]))}{'…' if len(maps) > 2 else ''}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        stat_card("Players", summary["player"].nunique(), "Active in selected context")
    with k2:
        stat_card("Avg GrevScore", f"{summary['grevscore'].mean():.1f}", "Squad firepower average")
    with k3:
        stat_card("Avg Rating", f"{summary['rating'].mean():.2f}", "Composite consistency")
    with k4:
        stat_card("Matches", int(df["match_id"].nunique()), "Unique matches tracked")

    section_header("Team Pulse", "Quick strengths and concerns from current filter window")
    hottest = summary.sort_values("form", ascending=False).head(2)["player"].tolist()
    cooling = summary.sort_values("form", ascending=True).head(2)["player"].tolist()
    pulse_a, pulse_b = st.columns(2, gap="small")
    with pulse_a:
        insight_card("Strength", f"Current momentum leaders: {', '.join(hottest)}.", "good")
    with pulse_b:
        insight_card("Concern", f"Focus rebound prep for: {', '.join(cooling)}.", "warn")

    section_header("Player Cards", "Compact performance cards with identity, role context, and key stats")

    rows = list(summary.iterrows())
    for i in range(0, len(rows), 3):
        cols = st.columns(3, gap="small")
        for c_idx, item in enumerate(rows[i : i + 3]):
            _, row = item
            merged = row.to_dict()
            meta = players_meta[
                players_meta.get("player_clean", players_meta.get("name", "")).astype(str).str.contains(str(row["player"]), case=False, regex=False)
            ]
            if not meta.empty:
                m = meta.iloc[0].to_dict()
                merged.update({"country": m.get("country", ""), "role": m.get("role", "")})

            merged["team_tag"] = "Medisports"
            merged["desc"] = player_description(row)
            merged["best_map"] = _context_for_player(df, str(row["player"]), "map")
            merged["best_side"] = _context_for_player(df, str(row["player"]), "side")
            merged["trend"] = _trend_for_player(df, str(row["player"]))

            with cols[c_idx]:
                player_card(merged)

    section_header("Squad Watchlist")
    top_player = summary.sort_values("grevscore", ascending=False).iloc[0]
    improved = summary.sort_values("form", ascending=False).iloc[0]
    coldest = summary.sort_values("form", ascending=True).iloc[0]

    w1, w2, w3 = st.columns(3, gap="small")
    with w1:
        insight_card("Top Performer", f"{top_player['player']} leads with {top_player['grevscore']:.1f} GrevScore.", "good")
    with w2:
        insight_card("Hottest Form", f"{improved['player']} is trending up in recent matches.", "info")
    with w3:
        insight_card("Concern", f"{coldest['player']} is in a colder form window.", "bad")
