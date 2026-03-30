from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
IMAGES = {
    "competition_logos": ROOT / "competition_logos",
    "map_images": ROOT / "map_images",
    "achievements": ROOT / "Achievement_png",
    "team_logos": ROOT / "team_logos",
    "player_photos": ROOT / "player_photos",
}

FILES = {
    "players": DATA_DIR / "players.csv",
    "player_matches": DATA_DIR / "PlayerDataMatser.csv",
    "tactics": DATA_DIR / "TacticsDataMaster.csv",
    "achievements": DATA_DIR / "Achievements.csv",
}
REQUIRED_FILES = ("players", "player_matches", "tactics", "achievements")

THEMES = {
    "Dark": {
        "bg": "#0b1020",
        "surface": "#111831",
        "text": "#e9ecf7",
        "muted": "#97a1c0",
        "accent": "#46d9ff",
        "border": "#283353",
        "good": "#21c77a",
        "mid": "#f3c948",
        "poor": "#ff9e45",
        "bad": "#f85959",
    },
    "Light": {
        "bg": "#f3f6fb",
        "surface": "#ffffff",
        "text": "#111827",
        "muted": "#4b5563",
        "accent": "#0a84ff",
        "border": "#d6dbe8",
        "good": "#1f9d66",
        "mid": "#bf8c00",
        "poor": "#d66a00",
        "bad": "#cc2f2f",
    },
}

TIER_COLORS = {"S": "#FFD166", "A": "#9D4EDD", "B": "#3A86FF", "C": "#2AA876"}
