import streamlit as st

from app.config import TIER_COLORS, THEMES


def inject_styles(theme_name: str = "Dark"):
    theme = THEMES.get(theme_name, THEMES["Dark"])
    css = f"""
    <style>
    :root {{
      --bg: {theme['bg']};
      --surface: {theme['surface']};
      --surface-soft: {theme['surface']};
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
      --radius-s: 10px;
      --radius-m: 14px;
      --radius-l: 18px;
    }}

    .stApp {{ background: var(--bg); color: var(--text); }}
    .block-container {{ padding-top: 1.1rem; padding-bottom: 1.5rem; max-width: 96%; }}

    .section-title {{ margin: var(--space-5) 0 var(--space-2) 0; font-size: 1.08rem; font-weight: 700; letter-spacing: 0.02em; }}

    .chip {{
      display:inline-flex; align-items:center; gap:6px;
      padding:3px 10px; border-radius:999px; border:1px solid var(--border);
      font-size:12px; margin-right:6px; margin-bottom:6px; color: var(--text);
      background: color-mix(in srgb, var(--surface) 75%, var(--accent) 25%);
    }}

    .chip-good {{ background: color-mix(in srgb, var(--good) 20%, transparent); border-color: color-mix(in srgb, var(--good) 45%, var(--border)); }}
    .chip-mid {{ background: color-mix(in srgb, var(--mid) 22%, transparent); border-color: color-mix(in srgb, var(--mid) 45%, var(--border)); }}
    .chip-poor {{ background: color-mix(in srgb, var(--poor) 20%, transparent); border-color: color-mix(in srgb, var(--poor) 45%, var(--border)); }}
    .chip-bad {{ background: color-mix(in srgb, var(--bad) 18%, transparent); border-color: color-mix(in srgb, var(--bad) 50%, var(--border)); }}

    .panel {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 90%, #fff 10%), var(--surface));
      border: 1px solid var(--border);
      border-radius: var(--radius-m);
      padding: var(--space-4);
      margin-bottom: var(--space-3);
      box-shadow: 0 10px 24px rgba(0,0,0,0.18);
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
      background: radial-gradient(circle at 0% 0%, color-mix(in srgb, var(--accent) 18%, transparent), transparent 40%),
                  linear-gradient(180deg, color-mix(in srgb, var(--surface) 88%, #fff 12%), var(--surface));
      margin-bottom: var(--space-4);
    }}

    .metric-title {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .metric-value {{ font-size: 28px; line-height: 1.2; font-weight: 750; margin-top: 2px; }}

    .player-card {{ height: 100%; min-height: 260px; }}
    .player-name {{ font-size: 1.05rem; font-weight: 700; margin-bottom: 4px; }}
    .identity-line {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; }}
    .player-desc {{ font-size: 13px; margin-bottom: 10px; }}
    .stats-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }}
    .stat-item {{
      background: color-mix(in srgb, var(--surface) 82%, #fff 18%);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 7px 8px;
    }}
    .stat-item .label {{ color: var(--muted); font-size: 11px; }}
    .stat-item .value {{ font-size: 14px; font-weight: 650; }}

    .muted {{ color: var(--muted); font-size:12px; }}
    .stat-good {{ color:var(--good); }} .stat-mid {{ color:var(--mid); }}
    .stat-poor {{ color:var(--poor); }} .stat-bad {{ color:var(--bad); }}

    section[data-testid="stSidebar"] .stMarkdown {{ margin-bottom: 6px; }}
    .sidebar-card {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 90%, #fff 10%), var(--surface));
      border:1px solid var(--border);
      border-radius:12px;
      padding:10px 12px 6px 12px;
      margin: 8px 0;
    }}
    .sidebar-head {{
      color: var(--text);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stMultiSelect label,
    section[data-testid="stSidebar"] .stRadio label {{
      font-size: 0.78rem !important;
      color: var(--muted) !important;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    section[data-testid="stSidebar"] .stRadio > div {{ gap: 4px; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def tier_badge(tier: str) -> str:
    color = TIER_COLORS.get(str(tier).strip().upper(), "#8892b0")
    return f"<span class='chip' style='background:{color}26;border-color:{color};'>{tier}</span>"
