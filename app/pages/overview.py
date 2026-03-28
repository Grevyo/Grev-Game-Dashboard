import streamlit as st

from app.components import insight_card, player_card, section_header, stat_card
from app.descriptions import player_description
from app.image_helpers import find_player_photo
from app.transforms import best_contexts, summarize_player


def render(ctx):
    df = ctx["player_matches"]
    players_meta = ctx["players"]
    team_name = ctx["team_name"]

    st.title("Medisports Team Overview")
    st.caption(f"Team focus: {team_name}")

    if df.empty:
        st.warning("No rows available after filters.")
        return

    summary = summarize_player(df)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card("Players", summary["player"].nunique())
    with c2:
        stat_card("Avg GrevScore", f"{summary['grevscore'].mean():.1f}")
    with c3:
        stat_card("Avg Rating", f"{summary['rating'].mean():.2f}")
    with c4:
        stat_card("Matches", int(df["match_id"].nunique()))

    section_header("Squad Pulse", "Top and bottom trend signals from current filtered context.")
    hottest = summary.sort_values("form", ascending=False).head(2)["player"].tolist()
    cooling = summary.sort_values("form", ascending=True).head(2)["player"].tolist()
    insight_card("Strength", f"Best current form: {', '.join(hottest)}", "good")
    insight_card("Concern", f"Needs bounce-back: {', '.join(cooling)}", "warn")

    section_header("Players", "Performance cards with profile metadata and quick narratives")
    for _, row in summary.iterrows():
        merged = row.to_dict()
        meta = players_meta[players_meta.get("player_clean", players_meta.get("name", "")).astype(str).str.contains(str(row["player"]), case=False, regex=False)]
        if not meta.empty:
            m = meta.iloc[0].to_dict()
            merged.update({"country": m.get("country", ""), "role": m.get("role", "")})
        merged["desc"] = player_description(row)
        player_card(merged, photo_path=find_player_photo(str(row["player"])))

    maps = best_contexts(df, "map").head(5)
    sides = best_contexts(df, "side").head(5) if "side" in df.columns else None
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Best Maps")
        st.dataframe(maps, use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Best Sides")
        st.dataframe(sides if sides is not None else maps.head(0), use_container_width=True, hide_index=True)
