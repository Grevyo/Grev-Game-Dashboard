import re

from app.metrics import confidence_from_sample


def _clean_text(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    lowered = text.casefold()
    if lowered in {"nan", "none", "null", "n/a", "na"}:
        return ""
    return text


def _to_float(value, default: float = 0.0) -> float:
    cleaned = _clean_text(value)
    if not cleaned:
        return default
    try:
        number = float(cleaned)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return number


def _count_items(value) -> int:
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 0


def _safe_sentence(text: str) -> str:
    return _clean_text(text) or "No recent player note available."


def _qual(value: float, strong: float, mid: float) -> str:
    if value >= strong:
        return "strong"
    if value >= mid:
        return "stable"
    return "mixed"


def player_description(row):
    row = row if isinstance(row, dict) else {}

    grev = _to_float(row.get("grevscore", 0), 0)
    rating = _to_float(row.get("rating", 0), 0)
    form = _to_float(row.get("form", 0), 0)
    impact = _to_float(row.get("impact", 0), 0)
    kpd = _to_float(row.get("kpd", 0), 0)
    appearances = _to_float(row.get("appearance_share", 0), 0)
    achievements = _count_items(row.get("achievements", []))

    output_level = _qual(grev, strong=1.30, mid=1.00)
    consistency = (
        "improving"
        if form > grev + 0.05
        else "cooling"
        if form < grev - 0.05
        else "steady"
    )

    support_line = (
        "impact remains useful"
        if impact >= 17
        else "support impact is serviceable"
        if impact >= 13
        else "impact contribution is currently limited"
    )
    pedigree_line = (
        "with solid achievement pedigree"
        if achievements >= 3
        else "with some proven pedigree"
        if achievements >= 1
        else "with limited recent pedigree"
    )

    if appearances < 0.10:
        sample_note = "Limited recent sample"
    elif appearances > 0.35:
        sample_note = "Heavy recent usage"
    else:
        sample_note = "Healthy recent sample"

    frag_line = (
        "fragging output is high"
        if kpd >= 1.10
        else "fragging output is respectable"
        if kpd >= 0.95
        else "fragging output is below baseline"
    )

    if output_level == "strong":
        return _safe_sentence(
            f"{sample_note}; {frag_line} and {support_line}, {pedigree_line}. Form is {consistency}."
        )
    if output_level == "stable":
        return _safe_sentence(
            f"Stable production with {support_line}, {pedigree_line}. Recent form is {consistency} and rating sits around {rating:.2f}."
        )
    return _safe_sentence(
        f"Mixed recent output; {frag_line} and {support_line}. Form is {consistency}, though baseline remains recoverable."
    )


def matchup_insight(name, wins, losses, wr, sample):
    confidence = confidence_from_sample(sample)
    state = "favorable" if wr >= 55 else "difficult" if wr < 45 else "balanced"
    return f"Vs {name}: {wins}-{losses} ({wr:.1f}% WR) is {state}. Confidence: {confidence}."


def tactic_reason(tactic, score, trend, sample):
    conf = confidence_from_sample(sample)
    return f"{tactic} selected for score {score:.1f}, trend {trend}, confidence {conf} (n={sample:.0f})."
