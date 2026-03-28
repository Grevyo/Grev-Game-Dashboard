import pandas as pd


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
