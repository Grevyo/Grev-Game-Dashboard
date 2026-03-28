import re

import pandas as pd

from app.descriptions import tactic_reason
from app.metrics import trend_label


def tactic_category(name: str) -> str:
    n = str(name).upper()
    if "(P)" in n or n.startswith("P"):
        return "Pistol"
    if "(E)" in n or n.startswith("E"):
        return "Eco"
    return "Standard"


def route_key(name: str) -> str:
    n = str(name).upper()
    patterns = ["A MID", "A HALL", "A MAIN", "B IVY", "B HALL", "B MAIN", "MID", "A", "B"]
    for p in patterns:
        if p in n:
            return p
    cleaned = re.sub(r"[^A-Z0-9]+", " ", n)
    return " ".join(cleaned.split()[:3])


def tactic_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
    x["category"] = x["tactic_name"].map(tactic_category)
    agg = (
        x.groupby(["map", "side", "tactic_name", "category"], dropna=False)
        .agg(wins=("wins", "sum"), losses=("losses", "sum"), uses=("total_rounds", "sum"))
        .reset_index()
    )
    agg["win_rate"] = (agg["wins"] / (agg["wins"] + agg["losses"]).clip(lower=1) * 100).fillna(0)
    agg["score"] = agg["win_rate"] * 0.6 + agg["uses"].clip(upper=25) * 1.6
    agg["route_key"] = agg["tactic_name"].map(route_key)
    agg["trend"] = agg["win_rate"].map(lambda w: "Rising" if w >= 60 else "Falling" if w < 45 else "Flat")
    agg["reason"] = agg.apply(lambda r: tactic_reason(r["tactic_name"], r["score"], r["trend"], r["uses"]), axis=1)
    return agg


def tactic_bucket(row) -> str:
    if row["uses"] < 5 and row["win_rate"] >= 55:
        return "Promising / needs more data"
    if row["win_rate"] >= 62 and row["uses"] >= 5:
        return "Working well"
    if row["win_rate"] < 40 and row["uses"] >= 5:
        return "Drop / not working"
    if row["win_rate"] < 50:
        return "Falling off"
    return "Neutral / situational"


def recommend_set(summary: pd.DataFrame, map_name: str, side: str) -> pd.DataFrame:
    pool = summary[(summary["map"] == map_name) & (summary["side"] == side)].copy()
    if pool.empty:
        return pool

    pool["bucket"] = pool.apply(tactic_bucket, axis=1)
    picks = []

    def pick(category, n, include=None):
        local = pool[pool["category"] == category].sort_values(["score", "uses"], ascending=False)
        chosen_routes = set()
        count = 0
        for _, row in local.iterrows():
            if include and include not in row["tactic_name"].upper():
                continue
            if row["route_key"] in chosen_routes:
                continue
            picks.append(row)
            chosen_routes.add(row["route_key"])
            count += 1
            if count >= n:
                break

    pick("Pistol", 1)
    pick("Eco", 2)
    pick("Standard", 2, include="A")
    pick("Standard", 2, include="B")

    out = pd.DataFrame(picks).drop_duplicates(subset=["tactic_name"]) if picks else pd.DataFrame()
    return out.sort_values("score", ascending=False)
