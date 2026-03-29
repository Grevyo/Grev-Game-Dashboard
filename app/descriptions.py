from app.metrics import confidence_from_sample


def _qual(value: float, strong: float, mid: float) -> str:
    if value >= strong:
        return "strong"
    if value >= mid:
        return "stable"
    return "mixed"


def player_description(row):
    grev = float(row.get("grevscore", 0) or 0)
    rating = float(row.get("rating", 0) or 0)
    form = float(row.get("form", 0) or 0)
    impact = float(row.get("impact", 0) or 0)
    kpd = float(row.get("kpd", 0) or 0)
    appearances = float(row.get("appearance_share", 0) or 0)
    achievements = len(row.get("achievements", []) or [])

    output_level = _qual(grev, strong=1.30, mid=1.00)
    consistency = "improving" if form > grev + 0.05 else "cooling" if form < grev - 0.05 else "steady"

    support_line = "impact remains useful" if impact >= 17 else "support impact is serviceable" if impact >= 13 else "impact contribution is currently limited"
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

    frag_line = "fragging output is high" if kpd >= 1.10 else "fragging output is respectable" if kpd >= 0.95 else "fragging output is below baseline"

    if output_level == "strong":
        return f"{sample_note}; {frag_line} and {support_line}, {pedigree_line}. Form is {consistency}."
    if output_level == "stable":
        return f"Stable production with {support_line}, {pedigree_line}. Recent form is {consistency} and rating sits around {rating:.2f}."
    return f"Mixed recent output; {frag_line} and {support_line}. Form is {consistency}, though baseline remains recoverable."


def matchup_insight(name, wins, losses, wr, sample):
    confidence = confidence_from_sample(sample)
    state = "favorable" if wr >= 55 else "difficult" if wr < 45 else "balanced"
    return f"Vs {name}: {wins}-{losses} ({wr:.1f}% WR) is {state}. Confidence: {confidence}."


def tactic_reason(tactic, score, trend, sample):
    conf = confidence_from_sample(sample)
    return f"{tactic} selected for score {score:.1f}, trend {trend}, confidence {conf} (n={sample:.0f})."
