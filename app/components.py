import math

import streamlit as st

from app.metrics import classify_quality
from app.styles import tier_badge


def section_header(title: str, subtitle: str = ""):
    st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='section-subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def stat_card(label: str, value, help_text: str = "", quality_override: str | None = None):
    num_value = None
    try:
        num_value = float(value)
    except Exception:
        num_value = None
    quality = quality_override or (classify_quality(num_value) if isinstance(num_value, (int, float)) and not math.isnan(num_value) else "mid")
    st.markdown(
        f"""
        <div class='panel panel-tight accent-{quality}'>
            <div class='metric-title'>{label}</div>
            <div class='metric-value stat-{quality}'>{value}</div>
            <div class='muted'>{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _tone_from_score(score: float) -> str:
    if score >= 72:
        return "good"
    if score >= 58:
        return "mid"
    if score >= 44:
        return "poor"
    return "bad"


def trend_chip(trend: str) -> str:
    key = str(trend or "Flat").strip().lower()
    tone = "mid"
    icon = "•"
    if "up" in key or "hot" in key or "rise" in key:
        tone = "good"
        icon = "↗"
    elif "down" in key or "cold" in key or "fall" in key:
        tone = "bad"
        icon = "↘"
    return f"<span class='chip chip-{tone}'>{icon} {trend}</span>"


def player_card(row: dict):
    grev = float(row.get("grevscore", 0) or 0)
    tone = _tone_from_score(grev)
    identity_bits = [row.get("team_tag", "Medisports")]
    if row.get("country"):
        identity_bits.append(str(row.get("country")))
    if row.get("role"):
        identity_bits.append(str(row.get("role")))

    photo_uri = row.get("photo_uri")
    logo_uri = row.get("team_logo_uri")
    photo_missing_reason = str(row.get("photo_missing_reason", "not found"))
    profile_visual = (
        f"<img class='player-avatar' src='{photo_uri}' alt='Player photo'/>"
        if photo_uri
        else f"<div class='player-avatar fallback-avatar'>No Photo<br><small>{photo_missing_reason}</small></div>"
    )
    logo_visual = f"<img class='team-mini-logo' src='{logo_uri}' alt='Team logo'/>" if logo_uri else ""

    stat_items = [
        ("GrevScore", f"{grev:.1f}"),
        ("Rating", f"{float(row.get('rating', 0) or 0):.2f}"),
        ("K/D", f"{float(row.get('kpd', 0) or 0):.2f}"),
        ("Impact", f"{float(row.get('impact', 0) or 0):.1f}"),
        ("HS%", f"{float(row.get('hs_pct', 0) or 0):.1f}%"),
        ("Matches", f"{int(row.get('matches', 0) or 0)}"),
    ]
    stats_html = "".join(
        f"<div class='stat-item'><div class='label'>{label}</div><div class='value'>{value}</div></div>" for label, value in stat_items
    )

    card_html = f"""
    <div class='panel player-card accent-{tone}'>
        <div class='player-head'>
          <div class='player-head-left'>{profile_visual}</div>
          <div class='player-head-meta'>
            <p class='player-name'>{row.get('player', 'Unknown')}</p>
            <p class='identity-line'>{' • '.join(identity_bits)}</p>
          </div>
          <div>{logo_visual}</div>
        </div>
        <div>{tier_badge(row.get('tier', '-'))}{trend_chip(row.get('trend', 'Stable'))}</div>
        <p class='player-desc'>{row.get('desc', '')}</p>
        <div class='stats-grid'>{stats_html}</div>
        <div class='muted'>Best map <strong>{row.get('best_map', 'N/A')}</strong> · Best side <strong>{row.get('best_side', 'N/A')}</strong></div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def insight_card(title: str, body: str, level: str = "info"):
    tone = {"info": "mid", "warn": "poor", "good": "good", "bad": "bad"}.get(level, "mid")
    icon = {"info": "ℹ", "warn": "⚠", "good": "▲", "bad": "▼"}.get(level, "ℹ")
    st.markdown(
        f"<div class='panel panel-tight accent-{tone}'><strong>{icon} {title}</strong><br><span class='muted'>{body}</span></div>",
        unsafe_allow_html=True,
    )


def render_filter_chip(label: str, value: str):
    st.markdown(f"<span class='chip'>{label}: {value}</span>", unsafe_allow_html=True)
