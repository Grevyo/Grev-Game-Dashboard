import streamlit as st

from app.config import TIER_COLORS, THEMES


def inject_styles(theme_name: str = "Dark"):
    theme = THEMES.get(theme_name, THEMES["Dark"])
    css = f"""
    <style>
    .stApp {{ background: {theme['bg']}; color: {theme['text']}; }}
    .chip {{ display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid {theme['border']};font-size:12px;margin-right:6px; }}
    .panel {{ background:{theme['surface']}; border:1px solid {theme['border']}; border-radius:14px; padding:12px 14px; margin-bottom:10px; }}
    .stat-good {{ color:{theme['good']}; }} .stat-mid {{ color:{theme['mid']}; }}
    .stat-poor {{ color:{theme['poor']}; }} .stat-bad {{ color:{theme['bad']}; }}
    .muted {{ color:{theme['muted']};font-size:12px; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def tier_badge(tier: str) -> str:
    color = TIER_COLORS.get(str(tier).strip().upper(), "#8892b0")
    return f"<span class='chip' style='background:{color}26;border-color:{color};'>{tier}</span>"
