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
    if score >= 1.2:
        return "good"
    if score >= 1.0:
        return "mid"
    if score >= 0.76:
        return "poor"
    return "bad"


def _strip_tags_to_text(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _identity_line_text(row: dict, is_streamer_card: bool) -> str:
    def _clean_identity_source(value) -> str:
        text = _strip_tags_to_text(value)
        if not text:
            return ""
        lowered = text.casefold()
        if lowered in {"streamer", "n/a", "na", "none", "null", "unknown", "-", "--"}:
            return ""
        return text

    primary = _clean_identity_source(row.get("nationality"))
    fallback = "" if is_streamer_card else _clean_identity_source(row.get("country"))
    safe_identity = nationality_label(primary or fallback)
    return _strip_tags_to_text(safe_identity) or "Nationality N/A"





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


def render_achievement_mini_tile(achievement: dict, size_variant: str = "overview") -> str:
    tier = str(achievement.get("tier", "")).strip().upper()
    tier = tier if tier in {"S", "A", "B", "C"} else "C"
    variant_class = "achievement-tile-lg" if str(size_variant).strip().casefold() == "viewer" else ""
    image_value = achievement.get("image_uri")
    has_image_branch = bool(image_value)
    thumb = (
        f"<img class='achievement-tile-thumb' src='{image_value}' alt='{achievement.get('name', 'Achievement')}'/>"
        if has_image_branch
        else "<div class='achievement-tile-thumb achievement-tile-thumb-fallback'>No Image</div>"
    )
    season_label = str(achievement.get("season_label", "")).strip()
    event_title = str(achievement.get("name", "")).strip()
    card_html = (
        f"<div class='achievement-tile {variant_class} tier-{tier}'>"
        f"{thumb}"
        f"<div class='achievement-season-top'>{season_label}</div>"
        f"<div class='achievement-tile-overlay'>"
        f"{achievement_tier_badge(tier)}"
        f"<span class='achievement-event-title' title='{event_title}'>{event_title}</span>"
        f"</div></div>"
    )
    return card_html


def _tier_box_html(tier: str, score: float | None) -> str:
    display = f"{score:.2f}" if isinstance(score, (int, float)) else "n/a"
    return (
        f"<div class='grev-tier-box grev-tier-{tier}'>"
        f"<span class='tier-name'>vs {tier}</span>"
        f"<span class='tier-score'>{display}</span>"
        "</div>"
    )


def _last_match_block_html(last_match: dict | None, title: str = "Last Match", empty_text: str = "No recent match", block_variant: str = "last") -> str:
    safe_title = html.escape(str(title))
    safe_empty_text = html.escape(str(empty_text))
    variant_class = "best-match-block" if block_variant == "best" else "last-match-block"
    if not last_match:
        return (
            f"<div class='{variant_class}'>"
            f"<div class='last-match-title'>{safe_title}</div>"
            f"<div class='last-match-line muted'>{safe_empty_text}</div>"
            "</div>"
        )

    date_played = html.escape(str(last_match.get("date_played", "")).strip())
    opponent = html.escape(str(last_match.get("opponent_team", "")).strip())
    result = html.escape(str(last_match.get("result", "")).strip())
    kpd = last_match.get("kpd")
    grevscore = last_match.get("grevscore")
    if not opponent or not result or not isinstance(kpd, (int, float)) or not isinstance(grevscore, (int, float)):
        return (
            f"<div class='{variant_class}'>"
            f"<div class='last-match-title'>{safe_title}</div>"
            f"<div class='last-match-line muted'>{safe_empty_text}</div>"
            "</div>"
        )

    result_key = result.strip().casefold()
    result_tone = "win" if "win" in result_key or result_key == "w" else "loss" if "loss" in result_key or result_key == "l" else "neutral"

    date_line = f"<div class='last-match-line muted'>Played: <strong>{date_played}</strong></div>" if date_played else ""
    return (
        f"<div class='{variant_class}'>"
        f"<div class='last-match-title'>{safe_title}</div>"
        f"{date_line}"
        f"<div class='last-match-line'>vs <strong>{opponent}</strong> • <strong class='last-match-result last-match-result-{result_tone}'>{result}</strong></div>"
        f"<div class='last-match-line muted'>KD: <strong class='last-match-metric'>{kpd:.2f}</strong> • GrevScore: <strong class='last-match-metric'>{grevscore:.2f}</strong></div>"
        "</div>"
    )


def player_card(row: dict):
    roster_bucket = str(row.get("roster_bucket", "") or "").strip().casefold()
    card_variant = str(row.get("card_variant", "") or "").strip().casefold()
    is_streamer_card = roster_bucket == "streamer" or card_variant == "streamer"
    grev = float(row.get("grevscore", 0) or 0)
    tone = "mid" if is_streamer_card else _tone_from_score(grev)
    identity_line = _identity_line_text(row, is_streamer_card)
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

    safe_player_name = html.escape(str(row.get("player", "Unknown")))
    safe_identity_line = html.escape(str(identity_line))
    safe_role_line = html.escape(str(role_line))
    safe_player_note = html.escape(str(_player_note(row) or ""))
    safe_best_map_label = html.escape(str(row.get("best_map_label", f"Best Map: {row.get('best_map', 'N/A')}")))
    safe_favourite_map = html.escape(str(row.get("favourite_map", "N/A")))
    last_match_title = "Last Match" if is_streamer_card else "Last Match ✓"
    last_match_html = _last_match_block_html(None, title=last_match_title) if is_streamer_card else _last_match_block_html(row.get("last_match"), title=last_match_title)
    best_match_html = _last_match_block_html(None, title="Best Match", empty_text="No best match", block_variant="best") if is_streamer_card else _last_match_block_html(row.get("best_match"), title="Best Match ✓", empty_text="No best match", block_variant="best")

    if is_streamer_card:
        streamer_card_html = f"""
        <div class='panel player-card player-card-streamer accent-mid player-card-subdued'>
            <div class='player-head player-head-streamer'>
                <div class='player-head-left'>
                    {profile_visual}
                </div>
                <div class='player-head-meta'>
                    <div class='player-head-title-row'>
                        <div class='player-name-row'>
                            <p class='player-name'>{safe_player_name}</p>
                        </div>
                        <div>{logo_visual}</div>
                    </div>
                    <p class='identity-line'>{safe_identity_line}</p>
                    <p class='identity-line'>{safe_role_line}</p>
                    {fame_html}
                    <div class='player-meta-row'><span class='muted'><strong>{safe_best_map_label}</strong> · Favourite map <strong>{safe_favourite_map}</strong></span></div>
                    {last_match_html}
                    {best_match_html}
                </div>
            </div>
            <div class='player-card-bottom'><p class='player-card-note'>{safe_player_note}</p></div>
        </div>
        """
        st.markdown(streamer_card_html, unsafe_allow_html=True)
        return

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
    ach_html = "".join(render_achievement_mini_tile(a) for a in ach_items)

    tier_order = ["S", "A", "B", "C"]
    tier_grevscores = row.get("tier_grevscores", {}) or {}
    tier_boxes = "".join(_tier_box_html(t, tier_grevscores.get(t)) for t in tier_order)
    tier_html = (
        "<div class='grev-tier-strip'><div class='grev-tier-label'>GrevScore vs Tier Bands</div>"
        f"<div class='grev-tier-row'>{tier_boxes}</div>"
        "<div class='muted grev-band-legend'>Super: 1.20+ • Good: 1.00–1.19 • Meh: 0.76–0.99 • Bad: ≤0.75</div></div>"
    )
    if not ach_html:
        ach_html = "<div class='achievement-empty'>No achievements recorded</div>"
    achievements_block_html = (
        f"<div class='achievement-strip achievement-strip-featured'>{ach_html}</div>"
        if ach_html
        else ""
    )

    context_html = (
        "<div class='player-meta-row'><span class='muted'><strong>"
        f"{safe_best_map_label}</strong> · Favourite map <strong>{safe_favourite_map}</strong> · Best side <strong>{html.escape(str(row.get('best_side', 'N/A')))}</strong></span></div>"
    )
    stats_block_html = f"<div class='stats-grid'>{stats_html}</div>"
    tier_block_html = tier_html

    card_html = f"""
    <div class='panel player-card accent-{tone}{' player-card-subdued' if row.get('card_variant') in {'subdued', 'streamer'} else ''}'>
        <div class='player-head'>
          <div class='player-head-left'>
            {profile_visual}
          </div>
          <div class='player-head-meta'>
            <div class='player-head-title-row'>
              <div class='player-name-row'>
                <p class='player-name'>{safe_player_name}</p>
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
        {last_match_html}
        {best_match_html}
        {stats_block_html}
        {tier_block_html}
        <div class='player-card-bottom'><p class='player-card-note'>{safe_player_note}</p></div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)



def style_refresh_note():
    st.markdown("<div class='style-refresh-note'>Style Refresh ✓</div>", unsafe_allow_html=True)


def data_section_shell(title: str, subtitle: str = "", tone: str = "mid"):
    st.markdown(
        f"""
        <div class='panel data-section-shell accent-{tone}'>
          <div class='section-title data-shell-title'>{title}</div>
          {f"<div class='section-subtitle data-shell-subtitle'>{subtitle}</div>" if subtitle else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )

def insight_card(title: str, body: str, level: str = "info"):
    tone = {"info": "mid", "warn": "poor", "good": "good", "bad": "bad"}.get(level, "mid")
    icon = {"info": "ℹ", "warn": "⚠", "good": "▲", "bad": "▼"}.get(level, "ℹ")
    st.markdown(
        f"<div class='panel panel-tight accent-{tone}'><strong>{icon} {title}</strong><br><span class='muted'>{body}</span></div>",
        unsafe_allow_html=True,
    )


def render_filter_chip(label: str, value: str):
    st.markdown(f"<span class='chip'>{label}: {value}</span>", unsafe_allow_html=True)
