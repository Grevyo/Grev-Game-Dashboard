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

    .player-card {{ min-height: 352px; height: 100%; display:flex; flex-direction:column; gap: 10px; }}
    .player-head {{ display:flex; align-items:flex-start; gap:12px; }}
    .player-head-left {{ flex:0 0 98px; display:flex; flex-direction:column; gap:6px; }}
    .player-head-meta {{ flex:1; min-width:0; display:flex; flex-direction:column; gap:6px; }}
    .player-avatar-frame {{
      width: 98px; height: 114px; border-radius: 12px; overflow:hidden;
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
    .player-name {{ font-size: 0.95rem; font-weight: 720; margin: 0; line-height:1.25; }}
    .identity-line {{ color: var(--muted); font-size: 11px; margin: 0; line-height: 1.3; }}
    .fame-line {{ display:flex; align-items:center; gap:6px; margin-top:1px; }}
    .fame-label {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .fame-stars {{ font-size: 13px; letter-spacing: 0.08em; color: color-mix(in srgb, var(--mid) 70%, #fff 30%); }}
    .fame-value {{ color: var(--muted); font-size: 10px; }}
    .player-meta-row {{ display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }}
    .player-desc {{
      font-size: 11px; color: color-mix(in srgb, var(--text) 88%, #fff 12%); margin: 0;
      min-height: 42px; max-height: 42px; overflow: hidden;
      display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
      line-clamp: 3;
    }}
    .achievement-strip {{
      display:grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 4px;
      min-height: 42px;
      align-items:stretch;
    }}
    .achievement-strip-featured {{ margin-top: 0; }}
    .achievement-tile {{
      position: relative;
      min-height: 42px;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      background: color-mix(in srgb, var(--surface) 88%, #fff 12%);
      box-shadow: 0 6px 12px rgba(0,0,0,0.2);
    }}
    .achievement-tile-thumb {{
      width: 100%;
      height: 100%;
      min-height: 42px;
      object-fit: cover;
      transform: scale(1.02);
      filter: saturate(1.05);
    }}
    .achievement-tile-overlay {{
      position: absolute;
      left: 0; right: 0; bottom: 0;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      padding: 3px;
      background: linear-gradient(180deg, transparent 0%, rgba(8,12,20,0.58) 100%);
    }}
    .achievement-tier {{
      padding: 1px 4px; border-radius: 999px; font-size: 7px; font-weight: 750; letter-spacing: 0.03em;
      border: 1px solid currentColor; align-self: flex-start;
    }}
    .stats-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-top: 2px; }}
    .stat-item {{
      background: color-mix(in srgb, var(--surface) 90%, #fff 10%);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 6px 8px 7px 8px;
      position: relative;
      overflow: hidden;
    }}
    .stat-item .label {{ color: color-mix(in srgb, var(--muted) 90%, #fff 10%); font-size: 8px; text-transform: uppercase; letter-spacing: 0.07em; }}
    .stat-item .value {{ font-size: 13px; font-weight: 700; margin-top: 1px; }}
    .tone-good {{ background: linear-gradient(180deg, color-mix(in srgb, var(--good) 14%, var(--surface)) 0 5px, color-mix(in srgb, var(--surface) 92%, #fff 8%) 5px 100%); border-color: color-mix(in srgb, var(--good) 60%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--good) 20%, transparent), 0 0 10px color-mix(in srgb, var(--good) 16%, transparent); }}
    .tone-mid {{ background: linear-gradient(180deg, color-mix(in srgb, var(--mid) 15%, var(--surface)) 0 5px, color-mix(in srgb, var(--surface) 92%, #fff 8%) 5px 100%); border-color: color-mix(in srgb, var(--mid) 60%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mid) 18%, transparent), 0 0 10px color-mix(in srgb, var(--mid) 15%, transparent); }}
    .tone-poor {{ background: linear-gradient(180deg, color-mix(in srgb, var(--poor) 16%, var(--surface)) 0 5px, color-mix(in srgb, var(--surface) 92%, #fff 8%) 5px 100%); border-color: color-mix(in srgb, var(--poor) 60%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--poor) 18%, transparent), 0 0 10px color-mix(in srgb, var(--poor) 16%, transparent); }}
    .tone-bad {{ background: linear-gradient(180deg, color-mix(in srgb, var(--bad) 15%, var(--surface)) 0 5px, color-mix(in srgb, var(--surface) 92%, #fff 8%) 5px 100%); border-color: color-mix(in srgb, var(--bad) 64%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bad) 20%, transparent), 0 0 10px color-mix(in srgb, var(--bad) 15%, transparent); }}
    .achievement-more {{ font-size: 8px; padding: 1px 4px; margin: 0; width: 100%; justify-content: center; }}
    .achievement-tile.tier-S {{ border-color: color-mix(in srgb, #f5c542 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #f5c542 22%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}
    .achievement-tile.tier-A {{ border-color: color-mix(in srgb, #9c6bff 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #9c6bff 22%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}
    .achievement-tile.tier-B {{ border-color: color-mix(in srgb, #4f8dff 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #4f8dff 20%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}
    .achievement-tile.tier-C {{ border-color: color-mix(in srgb, #3db97a 58%, var(--border)); box-shadow: inset 0 0 0 1px color-mix(in srgb, #3db97a 20%, transparent), 0 8px 18px rgba(0,0,0,0.24); }}
    @media (max-width: 1280px) {{
      .achievement-strip {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    }}
    @media (max-width: 980px) {{
      .achievement-strip {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    }}

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
