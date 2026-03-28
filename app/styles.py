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

    .player-card {{ min-height: 390px; display:flex; flex-direction:column; gap: 10px; }}
    .player-head {{ display:flex; align-items:flex-start; gap:12px; }}
    .player-head-left {{ flex:0 0 auto; }}
    .player-head-meta {{ flex:1; min-width:0; }}
    .player-avatar-frame {{
      width: 82px; height: 104px; border-radius: 14px; overflow:hidden;
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
      width: 32px; height: 32px; object-fit: contain;
      border-radius: 8px; padding: 3px;
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--surface) 70%, #fff 30%);
    }}
    .hero-logo {{ width: 72px; height: 72px; object-fit: contain; border-radius: 12px; border: 1px solid var(--border); padding: 6px; background: color-mix(in srgb, var(--surface) 72%, #fff 28%); }}
    .hero-player-photo-frame {{
      width: 128px; height: 156px; border-radius: 16px; overflow:hidden;
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

    .player-name {{ font-size: 1.03rem; font-weight: 720; margin: 0; }}
    .identity-line {{ color: var(--muted); font-size: 12px; margin: 0; }}
    .player-desc {{ font-size: 12px; color: color-mix(in srgb, var(--text) 88%, #fff 12%); margin: 0; min-height: 30px; }}
    .achievement-strip {{ display:flex; flex-wrap:wrap; gap: 6px; min-height: 36px; align-items:stretch; }}
    .achievement-chip {{
      display:flex; gap:6px; align-items:center;
      background: color-mix(in srgb, var(--surface) 84%, #fff 16%);
      border: 1px solid var(--border); border-radius: 10px; padding: 6px;
      min-width: 0;
    }}
    .achievement-chip-thumb {{ width: 26px; height: 26px; object-fit: contain; border-radius: 8px; }}
    .achievement-chip-name {{ font-size: 11px; font-weight: 680; line-height: 1.1; }}
    .achievement-chip-meta {{ font-size: 10px; color: var(--muted); }}
    .stats-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    .stat-item {{
      background: color-mix(in srgb, var(--surface) 82%, #fff 18%);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px;
    }}
    .stat-item .label {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .stat-item .value {{ font-size: 14px; font-weight: 680; margin-top: 2px; }}

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
