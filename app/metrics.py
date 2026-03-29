import pandas as pd

DEFAULT_STAT_BANDS = (0.7, 1.0, 1.35)
STAT_BANDS = {
    "grevscore": (0.75, 1.0, 1.4),
    "rating": (0.85, 1.0, 1.2),
    "impact": (20.0, 26.0, 32.0),
    "form": (0.8, 1.0, 1.3),
    "k/d": (0.85, 1.0, 1.2),
    "kpr": (0.6, 0.75, 0.95),
    "accuracy": (30.0, 38.0, 46.0),
    "hs%": (35.0, 45.0, 55.0),
}


def confidence_from_sample(n: float) -> str:
    if n >= 40:
        return "High"
    if n >= 20:
        return "Medium"
    return "Low"


def trend_label(series: pd.Series) -> str:
    if len(series) < 2:
        return "Flat"
    delta = series.tail(3).mean() - series.head(3).mean()
    if delta > 3:
        return "Rising"
    if delta < -3:
        return "Falling"
    return "Flat"


def win_rate(w: pd.Series, l: pd.Series) -> pd.Series:
    total = w + l
    return (w / total * 100).fillna(0)


def classify_quality(score: float) -> str:
    if score >= 70:
        return "good"
    if score >= 55:
        return "mid"
    if score >= 40:
        return "poor"
    return "bad"


def stat_tone(stat_name: str, value: float) -> str:
    key = str(stat_name or "").strip().lower()
    low, mid, high = STAT_BANDS.get(key, DEFAULT_STAT_BANDS)
    if value >= high:
        return "good"
    if value >= mid:
        return "mid"
    if value >= low:
        return "poor"
    return "bad"
