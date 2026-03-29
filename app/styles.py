import streamlit as st

from app.config import TIER_COLORS, THEMES


def inject_styles(theme_name: str = "Dark"):
    theme = THEMES.get(theme_name, THEMES["Dark"])
    css = f"""
    <style>
    :root {{
      --bg: {theme['bg']};
      --surface: {theme['surface']};
      --surface-soft: color-mix(in srgb, {theme['surface']} 88%, #fff 12%);
      --text: {theme['text']};
      --muted: {theme['muted']};
      --accent: {theme['accent']};
      --border: {theme['border']};
      --good: {theme['good']};
      --mid: {theme['mid']};
      --poor: {theme['poor']};
      --bad: {theme['bad']};
      --space-1: 4px;
      --space-2: 8px;
      --space-3: 12px;
      --space-4: 16px;
      --space-5: 20px;
      --space-6: 24px;
      --space-7: 32px;
      --radius-s: 10px;
      --radius-m: 14px;
      --radius-l: 18px;
    }}

    .stApp {{ background: radial-gradient(circle at 0% 0%, color-mix(in srgb, var(--accent) 8%, transparent), transparent 42%), var(--bg); color: var(--text); }}
    .block-container {{ padding-top: 0.9rem; padding-bottom: 1.4rem; max-width: 98%; }}

    .page-shell {{ display:flex; flex-direction:column; gap: var(--space-5); }}
    .section-title {{ margin: 0 0 var(--space-2) 0; font-size: 1.05rem; font-weight: 750; letter-spacing: 0.02em; color: var(--text); }}
    .section-subtitle {{ color: var(--muted); font-size: 0.82rem; margin-bottom: var(--space-3); }}

    .chip {{
      display:inline-flex; align-items:center; gap:6px;
      padding:4px 10px; border-radius:999px; border:1px solid var(--border);
      font-size:11px; margin-right:6px; margin-bottom:6px; color: var(--text);
      background: color-mix(in srgb, var(--surface) 72%, var(--accent) 28%);
      letter-spacing: 0.02em;
    }}
    .chip-good {{ background: color-mix(in srgb, var(--good) 18%, transparent); border-color: color-mix(in srgb, var(--good) 45%, var(--border)); }}
    .chip-mid {{ background: color-mix(in srgb, var(--mid) 22%, transparent); border-color: color-mix(in srgb, var(--mid) 45%, var(--border)); }}
    .chip-poor {{ background: color-mix(in srgb, var(--poor) 20%, transparent); border-color: color-mix(in srgb, var(--poor) 45%, var(--border)); }}
    .chip-bad {{ background: color-mix(in srgb, var(--bad) 18%, transparent); border-color: color-mix(in srgb, var(--bad) 50%, var(--border)); }}

    .panel {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 91%, #fff 9%), var(--surface));
      border: 1px solid var(--border);
      border-radius: var(--radius-m);
      padding: var(--space-4);
      box-shadow: 0 10px 24px rgba(0,0,0,0.18);
      height: 100%;
    }}
    .panel-tight {{ padding: var(--space-3); }}
    .accent-good {{ border-top: 3px solid var(--good); }}
    .accent-mid {{ border-top: 3px solid var(--mid); }}
    .accent-poor {{ border-top: 3px solid var(--poor); }}
    .accent-bad {{ border-top: 3px solid var(--bad); }}

    .hero-band {{
      padding: var(--space-5);
      border-radius: var(--radius-l);
      border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
      background:
        radial-gradient(circle at 100% 0%, color-mix(in srgb, var(--accent) 20%, transparent), transparent 35%),
        linear-gradient(180deg, color-mix(in srgb, var(--surface) 90%, #fff 10%), var(--surface));
    }}

    .metric-title {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .metric-value {{ font-size: 25px; line-height: 1.15; font-weight: 760; margin-top: 3px; }}

    .top-nav {{
      display:flex; align-items:center; gap: 10px; padding: 8px 10px;
      background: color-mix(in srgb, var(--surface) 94%, #fff 6%);
      border: 1px solid var(--border); border-radius: 999px;
      margin-bottom: 12px;
    }}

    .context-ribbon {{
      background: color-mix(in srgb, var(--surface) 95%, #fff 5%);
      border: 1px solid var(--border);
      border-radius: var(--radius-m);
      padding: 10px 12px;
      margin-bottom: 14px;
    }}

    .player-card {{
      min-height: 690px;
      height: 690px;
      display:flex;
      flex-direction:column;
      gap: 8px;
      overflow: hidden;
    }}
    .player-head {{ display:flex; align-items:flex-start; gap:10px; min-height: 148px; }}
    .player-head-left {{ flex:0 0 92px; display:flex; flex-direction:column; gap:6px; }}
    .player-head-meta {{ flex:1; min-width:0; display:flex; flex-direction:column; gap:4px; min-height: 0; }}
    .player-avatar-frame {{
      width: 92px; height: 116px; border-radius: 10px; overflow:hidden;
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--surface) 72%, #fff 28%);
      display:flex; align-items:center; justify-content:center;
    }}
    .player-avatar {{
      width: 100%; height: 100%; object-fit: cover;
      border-radius: 0;
      background: color-mix(in srgb, var(--surface) 72%, #fff 28%);
    }}
    .fallback-avatar {{ display:flex; align-items:center; justify-content:center; font-size:10px; color: var(--muted); }}
    .team-mini-logo {{
      width: 26px; height: 26px; object-fit: contain;
      border-radius: 8px; padding: 3px;
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--surface) 70%, #fff 30%);
    }}
    .hero-logo {{ width: 72px; height: 72px; object-fit: contain; border-radius: 12px; border: 1px solid var(--border); padding: 6px; background: color-mix(in srgb, var(--surface) 72%, #fff 28%); }}
    .hero-player-photo-frame {{
      width: 152px; height: 192px; border-radius: 16px; overflow:hidden;
      border: 1px solid var(--border); flex: 0 0 auto;
      background: color-mix(in srgb, var(--surface) 72%, #fff 28%);
    }}
    .hero-player-photo {{ width: 100%; height: 100%; object-fit: cover; border-radius: 0; border: 0; }}
    .achievement-thumb, .competition-thumb, .map-thumb {{
      width: 42px; height: 42px; object-fit: contain;
      border-radius: 10px; border: 1px solid var(--border);
      padding: 4px; background: color-mix(in srgb, var(--surface) 72%, #fff 28%);
      margin-bottom: 8px;
    }}

    .player-head-title-row {{ display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }}
    .player-name-row {{ display:flex; align-items:center; gap:6px; min-width:0; flex-wrap:wrap; }}
    .player-name {{ font-size: 0.91rem; font-weight: 720; margin: 0; line-height:1.25; }}
    .identity-line {{ color: var(--muted); font-size: 11px; margin: 0; line-height: 1.3; }}
    .fame-line {{ display:flex; align-items:center; gap:6px; margin-top:1px; }}
    .fame-label {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .fame-stars {{ font-size: 13px; letter-spacing: 0.08em; color: color-mix(in srgb, var(--mid) 70%, #fff 30%); }}
    .fame-value {{ color: var(--muted); font-size: 10px; }}
    .player-meta-row {{ display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }}
    .achievement-strip {{
      display:flex;
      flex-direction: row;
      flex-wrap: nowrap;
      gap: 7px;
      min-height: 76px;
      max-height: 76px;
      align-items:stretch;
      overflow: hidden;
    }}
    .achievement-strip-featured {{ margin-top: 0; }}
    .achievement-empty {{
      display:flex;
      align-items:center;
      justify-content:center;
      width: 100%;
      border: 1px dashed var(--border);
      border-radius: 8px;
      color: var(--muted);
      font-size: 10px;
    }}
    .achievement-tile {{
      position: relative;
      flex: 0 0 68px;
      width: 68px;
      height: 76px;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      background: color-mix(in srgb, var(--surface) 88%, #fff 12%);
      box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }}
    .achievement-tile-thumb {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      filter: saturate(1.05);
    }}
    .achievement-tile-thumb-fallback {{
      display:flex;
      align-items:center;
      justify-content:center;
      font-size: 8px;
      color: var(--muted);
    }}
    .achievement-tile-overlay {{
      position: absolute;
      left: 0; right: 0; bottom: 0;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      padding: 4px 4px 3px;
      gap: 1px;
      background: linear-gradient(180deg, transparent 0%, rgba(8,12,20,0.58) 100%);
    }}
    .achievement-tier {{
      padding: 0 4px; border-radius: 999px; font-size: 8px; font-weight: 750; letter-spacing: 0.03em;
      border: 1px solid currentColor; align-self: flex-start;
    }}
    .achievement-season {{
      color: #eef2ff;
      font-size: 8px;
      line-height: 1.1;
      font-weight: 600;
      text-shadow: 0 1px 2px rgba(0,0,0,0.6);
      white-space: nowrap;
    }}
    .achievement-overflow {{
      flex: 0 0 68px;
      width: 68px;
      height: 76px;
      display:flex;
      align-items:center;
      justify-content:center;
      border: 1px dashed color-mix(in srgb, var(--accent) 40%, var(--border));
      border-radius: 8px;
      background: color-mix(in srgb, var(--surface) 75%, var(--accent) 25%);
      color: var(--text);
      font-size: 12px;
      font-weight: 760;
    }}
    .stats-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 2px; }}
    .stat-item {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 82%, #0a1220 18%), color-mix(in srgb, var(--surface) 94%, #05080f 6%));
      border: 1px solid color-mix(in srgb, var(--border) 72%, #0f1727 28%);
      border-radius: 11px;
      padding: 8px 10px 9px 10px;
      position: relative;
      overflow: hidden;
      box-shadow: 0 8px 18px rgba(0,0,0,0.26);
    }}
    .stat-item::before {{
      content:"";
      position:absolute;
      left:0;
      right:0;
      top:0;
      height:3px;
      opacity:0.95;
    }}
    .stat-item .label {{ color: color-mix(in srgb, var(--muted) 82%, #fff 18%); font-size: 8.5px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .stat-item .value {{ font-size: 14px; font-weight: 740; margin-top: 2px; }}
    .tone-good {{ border-color: color-mix(in srgb, var(--good) 52%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--good) 16%, transparent), 0 10px 20px rgba(0,0,0,0.24); }}
    .tone-good::before {{ background: linear-gradient(90deg, color-mix(in srgb, var(--good) 76%, #fff 24%), color-mix(in srgb, var(--good) 45%, transparent)); }}
    .tone-mid {{ border-color: color-mix(in srgb, var(--mid) 54%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mid) 16%, transparent), 0 10px 20px rgba(0,0,0,0.24); }}
    .tone-mid::before {{ background: linear-gradient(90deg, color-mix(in srgb, var(--mid) 74%, #fff 26%), color-mix(in srgb, var(--mid) 45%, transparent)); }}
    .tone-poor {{ border-color: color-mix(in srgb, var(--poor) 56%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--poor) 16%, transparent), 0 10px 20px rgba(0,0,0,0.24); }}
    .tone-poor::before {{ background: linear-gradient(90deg, color-mix(in srgb, var(--poor) 78%, #fff 22%), color-mix(in srgb, var(--poor) 45%, transparent)); }}
    .tone-bad {{ border-color: color-mix(in srgb, var(--bad) 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bad) 18%, transparent), 0 10px 20px rgba(0,0,0,0.24); }}
    .tone-bad::before {{ background: linear-gradient(90deg, color-mix(in srgb, var(--bad) 78%, #fff 22%), color-mix(in srgb, var(--bad) 45%, transparent)); }}

    .grev-tier-strip {{
      border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--border));
      border-radius: 10px;
      padding: 7px 8px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 86%, #0a1220 14%), color-mix(in srgb, var(--surface) 95%, #05080f 5%));
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 10%, transparent);
    }}
    .grev-tier-label {{ font-size: 8px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 5px; }}
    .grev-tier-row {{ display:flex; align-items:stretch; gap: 5px; }}
    .grev-tier-box {{
      width: 40px;
      min-height: 34px;
      border-radius: 6px;
      border: 1px solid color-mix(in srgb, var(--border) 86%, #fff 14%);
      display:flex;
      flex-direction: column;
      align-items:center;
      justify-content:center;
      font-size: 9px;
      color: color-mix(in srgb, var(--muted) 84%, #fff 16%);
      background: color-mix(in srgb, var(--surface) 89%, #fff 11%);
      gap: 1px;
      padding: 2px 1px;
    }}
    .tier-name {{ font-size: 8px; line-height: 1; font-weight: 700; }}
    .tier-score {{ font-size: 11.5px; line-height: 1.05; font-weight: 780; color: var(--text); }}
    .grev-tier-S {{ border-color: color-mix(in srgb, #f5c542 65%, var(--border)); background: color-mix(in srgb, #f5c542 18%, var(--surface)); }}
    .grev-tier-A {{ border-color: color-mix(in srgb, #9c6bff 65%, var(--border)); background: color-mix(in srgb, #9c6bff 18%, var(--surface)); }}
    .grev-tier-B {{ border-color: color-mix(in srgb, #4f8dff 65%, var(--border)); background: color-mix(in srgb, #4f8dff 18%, var(--surface)); }}
    .grev-tier-C {{ border-color: color-mix(in srgb, #3db97a 65%, var(--border)); background: color-mix(in srgb, #3db97a 18%, var(--surface)); }}
    .player-card-bottom {{ margin-top: auto; }}
    .player-card-note {{
      font-size: 10.5px;
      color: color-mix(in srgb, var(--text) 90%, #fff 10%);
      margin: 0;
      min-height: 76px;
      max-height: 76px;
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 6;
      -webkit-box-orient: vertical;
      line-clamp: 6;
    }}
    .roster-section {{
      border-radius: var(--radius-l);
      border: 1px solid var(--border);
      padding: 10px 10px 2px 10px;
      margin-bottom: 14px;
    }}
    .roster-section-main {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 94%, #fff 6%), color-mix(in srgb, var(--surface) 99%, #000 1%));
      border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
    }}
    .roster-section-academy {{
      margin-top: 18px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 82%, #111a2a 18%), color-mix(in srgb, var(--surface) 92%, #0a1220 8%));
      border-color: color-mix(in srgb, var(--poor) 55%, var(--border));
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--poor) 22%, transparent);
    }}
    .roster-section-transferred {{
      margin-top: 14px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 80%, #070b12 20%), color-mix(in srgb, var(--surface) 90%, #03060a 10%));
      border-color: color-mix(in srgb, var(--bad) 44%, var(--border));
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bad) 14%, transparent);
    }}
    .player-card-subdued {{ opacity: 0.88; filter: saturate(0.86); }}
    .achievement-tile.tier-S {{ border-color: color-mix(in srgb, #f5c542 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #f5c542 22%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}
    .achievement-tile.tier-A {{ border-color: color-mix(in srgb, #9c6bff 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #9c6bff 22%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}
    .achievement-tile.tier-B {{ border-color: color-mix(in srgb, #4f8dff 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #4f8dff 20%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}
    .achievement-tile.tier-C {{ border-color: color-mix(in srgb, #3db97a 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #3db97a 20%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}

    .toolbar-shell {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 92%, #fff 8%), var(--surface));
      border: 1px solid var(--border);
      border-radius: var(--radius-m);
      padding: 10px 12px 4px 12px;
      margin-bottom: 12px;
    }}

    .subtle-grid {{ display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px; }}

    .muted {{ color: var(--muted); font-size:12px; }}
    .stat-good {{ color:var(--good); }} .stat-mid {{ color:var(--mid); }}
    .stat-poor {{ color:var(--poor); }} .stat-bad {{ color:var(--bad); }}

    div[data-testid="stHorizontalBlock"] > div {{ align-self: stretch; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def tier_badge(tier: str) -> str:
    color = TIER_COLORS.get(str(tier).strip().upper(), "#8892b0")
    return f"<span class='chip' style='background:{color}26;border-color:{color};'>Tier {tier}</span>"


def achievement_tier_badge(tier: str) -> str:
    palette = {
        "S": "#f5c542",
        "A": "#9c6bff",
        "B": "#4f8dff",
        "C": "#3db97a",
    }
    key = str(tier or "-").strip().upper()
    color = palette.get(key, "#8892b0")
    return f"<span class='achievement-tier' style='color:{color};background:{color}1f;'>{key}</span>"
