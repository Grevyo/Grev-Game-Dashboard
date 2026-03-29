import html
import math
import re

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


def _clean_card_meta_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _tone_from_score(score: float) -> str:
    if score >= 1.4:
        return "good"
    if score >= 1.0:
        return "mid"
    if score >= 0.75:
        return "poor"
    return "bad"


def _strip_tags_to_text(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text





def _player_note(row: dict) -> str:
    if row.get("roster_bucket") == "streamer" or row.get("card_variant") == "streamer":
        return "Streamer profile — competitive stats not yet tracked."
    custom_desc = str(row.get("desc", "")).strip()
    if custom_desc:
        return custom_desc
    grev = float(row.get("grevscore", 0) or 0)
    kpd = float(row.get("kpd", 0) or 0)
    trend = str(row.get("trend", "Stable") or "Stable")
    best_map = row.get("best_map", "N/A")
    return f"{trend} form. Best map: {best_map}. Baseline: {grev:.2f} GrevScore with {kpd:.2f} K/D in this scope."

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


def render_achievement_mini_tile(achievement: dict) -> str:
    tier = str(achievement.get("tier", "")).strip().upper()
    tier = tier if tier in {"S", "A", "B", "C"} else "C"
    thumb = (
        f"<img class='achievement-tile-thumb' src='{achievement.get('image_uri')}' alt='{achievement.get('name', 'Achievement')}'/>"
        if achievement.get("image_uri")
        else "<div class='achievement-tile-thumb achievement-tile-thumb-fallback'>No Image</div>"
    )
    season_label = str(achievement.get("season_label", "")).strip()
    return (
        f"<div class='achievement-tile tier-{tier}'>"
        f"{thumb}"
        f"<div class='achievement-tile-overlay'>"
        f"{achievement_tier_badge(tier)}"
        f"<span class='achievement-season'>{season_label}</span>"
        f"</div></div>"
    )


def _tier_box_html(tier: str, score: float | None) -> str:
    display = f"{score:.2f}" if isinstance(score, (int, float)) else "n/a"
    return (
        f"<div class='grev-tier-box grev-tier-{tier}'>"
        f"<span class='tier-name'>vs {tier}</span>"
        f"<span class='tier-score'>{display}</span>"
        "</div>"
    )


def player_card(row: dict):
    roster_bucket = str(row.get("roster_bucket", "") or "").strip().casefold()
    card_variant = str(row.get("card_variant", "") or "").strip().casefold()
    is_streamer_card = roster_bucket == "streamer" or card_variant == "streamer"
    grev = float(row.get("grevscore", 0) or 0)
    tone = "mid" if is_streamer_card else _tone_from_score(grev)
    nationality = _strip_tags_to_text(nationality_label(row.get("nationality") or row.get("country")))
    identity_line = nationality or "Nationality N/A"
    role_line = "Streamer" if is_streamer_card else (row.get("role") or "Role N/A")

    photo_uri = row.get("photo_uri")
    logo_uri = row.get("team_logo_uri")
    photo_missing_reason = str(row.get("photo_missing_reason", "not found"))
    profile_visual = (
        f"<div class='player-avatar-frame'><img class='player-avatar' src='{photo_uri}' alt='Player photo'/></div>"
        if photo_uri
        else f"<div class='player-avatar-frame'><div class='player-avatar fallback-avatar'>No Photo<br><small>{photo_missing_reason}</small></div></div>"
    )
    logo_visual = f"<img class='team-mini-logo' src='{logo_uri}' alt='Team logo'/>" if logo_uri else ""

    fame_value = _clean_card_meta_value(row.get("fame"))
    fame_stars, fame_numeric = fame_to_stars(fame_value)
    fame_html = (
        f"<div class='fame-line'><span class='fame-label'>Fame</span><span class='fame-stars'>{fame_stars}</span><span class='fame-value'>{fame_numeric}</span></div>"
        if fame_stars and fame_numeric
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
    ach_html = "".join(render_achievement_mini_tile(a) for a in ach_items[:4])

    tier_order = ["S", "A", "B", "C"]
    tier_grevscores = row.get("tier_grevscores", {}) or {}
    tier_boxes = "".join(_tier_box_html(t, tier_grevscores.get(t)) for t in tier_order)
    tier_html = "<div class='grev-tier-strip'><div class='grev-tier-label'>GrevScore vs Tier Bands</div>" f"<div class='grev-tier-row'>{tier_boxes}</div></div>"
    if int(row.get("achievements_hidden", 0) or 0) > 0:
        ach_html += f"<div class='achievement-overflow'>+{int(row.get('achievements_hidden', 0))}</div>"
    if not ach_html and not is_streamer_card:
        ach_html = "<div class='achievement-empty'>No achievements recorded</div>"
    achievements_block_html = f"<div class='achievement-strip achievement-strip-featured'>{ach_html}</div>" if ach_html else ""

    safe_identity_line = html.escape(str(identity_line))
    safe_role_line = html.escape(str(role_line))
    safe_player_note = html.escape(str(_player_note(row) or ""))
    trend_html = "" if is_streamer_card else trend_chip(row.get("trend", "Stable"))
    context_html = (
        ""
        if is_streamer_card
        else (
            "<div class='player-meta-row'><span class='muted'>Best map <strong>"
            f"{html.escape(str(row.get('best_map', 'N/A')))}</strong> · Best side <strong>{html.escape(str(row.get('best_side', 'N/A')))}</strong></span></div>"
        )
    )
    stats_block_html = "" if is_streamer_card else f"<div class='stats-grid'>{stats_html}</div>"
    tier_block_html = "" if is_streamer_card else tier_html

    card_html = f"""
    <div class='panel player-card accent-{tone}{' player-card-subdued' if row.get('card_variant') in {'subdued', 'streamer'} else ''}'>
        <div class='player-head'>
          <div class='player-head-left'>
            {profile_visual}
          </div>
          <div class='player-head-meta'>
            <div class='player-head-title-row'>
              <div class='player-name-row'>
                <p class='player-name'>{html.escape(str(row.get('player', 'Unknown')))}</p>
                {trend_html}
              </div>
              <div>{logo_visual}</div>
            </div>
            <p class='identity-line'>{safe_identity_line}</p>
            <p class='identity-line'>{safe_role_line}</p>
            {fame_html}
            {context_html}
          </div>
        </div>
        {achievements_block_html}
        {stats_block_html}
        {tier_block_html}
        <div class='player-card-bottom'><p class='player-card-note'>{safe_player_note}</p></div>
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
