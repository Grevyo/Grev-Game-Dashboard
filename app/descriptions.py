from app.metrics import confidence_from_sample, trend_label


def player_description(row):
    trend = "up" if row.get("form", 0) >= row.get("grevscore", 0) else "steady"
    best_map = row.get("best_map") or "current map pool"
    return (
        f"Form is trending {trend} with {row.get('grevscore', 0):.2f} GrevScore and "
        f"{row.get('kpd', 0):.2f} K/D, strongest on {best_map}."
    )


def matchup_insight(name, wins, losses, wr, sample):
    confidence = confidence_from_sample(sample)
    state = "favorable" if wr >= 55 else "difficult" if wr < 45 else "balanced"
    return f"Vs {name}: {wins}-{losses} ({wr:.1f}% WR) is {state}. Confidence: {confidence}."


def tactic_reason(tactic, score, trend, sample):
    conf = confidence_from_sample(sample)
    return f"{tactic} selected for score {score:.1f}, trend {trend}, confidence {conf} (n={sample:.0f})."
