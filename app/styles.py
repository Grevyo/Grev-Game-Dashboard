import streamlit as st

from app.config import TIER_COLORS, THEMES


def inject_styles(theme_name: str = "Dark"):
    theme = THEMES.get(theme_name, THEMES["Dark"])
    accent = theme.get("accent", "#9FE870")
    css = f"""
    <style>
    :root {{
      --bg-0:#06080b;
      --bg-1:#0b1016;
      --bg-2:#111821;
      --bg-3:#151f2b;
      --panel:#0d141d;
      --panel-2:#121c28;
      --line:#273443;
      --line-soft:#1f2935;
      --text:#f3f7fc;
      --muted:#91a1b4;
      --lime:#9FE870;
      --ember:#ff9f43;
      --crimson:#ff4d5e;
      --gold:#d3a85c;
      --steel:#9fb4ca;
      --accent:{accent};
      --good:{theme.get('good', '#9FE870')};
      --mid:{theme.get('mid', '#d3a85c')};
      --poor:{theme.get('poor', '#ff9f43')};
      --bad:{theme.get('bad', '#ff4d5e')};
      --radius-xs:4px;
      --radius-s:6px;
      --radius-m:9px;
      --radius-l:12px;
    }}

    .stApp {{
      background:
        radial-gradient(1400px 420px at 50% -80px, rgba(159,232,112,.08), transparent 58%),
        radial-gradient(900px 280px at 100% 0, rgba(211,168,92,.08), transparent 58%),
        linear-gradient(180deg, var(--bg-0) 0%, var(--bg-1) 34%, #070b10 100%);
      color: var(--text);
    }}
    .block-container {{
      max-width: min(98vw, 1820px);
      padding: .85rem .8rem 1.4rem;
    }}

    h1,h2,h3,h4 {{ color:var(--text); letter-spacing:.01em; font-weight:760; }}
    .section-title {{
      margin:0 0 .35rem 0;
      font-size:.74rem;
      text-transform:uppercase;
      letter-spacing:.15em;
      color:#8fa3ba;
      font-weight:700;
    }}
    .section-subtitle {{ font-size:.82rem; color:var(--muted); margin:0 0 .55rem; }}
    .muted {{ color:var(--muted); font-size:.76rem; line-height:1.35; }}

    .hero-band {{
      position:relative;
      overflow:hidden;
      border:1px solid #304153;
      border-radius: var(--radius-l);
      padding: .8rem .95rem;
      background:
        linear-gradient(92deg, rgba(12,20,30,.97) 0%, rgba(10,16,24,.96) 44%, rgba(15,24,34,.98) 100%);
      box-shadow: 0 24px 48px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06);
    }}
    .app-topbar {{ padding: .7rem .9rem; }}
    .app-topbar-row {{ display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
    .app-topbar-brand {{ display:flex; align-items:center; gap:10px; min-width: 0; }}
    .app-topbar-copy {{ min-width: 0; }}
    .app-topbar-kicker {{ margin:0 0 .1rem 0 !important; }}
    .app-topbar-title {{
      font-size:1.04rem;
      line-height:1.12;
      font-weight:800;
      letter-spacing:.01em;
      color:#f4f9ff;
    }}
    .app-topbar-subtitle {{ margin:.2rem 0 0 0; font-size:.74rem; max-width:780px; line-height:1.35; }}
    .app-topbar-chips {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; }}
    .hero-band::before {{
      content:""; position:absolute; inset:0; pointer-events:none;
      background: linear-gradient(90deg, transparent 0%, rgba(159,232,112,.07) 45%, transparent 100%);
    }}

    .panel, .table-frame, .analytics-frame, .toolbar-shell, .context-ribbon,
    .roster-section, .breakdown-table-wrap, .map-performance-table-wrap,
    .map-breakdown-card, .player-viewer-gauge-panel, .achievement-strip-viewer {{
      border: 1px solid var(--line);
      border-radius: var(--radius-m);
      background: linear-gradient(180deg, var(--panel-2) 0%, var(--panel) 100%);
      box-shadow: 0 14px 26px rgba(0,0,0,.32), inset 0 1px 0 rgba(255,255,255,.04);
    }}
    .panel {{ padding:.85rem; }}
    .panel-tight {{ padding:.65rem; }}

    .accent-good {{ border-top:2px solid var(--lime); }}
    .accent-mid {{ border-top:2px solid var(--gold); }}
    .accent-poor {{ border-top:2px solid var(--ember); }}
    .accent-bad {{ border-top:2px solid var(--crimson); }}

    .metric-title, .label {{ font-size:.62rem; letter-spacing:.16em; text-transform:uppercase; color:#8fa3ba; font-weight:700; }}
    .metric-value {{ font-size:1.48rem; font-weight:800; line-height:1.08; color:#f7fbff; }}
    .stat-good {{ color:var(--lime); }} .stat-mid {{ color:var(--gold); }}
    .stat-poor {{ color:var(--ember); }} .stat-bad {{ color:var(--crimson); }}

    .stat-widget, .stat-item {{
      border:1px solid var(--line-soft);
      border-radius: var(--radius-s);
      background: linear-gradient(180deg, #131d29, #0f1823);
      padding:.48rem .58rem;
    }}
    .subtle-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.45rem; }}
    .stats-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.5rem; }}

    .chip {{
      display:inline-flex; align-items:center;
      border:1px solid #3a4b5d; border-radius:3px;
      background:#101925; color:#d8e3ef;
      font-size:.58rem; text-transform:uppercase; letter-spacing:.12em;
      padding:3px 8px;
    }}

    .hero-logo {{
      width:56px;
      height:56px;
      object-fit:contain;
      filter: drop-shadow(0 8px 12px rgba(0,0,0,.28));
    }}
    .overview-hero .hero-logo {{ width:46px; height:46px; }}
    .player-viewer-hero .hero-logo {{ width:42px; height:42px; }}
    .app-topbar .hero-logo {{ width:48px; height:48px; }}
    .chip-good {{ border-color:color-mix(in srgb, var(--lime) 55%, #31404f); color:var(--lime); }}
    .chip-mid {{ border-color:color-mix(in srgb, var(--gold) 55%, #31404f); color:var(--gold); }}
    .chip-poor {{ border-color:color-mix(in srgb, var(--ember) 55%, #31404f); color:var(--ember); }}
    .chip-bad {{ border-color:color-mix(in srgb, var(--crimson) 55%, #31404f); color:var(--crimson); }}

    div[data-testid="stPills"], div[data-testid="stSegmentedControl"], div[data-testid="stRadio"][role="radiogroup"] {{
      border:1px solid var(--line); border-radius:7px; padding:5px;
      background:#0d141e; box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
      margin-bottom: 10px;
    }}
    div[data-testid="stSegmentedControl"] > div,
    div[data-testid="stPills"] > div,
    div[data-testid="stRadio"][role="radiogroup"] > div {{
      display:flex;
      flex-wrap:nowrap;
      gap:6px;
    }}
    div[data-testid="stPills"] label[data-baseweb="checkbox"] > div:first-child,
    div[data-testid="stSegmentedControl"] label[data-baseweb="radio"] > div:first-child,
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {{ display:none; }}
    div[data-testid="stPills"] label[data-baseweb="checkbox"] > div:last-child,
    div[data-testid="stSegmentedControl"] label[data-baseweb="radio"] > div:last-child,
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:last-child {{
      border:1px solid #324455; border-radius:4px; background:#121b27; color:#9cb0c5;
      text-transform:uppercase; letter-spacing:.1em; font-size:.67rem; padding:7px 12px;
    }}
    div[data-testid="stPills"] input:checked + div,
    div[data-testid="stSegmentedControl"] input:checked + div,
    div[data-testid="stRadio"] input:checked + div {{
      background:linear-gradient(180deg, #1c2a3a, #151f2c);
      border-color: color-mix(in srgb, var(--lime) 60%, #52657a 40%);
      color:#ebfff0;
      box-shadow: inset 0 0 0 1px rgba(159,232,112,.18);
    }}

    div[data-testid="stSidebar"] {{
      background: linear-gradient(180deg, #090e15 0%, #0b121b 100%);
      border-right:1px solid #263342;
    }}
    .stButton>button {{
      border:1px solid #415466; border-radius:5px;
      background:linear-gradient(180deg, #16212f, #101822);
      color:#f1f6fc; text-transform:uppercase; letter-spacing:.08em; font-size:.66rem; font-weight:700;
    }}
    .stButton>button:hover {{ border-color:#8ab56b; }}

    div[data-testid="stSelectbox"] > div, div[data-testid="stMultiSelect"] > div,
    div[data-testid="stNumberInput"] > div, div[data-testid="stTextInput"] > div,
    div[data-testid="stSlider"] {{
      border-radius:5px !important; border:1px solid #334455 !important; background:#0e1621 !important;
    }}

    [data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:8px; background:#0d141e; }}

    .player-card {{ min-height: 680px; display:flex; flex-direction:column; gap:8px; }}
    .player-head {{ display:flex; gap:10px; }}
    .player-avatar-frame, .hero-player-photo-frame {{ border:1px solid #3b4d61; border-radius:6px; background:#101925; }}
    .player-avatar-frame {{ width:94px; height:118px; overflow:hidden; }}
    .hero-player-photo-frame {{ width:152px; height:190px; overflow:hidden; }}
    .player-avatar, .hero-player-photo {{ width:100%; height:100%; object-fit:cover; }}
    .player-name {{ margin:0; font-size:.95rem; font-weight:760; letter-spacing:.01em; }}
    .identity-line {{ margin:0; color:var(--muted); font-size:.66rem; letter-spacing:.06em; text-transform:uppercase; }}
    .player-card-note {{ margin:0; font-size:.74rem; line-height:1.4; color:#c3d2e2; }}

    .achievement-strip {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .achievement-tile {{
      position:relative; width:74px; height:82px; overflow:hidden;
      border:1px solid #465769; border-radius:5px;
      background:linear-gradient(180deg,#1a2432,#121a25);
      box-shadow: 0 10px 20px rgba(0,0,0,.3);
    }}
    .achievement-tile-lg {{ width:84px; height:94px; }}
    .achievement-tier {{ font-size:.52rem; padding:1px 4px; border:1px solid currentColor; border-radius:3px; }}
    .achievement-season-top {{
      position:absolute; top:4px; left:4px; right:4px; padding:2px 5px;
      font-size:.5rem; text-align:center; letter-spacing:.08em; text-transform:uppercase;
      background:rgba(8,12,19,.84); border:1px solid rgba(255,255,255,.16); border-radius:3px;
    }}
    .achievement-tile-overlay {{ position:absolute; inset:auto 0 0 0; padding:3px 4px; background:linear-gradient(180deg,transparent,rgba(5,9,14,.88)); }}
    .achievement-event-title {{ font-size:.46rem; line-height:1.2; color:#f3f6ff; font-weight:700; display:block; }}

    .match-list-wrap {{ display:flex; flex-direction:column; gap:7px; }}
    .match-list-item, .last-match-block, .best-match-block {{ border:1px solid #324455; border-radius:6px; padding:7px 9px; background:#101925; }}
    .match-list-head {{ display:flex; justify-content:space-between; font-size:.63rem; }}
    .match-list-line, .last-match-line {{ font-size:.68rem; color:#b8c7d8; margin-top:2px; }}
    .last-match-title {{ font-size:.56rem; letter-spacing:.14em; text-transform:uppercase; color:#8ea2b8; }}
    .last-match-result, .match-outcome {{ border:1px solid #3f4f60; border-radius:3px; padding:1px 5px; font-size:.56rem; letter-spacing:.06em; text-transform:uppercase; }}
    .last-match-result-win, .match-outcome.win {{ color:var(--lime); }}
    .last-match-result-loss, .match-outcome.loss {{ color:var(--crimson); }}

    .player-viewer-hero-grid {{ display:grid; grid-template-columns: minmax(0,2fr) minmax(280px,1fr); gap:10px; }}
    .overview-hero-row {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; }}
    .overview-hero-brand {{ display:flex; align-items:flex-start; gap:10px; }}
    .overview-hero-copy {{ display:flex; flex-direction:column; gap:7px; }}
    .overview-hero-kicker {{ margin:0 !important; }}
    .overview-hero-title {{
      font-size:1.02rem;
      line-height:1.25;
      font-weight:760;
      color:#edf4fd;
      margin:0;
    }}
    .overview-hero-meta, .overview-hero-stats {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; }}

    .player-viewer-head-main {{ display:flex; gap:10px; align-items:flex-start; }}
    .player-viewer-player-title {{
      margin:0 0 2px 0;
      font-size:1.18rem;
      line-height:1.12;
      font-weight:800;
      letter-spacing:.01em;
      color:#f5fbff;
    }}
    .player-viewer-player-meta {{
      margin:0;
      color:#9db0c4;
      font-size:.72rem;
      letter-spacing:.06em;
      text-transform:uppercase;
    }}
    .player-viewer-chip-row {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }}
    .player-viewer-form-note {{ margin-top:8px; }}
    .player-viewer-top-metrics {{ display:grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap:7px; margin-top:10px; }}
    .grev-gauge {{
      --gauge-pct:50%; width:164px; height:164px; border-radius:999px;
      background:conic-gradient(from -90deg, var(--lime) 0 var(--gauge-pct), #2c3b4b var(--gauge-pct) 100%);
      display:grid; place-items:center;
    }}
    .grev-gauge-inner {{ width:120px; height:120px; border-radius:999px; background:#101925; border:1px solid #37485a; display:flex; align-items:center; justify-content:center; flex-direction:column; }}

    .grev-tier-strip {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:6px; }}
    .grev-tier-box {{ border:1px solid #324354; border-radius:6px; padding:6px; background:#121b28; display:flex; flex-direction:column; gap:3px; }}
    .tier-name {{ font-size:.58rem; text-transform:uppercase; letter-spacing:.12em; color:#90a4bb; }}
    .tier-score {{ font-size:1rem; font-weight:800; }}

    .breakdown-table {{ width:100%; border-collapse:collapse; font-size:.74rem; }}
    .breakdown-table th, .breakdown-table td {{ border-bottom:1px solid #273544; padding:8px 7px; text-align:left; }}
    .breakdown-table th {{ background:#121d29; color:#b4c4d7; font-size:.58rem; letter-spacing:.13em; text-transform:uppercase; }}

    @media (max-width: 1120px) {{
      .player-viewer-hero-grid {{ grid-template-columns:1fr; }}
      .player-viewer-top-metrics {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
      .subtle-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    }}
    @media (max-width: 760px) {{
      .block-container {{ padding:.55rem .5rem 1.05rem; }}
      .app-topbar-title {{ font-size:.96rem; }}
      .hero-logo, .app-topbar .hero-logo {{ width:38px; height:38px; }}
      .overview-hero .hero-logo, .player-viewer-hero .hero-logo {{ width:34px; height:34px; }}
      .player-viewer-top-metrics, .stats-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .grev-tier-strip {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    }}
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
