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
    .block-container {{ padding-top: 1.55rem; padding-bottom: 1.4rem; max-width: 98%; }}

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
    .player-viewer-hero {{
      border-color: color-mix(in srgb, var(--accent) 42%, var(--border));
      box-shadow: 0 14px 28px rgba(0,0,0,0.2), inset 0 0 0 1px color-mix(in srgb, var(--accent) 12%, transparent);
    }}
    .player-viewer-head-main {{
      flex: 1;
      min-width: 320px;
      display: flex;
      align-items: flex-start;
      gap: 16px;
      padding: 2px;
    }}
    .player-viewer-hero-grid {{
      display:grid;
      grid-template-columns: minmax(0, 1.9fr) minmax(260px, 1fr);
      gap: 14px;
      align-items: stretch;
    }}
    .player-viewer-head-body {{ min-width: 0; }}
    .player-viewer-chip-row {{
      display:flex;
      flex-wrap: wrap;
      gap: 2px 4px;
      margin-top: 2px;
    }}
    .player-viewer-form-note {{ margin-top: 6px; }}
    .player-viewer-gauge-panel {{
      border: 1px solid color-mix(in srgb, var(--accent) 26%, var(--border));
      border-radius: 12px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 84%, #fff 16%), color-mix(in srgb, var(--surface) 94%, #000 6%));
      padding: 10px 12px;
      min-height: 220px;
      display:flex;
      flex-direction: column;
      gap: 10px;
    }}
    .player-viewer-gauge-header {{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap: 8px;
    }}
    .player-viewer-mini-title {{
      font-size: 0.92rem;
      margin: 0;
    }}
    .player-viewer-gauge-wrap {{
      display:flex;
      justify-content:center;
      align-items:center;
      flex: 1;
    }}
    .grev-gauge {{
      --gauge-pct: 50%;
      width: 170px;
      height: 170px;
      border-radius: 50%;
      background: conic-gradient(from -90deg, var(--good) 0 var(--gauge-pct), color-mix(in srgb, var(--border) 70%, #101827 30%) var(--gauge-pct) 100%);
      display:grid;
      place-items:center;
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 16%, transparent), 0 10px 18px rgba(0,0,0,0.26);
    }}
    .grev-gauge-inner {{
      width: 124px;
      height: 124px;
      border-radius: 50%;
      background: radial-gradient(circle at 50% 20%, color-mix(in srgb, var(--surface) 82%, #fff 18%), color-mix(in srgb, var(--surface) 96%, #000 4%));
      border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
      display:flex;
      flex-direction:column;
      justify-content:center;
      align-items:center;
      gap: 2px;
    }}
    .player-viewer-top-metrics {{
      margin-top: 12px;
      display:grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
    }}

    .metric-title {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .metric-value {{ font-size: 25px; line-height: 1.15; font-weight: 760; margin-top: 3px; }}

    /* Global page navigation: premium horizontal control (pills / segmented / radio fallback). */
    div[data-testid="stPills"],
    div[data-testid="stSegmentedControl"],
    div[data-testid="stRadio"][role="radiogroup"] {{
      display:flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 8px;
      margin-bottom: 12px;
      background: color-mix(in srgb, var(--surface) 94%, #fff 6%);
      border: 1px solid var(--border);
      border-radius: 999px;
      box-shadow: 0 8px 18px rgba(0,0,0,0.18);
    }}
    div[data-testid="stPills"] label[data-baseweb="checkbox"],
    div[data-testid="stSegmentedControl"] label[data-baseweb="radio"],
    div[data-testid="stRadio"] label[data-baseweb="radio"] {{
      margin: 0;
      min-height: 0;
    }}
    div[data-testid="stPills"] label[data-baseweb="checkbox"] > div:first-child,
    div[data-testid="stSegmentedControl"] label[data-baseweb="radio"] > div:first-child,
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {{
      display: none;
    }}
    div[data-testid="stPills"] label[data-baseweb="checkbox"] > div:last-child,
    div[data-testid="stSegmentedControl"] label[data-baseweb="radio"] > div:last-child,
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:last-child {{
      display:inline-flex;
      align-items:center;
      justify-content:center;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid color-mix(in srgb, var(--border) 82%, #fff 18%);
      background: color-mix(in srgb, var(--surface) 82%, #fff 18%);
      color: var(--muted);
      font-weight: 620;
      font-size: 0.84rem;
      letter-spacing: 0.01em;
      transition: all .18s ease;
      cursor: pointer;
    }}
    div[data-testid="stPills"] label[data-baseweb="checkbox"]:hover > div:last-child,
    div[data-testid="stSegmentedControl"] label[data-baseweb="radio"]:hover > div:last-child,
    div[data-testid="stRadio"] label[data-baseweb="radio"]:hover > div:last-child {{
      color: var(--text);
      border-color: color-mix(in srgb, var(--accent) 46%, var(--border));
      background: color-mix(in srgb, var(--surface) 74%, var(--accent) 26%);
      transform: translateY(-1px);
    }}
    div[data-testid="stPills"] input[type="checkbox"]:checked + div,
    div[data-testid="stSegmentedControl"] input[type="radio"]:checked + div,
    div[data-testid="stRadio"] input[type="radio"]:checked + div {{
      color: #f5f8ff;
      border-color: color-mix(in srgb, var(--accent) 75%, #ffffff 25%);
      background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 70%, #1d2b45 30%), color-mix(in srgb, var(--accent) 58%, #101829 42%));
      box-shadow: 0 6px 14px rgba(0,0,0,0.28), inset 0 0 0 1px color-mix(in srgb, #ffffff 18%, transparent);
      font-weight: 700;
    }}

    @media (max-width: 768px) {{
      .block-container {{ padding-top: 1.2rem; }}
      div[data-testid="stPills"],
      div[data-testid="stSegmentedControl"],
      div[data-testid="stRadio"][role="radiogroup"] {{
        border-radius: 16px;
        padding: 8px;
      }}
      div[data-testid="stPills"] label[data-baseweb="checkbox"] > div:last-child,
      div[data-testid="stSegmentedControl"] label[data-baseweb="radio"] > div:last-child,
      div[data-testid="stRadio"] label[data-baseweb="radio"] > div:last-child {{
        padding: 8px 12px;
        font-size: 0.8rem;
      }}
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
      height: auto;
      display:flex;
      flex-direction:column;
      gap: 8px;
      overflow: visible;
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
    .last-match-block {{
      margin-top: 2px;
      padding: 5px 7px;
      border-radius: 8px;
      border: 1px solid color-mix(in srgb, var(--mid) 26%, var(--border));
      border-left: 3px solid color-mix(in srgb, var(--mid) 62%, #b4ccff 38%);
      background: linear-gradient(180deg, color-mix(in srgb, var(--mid) 12%, var(--surface)), color-mix(in srgb, var(--surface) 94%, #fff 6%));
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .last-match-title {{
      color: var(--muted);
      font-size: 9px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      line-height: 1.1;
    }}
    .last-match-line {{
      font-size: 10px;
      line-height: 1.25;
      color: var(--text);
      margin: 0;
    }}
    .last-match-line strong {{ font-weight: 700; }}
    .last-match-result {{
      padding: 0 5px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-size: 9px;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }}
    .last-match-result-win {{
      color: color-mix(in srgb, var(--good) 86%, #f4fff8 14%);
      background: color-mix(in srgb, var(--good) 22%, transparent);
      border-color: color-mix(in srgb, var(--good) 48%, transparent);
    }}
    .last-match-result-loss {{
      color: color-mix(in srgb, var(--bad) 86%, #fff4f4 14%);
      background: color-mix(in srgb, var(--bad) 22%, transparent);
      border-color: color-mix(in srgb, var(--bad) 48%, transparent);
    }}
    .last-match-result-neutral {{
      color: color-mix(in srgb, var(--mid) 82%, #f4f8ff 18%);
      background: color-mix(in srgb, var(--mid) 20%, transparent);
      border-color: color-mix(in srgb, var(--mid) 42%, transparent);
    }}
    .last-match-metric {{
      color: color-mix(in srgb, var(--text) 88%, #ffffff 12%);
      font-weight: 760;
    }}

    .best-match-block {{
      margin-top: 2px;
      padding: 5px 7px;
      border-radius: 8px;
      border: 1px solid color-mix(in srgb, var(--good) 24%, var(--border));
      border-left: 3px solid color-mix(in srgb, var(--good) 60%, #d9ffe9 40%);
      background: linear-gradient(180deg, color-mix(in srgb, var(--good) 10%, var(--surface)), color-mix(in srgb, var(--surface) 94%, #fff 6%));
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .achievement-strip {{
      display:flex;
      flex-direction: row;
      flex-wrap: wrap;
      gap: 7px;
      min-height: 76px;
      max-height: none;
      align-items: stretch;
      overflow: visible;
    }}
    .achievement-strip-featured {{ margin-top: 0; }}
    .achievement-strip-viewer {{
      gap: 10px;
      min-height: 86px;
      padding: 10px 12px;
      border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
      border-radius: 12px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 92%, #fff 8%), color-mix(in srgb, var(--surface) 98%, #000 2%));
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 10%, transparent);
    }}
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
      height: 72px;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: visible;
      background: color-mix(in srgb, var(--surface) 88%, #fff 12%);
      box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }}
    .achievement-tile-lg {{
      flex-basis: 78px;
      width: 78px;
      height: 82px;
      border-radius: 10px;
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
    .achievement-season-top {{
      position: absolute;
      top: 4px;
      left: 50%;
      transform: translateX(-50%);
      max-width: calc(100% - 8px);
      min-width: 56px;
      padding: 2px 7px;
      border-radius: 999px;
      border: 1px solid color-mix(in srgb, #ffffff 24%, transparent);
      background: color-mix(in srgb, rgba(7,12,24,0.9) 86%, #9fb8ff 14%);
      color: #f5f8ff;
      font-size: 8px;
      line-height: 1;
      font-weight: 700;
      letter-spacing: 0.02em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      text-align: center;
      text-shadow: 0 1px 2px rgba(0,0,0,0.55);
      z-index: 2;
    }}
    .achievement-tier {{
      padding: 0 4px; border-radius: 999px; font-size: 8px; font-weight: 750; letter-spacing: 0.03em;
      border: 1px solid currentColor; align-self: flex-start;
    }}
    .achievement-event-title {{
      color: #eef2ff;
      font-size: 7.5px;
      line-height: 1.15;
      font-weight: 760;
      text-shadow: 0 1px 3px rgba(0,0,0,0.78);
      display: block;
      word-break: break-word;
      overflow-wrap: anywhere;
      text-wrap: wrap;
    }}
    .achievement-tile-lg .achievement-season-top {{
      min-width: 64px;
      font-size: 9px;
    }}
    .achievement-tile-lg .achievement-tier {{
      font-size: 9px;
      padding: 0 5px;
    }}
    .achievement-tile-lg .achievement-event-title {{
      font-size: 8.5px;
      line-height: 1.2;
    }}
    .achievement-overflow {{
      flex: 0 0 70px;
      width: 70px;
      height: 74px;
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
    .grev-tier-row {{ display:flex; align-items:stretch; gap: 5px; width: 100%; }}
    .grev-tier-box {{
      flex: 1 1 0;
      min-width: 0;
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
    .lower-analytics-shell {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .lower-card {{
      background: linear-gradient(180deg, color-mix(in srgb, var(--surface) 93%, #fff 7%), color-mix(in srgb, var(--surface) 98%, #000 2%));
      border: 1px solid color-mix(in srgb, var(--accent) 24%, var(--border));
      border-radius: 12px;
      padding: 10px 12px;
      box-shadow: 0 10px 22px rgba(0,0,0,0.16);
      height: 100%;
    }}
    .lower-breakdown-title {{
      margin: 0 0 4px 0;
      font-size: 0.92rem;
      font-weight: 740;
      letter-spacing: 0.02em;
      color: var(--text);
    }}
    .lower-breakdown-subtitle {{
      font-size: 11px;
      margin-bottom: 8px;
    }}
    .breakdown-table-wrap {{
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      background: color-mix(in srgb, var(--surface) 95%, #fff 5%);
    }}
    .breakdown-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 12px;
    }}
    .breakdown-table th {{
      text-align: left;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: color-mix(in srgb, var(--text) 86%, #fff 14%);
      padding: 9px 10px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 22%, var(--surface)), color-mix(in srgb, var(--surface) 97%, #000 3%));
      border-bottom: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
    }}
    .breakdown-table th:not(:first-child),
    .breakdown-table td.breakdown-num {{
      text-align: right;
    }}
    .breakdown-table td {{
      padding: 8px 10px;
      border-bottom: 1px solid color-mix(in srgb, var(--border) 66%, transparent);
      color: var(--text);
    }}
    .breakdown-table tr:last-child td {{
      border-bottom: 0;
    }}
    .breakdown-row.even td {{
      background: color-mix(in srgb, var(--surface) 96%, #fff 4%);
    }}
    .breakdown-row.odd td {{
      background: color-mix(in srgb, var(--surface) 90%, #fff 10%);
    }}
    .breakdown-key {{
      font-weight: 640;
      letter-spacing: 0.01em;
    }}

    .subtle-grid {{ display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px; }}

    @media (max-width: 1100px) {{
      .player-viewer-hero-grid {{
        grid-template-columns: 1fr;
      }}
      .player-viewer-top-metrics {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 760px) {{
      .player-viewer-head-main {{
        min-width: 0;
        flex-direction: column;
      }}
      .player-viewer-top-metrics {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}


    .match-list-wrap {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .match-list-item {{
      border: 1px solid var(--border);
      border-left: 3px solid color-mix(in srgb, var(--mid) 58%, var(--border));
      border-radius: 10px;
      padding: 8px 10px;
      background: color-mix(in srgb, var(--surface) 92%, #fff 8%);
    }}
    .match-list-item.best {{ border-left-color: color-mix(in srgb, var(--good) 62%, var(--border)); }}
    .match-list-head {{ display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; font-size:11px; }}
    .match-list-line {{ font-size:11px; color: var(--muted); margin-top: 3px; }}
    .match-outcome {{
      border-radius: 999px;
      padding: 1px 7px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      border: 1px solid transparent;
    }}
    .match-outcome.win {{ color: var(--good); border-color: color-mix(in srgb, var(--good) 44%, transparent); background: color-mix(in srgb, var(--good) 18%, transparent); }}
    .match-outcome.loss {{ color: var(--bad); border-color: color-mix(in srgb, var(--bad) 44%, transparent); background: color-mix(in srgb, var(--bad) 18%, transparent); }}
    .match-outcome.neutral {{ color: var(--mid); border-color: color-mix(in srgb, var(--mid) 44%, transparent); background: color-mix(in srgb, var(--mid) 18%, transparent); }}
    .match-grev {{ font-weight: 780; color: color-mix(in srgb, var(--text) 90%, #fff 10%); }}

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
