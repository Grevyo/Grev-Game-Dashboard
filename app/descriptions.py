from app.metrics import confidence_from_sample, trend_label


def player_description(row):
    trend = "hot" if row.get("form", 0) >= row.get("grevscore", 0) else "cooling"
    return (
        f"{row.get('player')} is {trend}; GrevScore {row.get('grevscore', 0):.1f}, "
        f"K/D {row.get('kpd', 0):.2f}, Accuracy {row.get('accuracy_pct', 0):.1f}%."
    )


def matchup_insight(name, wins, losses, wr, sample):
    confidence = confidence_from_sample(sample)
    state = "favorable" if wr >= 55 else "difficult" if wr < 45 else "balanced"
    return f"Vs {name}: {wins}-{losses} ({wr:.1f}% WR) is {state}. Confidence: {confidence}."


def tactic_reason(tactic, score, trend, sample):
    conf = confidence_from_sample(sample)
    return f"{tactic} selected for score {score:.1f}, trend {trend}, confidence {conf} (n={sample:.0f})."
