import streamlit as st

from app.metrics import classify_quality
from app.styles import tier_badge


def section_header(title: str, subtitle: str = ""):
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)


def stat_card(label: str, value, help_text: str = ""):
    quality = classify_quality(float(value)) if isinstance(value, (int, float)) else "mid"
    st.markdown(f"<div class='panel'><div class='muted'>{label}</div><div class='stat-{quality}' style='font-size:24px;font-weight:700'>{value}</div><div class='muted'>{help_text}</div></div>", unsafe_allow_html=True)


def player_card(row, photo_path=None):
    cols = st.columns([1, 3, 2])
    with cols[0]:
        if photo_path:
            st.image(photo_path, use_container_width=True)
    with cols[1]:
        st.markdown(f"**{row.get('player','Unknown')}**")
        st.markdown(f"{row.get('desc','')}")
        st.markdown(tier_badge(row.get("tier", "-")), unsafe_allow_html=True)
    with cols[2]:
        st.metric("GrevScore", f"{row.get('grevscore',0):.1f}")
        st.metric("K/D", f"{row.get('kpd',0):.2f}")


def insight_card(title: str, body: str, level: str = "info"):
    icon = {"info": "ℹ️", "warn": "⚠️", "good": "✅"}.get(level, "ℹ️")
    st.markdown(f"<div class='panel'><strong>{icon} {title}</strong><br><span class='muted'>{body}</span></div>", unsafe_allow_html=True)
