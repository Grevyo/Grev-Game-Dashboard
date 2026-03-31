GROUPED_COMPETITION_COL = "grouped_competition_name"
RAW_COMPETITION_COL = "raw_competition_name"


def is_grouped_mode(mode: str | None) -> bool:
    normalized = str(mode or "").strip().casefold()
    return normalized in {"grouped", "grouped competitions"}


def get_active_competition_col(group_mode: bool) -> str:
    """Central key selector for competition-level filtering/grouping."""
    return GROUPED_COMPETITION_COL if group_mode else RAW_COMPETITION_COL


def get_competition_display_col(mode: str | None) -> str:
    """Backward-compatible string-mode wrapper."""
    return get_active_competition_col(is_grouped_mode(mode))


def competition_cols_for_mode(mode: str | None) -> list[str]:
    """Preferred-to-legacy fallback columns for the selected competition mode."""
    primary = get_competition_display_col(mode)
    if primary == GROUPED_COMPETITION_COL:
        return [GROUPED_COMPETITION_COL, "competition_group", "competition"]
    return [RAW_COMPETITION_COL, "competition"]
