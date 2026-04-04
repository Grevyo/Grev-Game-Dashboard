import re
import shlex
import unicodedata
import warnings
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from app.config import FILES, REQUIRED_FILES
from app.datetime_utils import normalize_time_series
from app.grouping import build_season_resolution_debug_table, normalize_competitions

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

MEDISPORTS_ALIASES = {
    "medisports",
    "medisport",
    "medisportsm",
    "med",
    "m",
}
MEDISPORTS_PLAYER_MARKER = "ⓜ"

SIDE_NORMALIZATION_MAP = {
    "red": "Red",
    "redside": "Red",
    "t": "Red",
    "tside": "Red",
    "attack": "Red",
    "attacking": "Red",
    "attacker": "Red",
    "attackers": "Red",
    "offense": "Red",
    "offence": "Red",
    "offensive": "Red",
    "blue": "Blue",
    "blueside": "Blue",
    "ct": "Blue",
    "ctside": "Blue",
    "counterterrorist": "Blue",
    "counter-terrorist": "Blue",
    "counter terrorist": "Blue",
    "defense": "Blue",
    "defence": "Blue",
    "defending": "Blue",
    "defender": "Blue",
    "defenders": "Blue",
    "defensive": "Blue",
}

PLAYER_MATCHES_NUMERIC_COLUMNS = (
    "kills",
    "deaths",
    "mvps",
    "kpd",
    "kd",
    "kda",
    "accuracy_pct",
    "hs_pct",
    "damage",
    "rounds_played",
    "wins",
    "losses",
    "total_rounds",
    "win_rate_pct",
    "kpr",
    "mvp_rate",
    "grevscore",
    "rating",
    "impact",
    "form",
    "matches",
    "appearance_share",
    "play_count",
    "sample_size",
)

TACTICS_NUMERIC_COLUMNS = (
    "wins",
    "losses",
    "total_rounds",
    "win_rate_pct",
    "rounds",
    "rounds_played",
    "sample_size",
    "play_count",
    "matches",
    "score",
    "rating",
    "impact",
    "form",
    "confidence",
    "recommendation_score",
    "recent_wr",
    "baseline_wr",
    "delta_vs_baseline",
    "s_tier_delta",
    "c_tier_inflation",
    "distinct_tactics",
    "competitiveness",
    "depth_score",
    "context_signal",
    "stomp_penalty",
)

def normalize_player_key(name: str | None) -> str:
    """Normalize player names into a stable comparison key."""
    text = str(name or "").strip()
    text = re.sub(r"^ⓜ\s*\|\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()

def normalize_team_name(team_name: str | None) -> str:
    """Normalize stylized team names into a compact comparison key."""
    if team_name is None:
        return ""
    text = unicodedata.normalize("NFKD", str(team_name)).casefold()
    text = "".join(ch for ch in text if ch.isalnum())
    return text


def is_medisports_team(team_name: str | None) -> bool:
    key = normalize_team_name(team_name)
    return any(alias in key for alias in MEDISPORTS_ALIASES) if key else False


def is_medisports_player(player_name: str | None) -> bool:
    return MEDISPORTS_PLAYER_MARKER in str(player_name or "")


def normalize_side_label(value: str | None) -> str:
    """Normalize side aliases to the canonical dashboard labels (Red/Blue)."""
    text = str(value or "").strip()
    if not text:
        return ""
    key = re.sub(r"[^a-z0-9]+", "", text.casefold())
    return SIDE_NORMALIZATION_MAP.get(key, text.title())


def get_medisports_player_names(df: pd.DataFrame, player_col: str = "player") -> list[str]:
    if df.empty or player_col not in df.columns:
        return []

    names = (
        df[player_col]
        .dropna()
        .astype(str)
        .str.strip()
    )
    names = names[names.str.contains(MEDISPORTS_PLAYER_MARKER, regex=False)]
    if names.empty:
        return []

    cleaned = names.str.replace(r"\s+", " ", regex=True).str.replace(r"\s*\|\s*", " | ", regex=True).str.strip()
    unique = {}
    for value in cleaned.sort_values(key=lambda s: s.str.casefold()).tolist():
        key = value.casefold()
        if key not in unique:
            unique[key] = value
    return list(unique.values())


def get_medisports_roster_df(df: pd.DataFrame, player_col: str = "player") -> pd.DataFrame:
    if df.empty or player_col not in df.columns:
        return df.iloc[0:0].copy()
    mask = df[player_col].map(is_medisports_player)
    return df[mask].copy()


def medisports_player_roster(df: pd.DataFrame, player_col: str = "player") -> list[str]:
    """Backward-compatible alias for existing imports."""
    return get_medisports_player_names(df, player_col=player_col)


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


def _read_players_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    parsed_rows: list[list[str]] = []
    row_shape_issues: list[tuple[int, int, int]] = []
    expected_cols = 0

    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                tokens = shlex.split(line)
                if not tokens:
                    continue
                if not parsed_rows:
                    parsed_rows.append(tokens)
                    expected_cols = len(tokens)
                    continue
                original_width = len(tokens)
                if len(tokens) < expected_cols:
                    tokens = tokens + [""] * (expected_cols - len(tokens))
                elif len(tokens) > expected_cols:
                    tokens = tokens[:expected_cols]
                if original_width != expected_cols:
                    row_shape_issues.append((line_number, original_width, expected_cols))
                parsed_rows.append(tokens)
    except Exception:
        return pd.DataFrame()

    if not parsed_rows:
        return pd.DataFrame()

    if row_shape_issues:
        issue_preview = ", ".join(
            f"line {line_no} ({found}→{expected})"
            for line_no, found, expected in row_shape_issues[:8]
        )
        if len(row_shape_issues) > 8:
            issue_preview += ", ..."
        warnings.warn(
            (
                f"players.csv row width mismatch detected; padded/truncated rows to {expected_cols} columns: "
                f"{issue_preview}"
            ),
            stacklevel=2,
        )

    header = parsed_rows[0]
    rows = parsed_rows[1:]
    if not rows:
        return _normalize_columns(pd.DataFrame(columns=header))
    return _normalize_columns(pd.DataFrame(rows, columns=header))


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


def safe_to_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.replace(
        {
            "": pd.NA,
            "nan": pd.NA,
            "none": pd.NA,
            "null": pd.NA,
            "n/a": pd.NA,
            "na": pd.NA,
        }
    )
    cleaned = cleaned.str.replace(",", "", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def coerce_numeric_columns(
    df: pd.DataFrame,
    columns: Iterable[str],
    *,
    dataset_name: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    debug_rows: list[str] = []
    for column in columns:
        if column not in out.columns:
            continue

        raw = out[column]
        stripped = raw.astype("string").str.strip()
        converted = safe_to_numeric(raw)
        raw_non_null = int(raw.notna().sum())
        converted_non_null = int(converted.notna().sum())
        nan_after_coerce = int((converted.isna() & stripped.notna() & stripped.ne("")).sum())
        object_source = bool(pd.api.types.is_object_dtype(raw) or pd.api.types.is_string_dtype(raw))

        out[column] = converted
        debug_rows.append(
            f"{column}: non-null {raw_non_null}->{converted_non_null}, "
            f"source={'text' if object_source else 'numeric'}, nan_after_coerce={nan_after_coerce}"
        )

    if debug_rows:
        print(f"[NUMERIC_COERCE] dataset={dataset_name}")
        for row in debug_rows:
            print(f"[NUMERIC_COERCE] {row}")
    return out


def _required_file_keys() -> tuple[str, ...]:
    return REQUIRED_FILES


def _validate_required_files() -> None:
    missing_files: list[Path] = []
    for file_key in _required_file_keys():
        file_path = FILES[file_key]
        if not file_path.exists():
            missing_files.append(file_path)
    if missing_files:
        missing_details = "\n".join(f"- {path}" for path in missing_files)
        raise FileNotFoundError(
            "Required data file(s) missing. Restore the files under the configured data/ directory:\n"
            f"{missing_details}"
        )


def _build_file_signature() -> tuple[tuple[str, str, int, int], ...]:
    signatures: list[tuple[str, str, int, int]] = []
    for file_key in _required_file_keys():
        file_path = FILES[file_key]
        stat = file_path.stat()
        signatures.append((file_key, str(file_path), stat.st_mtime_ns, stat.st_size))
    return tuple(signatures)



def _derive_core(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = _rename_known_columns(df)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "time" in df.columns:
        time_values = df["time"].astype("object")
        df["time_raw"] = time_values
        df["time"] = normalize_time_series(time_values)
    if "map" in df.columns:
        df["map"] = df["map"].astype(str).str.title().str.strip()
    if "side" in df.columns:
        df["side"] = df["side"].map(normalize_side_label)
    if "competition" in df.columns:
        df["raw_competition_name"] = df["competition"].fillna("").astype(str).str.strip()
    elif "raw_competition_name" in df.columns:
        df["raw_competition_name"] = df["raw_competition_name"].fillna("").astype(str).str.strip()
    elif "grouped_competition_name" in df.columns:
        # Legacy edge-case: grouped existed without raw; preserve row-level identity.
        df["raw_competition_name"] = df["grouped_competition_name"].fillna("").astype(str).str.strip()

    if "raw_competition_name" in df.columns and "competition" not in df.columns:
        # Ensure legacy callers still have a `competition` column if only raw_* is present.
        df["competition"] = df["raw_competition_name"]

    if "raw_competition_name" in df.columns:
        df = normalize_competitions(df, name_col="raw_competition_name", date_col="date")

    if "raw_competition_name" in df.columns and "grouped_competition_name" not in df.columns:
        # Failsafe for any unexpected input shape.
        df["grouped_competition_name"] = df["raw_competition_name"]
    if "grouped_competition_name" in df.columns and "raw_competition_name" not in df.columns:
        df["raw_competition_name"] = df["grouped_competition_name"]
    if "competition_group" not in df.columns and "grouped_competition_name" in df.columns:
        df["competition_group"] = df["grouped_competition_name"]
    if "player" in df.columns and "player_has_game_data" not in df.columns:
        df["player_has_game_data"] = True
    return df


def _dedupe_tactics_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    cleaned = df.copy()
    unnamed_cols = [c for c in cleaned.columns if str(c).strip().lower().startswith("unnamed:")]
    if unnamed_cols:
        cleaned = cleaned.drop(columns=unnamed_cols, errors="ignore")

    dedupe_keys = [
        "match_id",
        "date",
        "time",
        "map",
        "competition",
        "my_team",
        "opponent_team",
        "side",
        "tactic_name",
        "wins",
        "losses",
        "total_rounds",
        "win_rate_pct",
    ]
    existing_keys = [col for col in dedupe_keys if col in cleaned.columns]
    if not existing_keys:
        return cleaned

    return cleaned.drop_duplicates(subset=existing_keys, keep="first").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def _load_data_cached(_file_signature: tuple[tuple[str, str, int, int], ...]) -> dict[str, pd.DataFrame]:
    player_matches = _derive_core(_read_flexible_csv(FILES["player_matches"]))
    tactics = _derive_core(_read_flexible_csv(FILES["tactics"]))
    achievements = _derive_core(_read_flexible_csv(FILES["achievements"]))
    players = _derive_core(_read_players_csv_safe(FILES["players"]))

    if "" in tactics.columns and "tier" not in tactics.columns:
        tactics = tactics.rename(columns={"": "tier"})
    tactics = coerce_numeric_columns(tactics, TACTICS_NUMERIC_COLUMNS, dataset_name="tactics")
    tactics = _dedupe_tactics_rows(tactics)
    player_matches = coerce_numeric_columns(
        player_matches,
        PLAYER_MATCHES_NUMERIC_COLUMNS,
        dataset_name="player_matches",
    )

    if "player" in players.columns:
        players["player_clean"] = players["player"].map(normalize_player_key)
    elif "name" in players.columns:
        players["player_clean"] = players["name"].map(normalize_player_key)

    if "country" in players.columns and "nationality" not in players.columns:
        players["nationality"] = players["country"]

    for df in [player_matches, achievements]:
        if "player" in df.columns:
            df["player_clean"] = df["player"].map(normalize_player_key)

    if "player_clean" in players.columns:
        players["player_clean"] = players["player_clean"].map(normalize_player_key)

    # Temporary debug export to validate row-level season resolution.
    if not player_matches.empty:
        debug_table = build_season_resolution_debug_table(player_matches)
        if not debug_table.empty:
            debug_table.to_csv(Path("data/season_resolution_debug.csv"), index=False)

    # Focused debug trace for CPL Open achievement retention.
    achievement_path = FILES["achievements"]
    print(f"[ACH_DEBUG] achievements_file_path={achievement_path}")
    print(f"[ACH_DEBUG] achievements_row_count={len(achievements)}")
    print(f"[ACH_DEBUG] achievements_columns={list(achievements.columns)}")
    if "achievement_name" in achievements.columns:
        cpl_open_mask = achievements["achievement_name"].astype(str).str.contains("CPL Open", case=False, na=False)
        cpl_open_rows = achievements[cpl_open_mask]
        print("[ACH_DEBUG] loaded_rows_where_achievement_name_contains_CPL_Open")
        if cpl_open_rows.empty:
            print("[ACH_DEBUG] (none)")
        else:
            cols = [c for c in ["player", "achievement_name", "season_name", "position"] if c in cpl_open_rows.columns]
            print(cpl_open_rows[cols].to_string(index=False))
    if {"player", "achievement_name"}.issubset(achievements.columns):
        debug_player = "ⓜ | 8eeR"
        player_rows = achievements[achievements["player"].astype(str) == debug_player]
        print(f"[ACH_DEBUG] all_loaded_rows_for_player={debug_player}")
        if player_rows.empty:
            print("[ACH_DEBUG] (none)")
        else:
            cols = [c for c in ["player", "achievement_name", "season_name", "position"] if c in player_rows.columns]
            print(player_rows[cols].to_string(index=False))
            player_cpl_rows = player_rows[player_rows["achievement_name"].astype(str).str.contains("CPL Open", case=False, na=False)]
            print(f"[ACH_DEBUG] loaded_rows_for_player_where_achievement_name_contains_CPL_Open={debug_player}")
            if player_cpl_rows.empty:
                print("[ACH_DEBUG] (none)")
            else:
                print(player_cpl_rows[cols].to_string(index=False))

    return {
        "player_matches": player_matches,
        "tactics": tactics,
        "achievements": achievements,
        "players": players,
    }


def load_data() -> dict[str, pd.DataFrame]:
    _validate_required_files()
    file_signature = _build_file_signature()
    return _load_data_cached(file_signature)


def detect_our_team(player_matches: pd.DataFrame, tactics: pd.DataFrame) -> str:
    team_cols = []
    for df in [player_matches, tactics]:
        if not df.empty and "my_team" in df.columns:
            team_cols.extend(df["my_team"].dropna().tolist())
    if not team_cols:
        return "Medisports"
    s = pd.Series(team_cols).astype(str)
    likely = s[s.map(is_medisports_team)]
    return likely.mode().iloc[0] if not likely.empty else s.mode().iloc[0]


def validate_columns(df: pd.DataFrame, required: list[str], name: str) -> list[str]:
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.warning(f"{name} is missing columns: {', '.join(missing)}. Related sections are degraded.")
    return missing
