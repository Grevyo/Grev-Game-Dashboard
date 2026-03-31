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
        "bg": "#06080c",
        "surface": "#11161d",
        "text": "#edf1f6",
        "muted": "#93a0b2",
        "accent": "#c43d33",
        "border": "#2a323e",
        "good": "#2e9f64",
        "mid": "#d8a546",
        "poor": "#be6f35",
        "bad": "#b64646",
    },
    "Light": {
        "bg": "#f3f6fb",
        "surface": "#ffffff",
        "text": "#111827",
        "muted": "#4b5563",
        "accent": "#9c2f2f",
        "border": "#d6dbe8",
        "good": "#1f9d66",
        "mid": "#bf8c00",
        "poor": "#d66a00",
        "bad": "#cc2f2f",
    },
}

TIER_COLORS = {"S": "#FFD166", "A": "#9D4EDD", "B": "#3A86FF", "C": "#2AA876"}
