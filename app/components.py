import math

import streamlit as st

from app.metrics import classify_quality, stat_tone
from app.presentation_helpers import fame_to_stars, nationality_label
from app.styles import achievement_tier_badge


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
    if score >= 1.4:
        return "good"
    if score >= 1.0:
        return "mid"
    if score >= 0.75:
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
    if row.get("role"):
        identity_bits.append(str(row.get("role")))
    nationality = nationality_label(row.get("nationality") or row.get("country"))
    if nationality:
        identity_bits.append(nationality)

    photo_uri = row.get("photo_uri")
    logo_uri = row.get("team_logo_uri")
    photo_missing_reason = str(row.get("photo_missing_reason", "not found"))
    profile_visual = (
        f"<div class='player-avatar-frame'><img class='player-avatar' src='{photo_uri}' alt='Player photo'/></div>"
        if photo_uri
        else f"<div class='player-avatar-frame'><div class='player-avatar fallback-avatar'>No Photo<br><small>{photo_missing_reason}</small></div></div>"
    )
    logo_visual = f"<img class='team-mini-logo' src='{logo_uri}' alt='Team logo'/>" if logo_uri else ""

    fame_stars, fame_numeric = fame_to_stars(row.get("fame"))
    fame_html = (
        f"<div class='fame-line'><span class='fame-label'>Fame</span><span class='fame-stars'>{fame_stars}</span><span class='fame-value'>{fame_numeric}</span></div>"
        if fame_stars
        else ""
    )

    stat_items = [
        ("GrevScore", grev, f"{grev:.2f}"),
        ("Rating", float(row.get("rating", 0) or 0), f"{float(row.get('rating', 0) or 0):.2f}"),
        ("K/D", float(row.get("kpd", 0) or 0), f"{float(row.get('kpd', 0) or 0):.2f}"),
        ("Impact", float(row.get("impact", 0) or 0), f"{float(row.get('impact', 0) or 0):.1f}"),
        ("Form", float(row.get("form", 0) or 0), f"{float(row.get('form', 0) or 0):.2f}"),
        ("KPR", float(row.get("kpr", 0) or 0), f"{float(row.get('kpr', 0) or 0):.2f}"),
        ("Accuracy", float(row.get("accuracy_pct", 0) or 0), f"{float(row.get('accuracy_pct', 0) or 0):.1f}%"),
        ("HS%", float(row.get("hs_pct", 0) or 0), f"{float(row.get('hs_pct', 0) or 0):.1f}%"),
    ]
    stats_html = "".join(
        (
            f"<div class='stat-item tone-{stat_tone(label, val)}'>"
            f"<div class='label'>{label}</div><div class='value stat-{stat_tone(label, val)}'>{formatted}</div></div>"
        )
        for label, val, formatted in stat_items
    )
    ach_items = row.get("achievements", []) or []
    ach_chunks = []
    for a in ach_items[:3]:
        thumb = f"<img class='achievement-chip-thumb' src='{a.get('image_uri')}' alt='Achievement'/>" if a.get("image_uri") else ""
        season_tag = f"S{a.get('season')}" if a.get("season") else ""
        tier = str(a.get("tier", "-")).strip().upper()
        ach_chunks.append(
            f"<div class='achievement-chip'>{thumb}<div><div class='achievement-chip-name'>{a.get('name','Achievement')}</div>"
            f"<div class='achievement-chip-meta'>{a.get('position','')} {season_tag}</div></div>{achievement_tier_badge(tier)}</div>"
        )
    ach_html = "".join(ach_chunks)
    if row.get("achievements_hidden", 0):
        ach_html += f"<div class='chip achievement-more'>+{int(row.get('achievements_hidden', 0))} more</div>"

    card_html = f"""
    <div class='panel player-card accent-{tone}'>
        <div class='player-head'>
          <div class='player-head-left'>{profile_visual}</div>
          <div class='player-head-meta'>
            <div class='player-head-title-row'>
              <p class='player-name'>{row.get('player', 'Unknown')}</p>
              <div>{logo_visual}</div>
            </div>
            <p class='identity-line'>{' • '.join(identity_bits)}</p>
            {fame_html}
            <div class='achievement-strip achievement-strip-featured'>{ach_html or "<span class='muted'>No achievements recorded</span>"}</div>
          </div>
        </div>
        <div class='player-meta-row'>{trend_chip(row.get('trend', 'Stable'))}<span class='muted'>Best map <strong>{row.get('best_map', 'N/A')}</strong> · Best side <strong>{row.get('best_side', 'N/A')}</strong></span></div>
        <p class='player-desc'>{row.get('desc', '')}</p>
        <div class='stats-grid'>{stats_html}</div>
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
