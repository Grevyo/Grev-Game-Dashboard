"""Shared page-level layout helpers used across dashboard screens.

These wrappers keep page modules stable when component/helper modules are
refactored during redesign work.
"""

import streamlit as st


def section_header(title: str, subtitle: str = "") -> None:
    """Render the standard premium page section heading."""
    st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='section-subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def is_mobile_view(default: bool = False) -> bool:
    """Best-effort mobile detection based on request user-agent."""
    context = getattr(st, "context", None)
    headers = getattr(context, "headers", None) if context is not None else None
    if not headers:
        return default

    user_agent = str(headers.get("user-agent", "")).lower()
    if not user_agent:
        return default

    mobile_tokens = ["iphone", "android", "mobile", "ipad", "ipod", "windows phone"]
    return any(token in user_agent for token in mobile_tokens)
