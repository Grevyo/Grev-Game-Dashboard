def get_competition_display_col(mode: str | None) -> str:
    """Return the competition column to use for filtering and display."""
    return "grouped_competition_name" if mode == "Grouped competitions" else "raw_competition_name"


def competition_cols_for_mode(mode: str | None) -> list[str]:
    """Preferred-to-legacy fallback columns for the selected competition mode."""
    primary = get_competition_display_col(mode)
    if primary == "grouped_competition_name":
        return ["grouped_competition_name", "competition_group", "competition"]
    return ["raw_competition_name", "competition"]

