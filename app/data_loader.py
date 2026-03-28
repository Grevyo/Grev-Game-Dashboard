import re
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from app.config import FILES

SYNONYMS = {
    "date": ["date", "match_date"],
    "time": ["time", "match_time"],
    "map": ["map", "map_name"],
    "competition": ["competition", "tournament", "event"],
    "my_team": ["my_team", "team", "our_team"],
    "opponent_team": ["opponent_team", "opponent", "vs_team"],
    "player": ["player", "name"],
    "tier": ["tier", "league_tier"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _read_flexible_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    for delimiter in [",", "|", " "]:
        try:
            df = pd.read_csv(path, delimiter=delimiter, engine="python")
            if len(df.columns) >= 3:
                return _normalize_columns(df)
        except Exception:
            continue
    try:
        return _normalize_columns(pd.read_csv(path, sep=None, engine="python"))
    except Exception:
        return pd.DataFrame()


def _best_col(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def _rename_known_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for target, candidates in SYNONYMS.items():
        col = _best_col(df, candidates)
        if col:
            rename_map[col] = target
    return df.rename(columns=rename_map)


def _safe_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _extract_comp_group(comp: str) -> tuple[str, str | None]:
    if not isinstance(comp, str) or not comp.strip():
        return "Unknown Competition", None
    text = comp.strip()
    family = re.sub(r"([#sꜱ]?\d+[\.]?\d*)$", "", text, flags=re.IGNORECASE).strip(" -_")
    season_match = re.search(r"(?:season|s|ꜱ)\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    season = season_match.group(1) if season_match else None
    if not family:
        family = text
    grouped = f"{family} Season {season}" if season else family
    return grouped, season


def _derive_core(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = _rename_known_columns(df)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "time" in df.columns:
        df["time"] = df["time"].astype(str).str.strip()
    if "map" in df.columns:
        df["map"] = df["map"].astype(str).str.title().str.strip()
    if "side" in df.columns:
        df["side"] = df["side"].astype(str).str.title().replace({"Ct": "Blue", "T": "Red"})
    if "competition" in df.columns:
        comp_info = df["competition"].fillna("").map(_extract_comp_group)
        df["competition_group"] = comp_info.map(lambda x: x[0])
        df["season"] = comp_info.map(lambda x: x[1])
    return df


@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    player_matches = _derive_core(_read_flexible_csv(FILES["player_matches"]))
    tactics = _derive_core(_read_flexible_csv(FILES["tactics"]))
    achievements = _derive_core(_read_flexible_csv(FILES["achievements"]))
    players = _derive_core(_read_flexible_csv(FILES["players"]))

    tactics = tactics.rename(columns={"": "tier"})
    tactics = _safe_numeric(tactics, ["wins", "losses", "total_rounds", "win_rate_pct"])
    player_matches = _safe_numeric(
        player_matches,
        [
            "kills",
            "deaths",
            "mvps",
            "kpd",
            "accuracy_pct",
            "hs_pct",
            "damage",
            "rounds_played",
        ],
    )

    if "player" in players.columns:
        players["player_clean"] = players["player"].astype(str)
    elif "name" in players.columns:
        players["player_clean"] = players["name"].astype(str)

    for df in [player_matches, achievements]:
        if "player" in df.columns:
            df["player_clean"] = df["player"].astype(str).str.replace("ⓜ\s*\|\s*", "", regex=True).str.strip()

    if "player_clean" in players.columns:
        players["player_clean"] = players["player_clean"].astype(str).str.replace("ⓜ\s*\|\s*", "", regex=True).str.strip()

    return {
        "player_matches": player_matches,
        "tactics": tactics,
        "achievements": achievements,
        "players": players,
    }


def detect_our_team(player_matches: pd.DataFrame, tactics: pd.DataFrame) -> str:
    team_cols = []
    for df in [player_matches, tactics]:
        if not df.empty and "my_team" in df.columns:
            team_cols.extend(df["my_team"].dropna().tolist())
    if not team_cols:
        return "Medisports"
    s = pd.Series(team_cols).astype(str)
    likely = s[s.str.contains("med", case=False, regex=True)]
    return likely.mode().iloc[0] if not likely.empty else s.mode().iloc[0]


def validate_columns(df: pd.DataFrame, required: list[str], name: str) -> list[str]:
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.warning(f"{name} is missing columns: {', '.join(missing)}. Related sections are degraded.")
    return missing
