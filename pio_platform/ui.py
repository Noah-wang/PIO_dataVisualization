from __future__ import annotations

import html

import streamlit as st

from pio_platform.config import THEME_PRESETS
from pio_platform.i18n import t


def inject_global_styles(theme_name: str, accent_color: str) -> None:
    theme = THEME_PRESETS[theme_name]
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

        :root {{
            --page-bg: {theme.page_bg};
            --card-bg: {theme.card_bg};
            --card-alt-bg: {theme.card_alt_bg};
            --border: {theme.border};
            --text: {theme.text};
            --muted: {theme.muted_text};
            --accent: {accent_color};
            --sidebar-bg: {theme.sidebar_bg};
            --sidebar-surface: {theme.sidebar_surface};
            --sidebar-text: {theme.sidebar_text};
            --shadow-soft: 0 10px 24px rgba(8, 17, 31, 0.06);
            --shadow-card: 0 6px 16px rgba(8, 17, 31, 0.045);
        }}

        html, body, [class*="css"] {{
            font-family: "IBM Plex Sans", sans-serif;
        }}

        .stApp {{
            background:
                radial-gradient(circle at top right, rgba(15, 98, 254, 0.06), transparent 22%),
                linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0.0)),
                var(--page-bg);
            color: var(--text);
        }}

        [data-testid="stSidebar"] {{
            display: none;
        }}

        [data-testid="collapsedControl"] {{
            display: none;
        }}

        [data-testid="stHeader"] {{
            display: none;
        }}

        .block-container {{
            padding-top: 0.6rem;
            padding-bottom: 2.5rem;
            max-width: 1460px;
        }}

        .pio-kicker {{
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: rgba(15, 98, 254, 0.1);
            color: var(--accent);
            font-size: 0.74rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.13em;
            font-family: "IBM Plex Mono", monospace;
        }}

        .pio-title {{
            font-family: "Manrope", sans-serif;
            font-size: clamp(1.9rem, 2.3vw, 2.9rem);
            line-height: 1.02;
            letter-spacing: -0.04em;
            margin: 0.7rem 0 0.45rem;
            color: var(--text);
            max-width: 18ch;
        }}

        .stFileUploader {{
            margin-bottom: 0;
        }}

        .pio-subtitle {{
            font-size: 0.98rem;
            line-height: 1.7;
            color: var(--muted);
            max-width: 78ch;
            margin: 0;
        }}

        .pio-signal-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.85rem;
        }}

        .pio-signal {{
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.48rem 0.7rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.9);
            border: 1px solid rgba(160, 183, 214, 0.34);
            color: var(--text);
            font-size: 0.82rem;
            font-weight: 600;
        }}

        .pio-signal-dot {{
            width: 0.4rem;
            height: 0.4rem;
            border-radius: 999px;
            background: var(--accent);
            box-shadow: 0 0 0 3px rgba(15, 98, 254, 0.1);
        }}

        .pio-kpi {{
            position: relative;
            overflow: hidden;
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(160, 183, 214, 0.34);
            border-radius: 18px;
            padding: 0.95rem 1rem 0.9rem;
            min-height: 126px;
        }}

        .pio-kpi::before {{
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 2px;
            background: var(--accent);
        }}

        .pio-kpi-label {{
            color: var(--muted);
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.11em;
            font-weight: 600;
            font-family: "IBM Plex Mono", monospace;
        }}

        .pio-kpi-value {{
            font-family: "Manrope", sans-serif;
            font-size: clamp(1.9rem, 2.1vw, 2.6rem);
            line-height: 1;
            letter-spacing: -0.05em;
            font-weight: 700;
            margin: 0.7rem 0 0.45rem;
        }}

        .pio-kpi-foot {{
            color: var(--muted);
            font-size: 0.9rem;
        }}

        .pio-panel {{
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(160, 183, 214, 0.32);
            border-radius: 18px;
            padding: 1rem 1.05rem;
            margin-bottom: 1rem;
        }}

        .pio-panel h3 {{
            font-family: "Manrope", sans-serif;
            font-size: 1.12rem;
            line-height: 1.1;
            margin-top: 0.05rem;
            margin-bottom: 0.5rem;
            letter-spacing: -0.03em;
        }}

        .pio-insight-list {{
            margin: 0;
            padding-left: 1.15rem;
            color: var(--muted);
            line-height: 1.75;
            font-size: 0.96rem;
        }}

        .pio-metadata {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 0.7rem;
        }}

        .pio-meta-pill {{
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(160, 183, 214, 0.32);
            border-radius: 16px;
            padding: 0.8rem 0.85rem;
        }}

        .pio-meta-label {{
            display: block;
            color: var(--muted);
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            margin-bottom: 0.35rem;
            font-family: "IBM Plex Mono", monospace;
        }}

        .pio-meta-value {{
            color: var(--text);
            font-size: 1rem;
            font-weight: 700;
            line-height: 1.5;
            font-family: "Manrope", sans-serif;
        }}

        [data-testid="stDataFrame"] {{
            border: 1px solid rgba(160, 183, 214, 0.35);
            border-radius: 14px;
            overflow: hidden;
        }}

        .stPlotlyChart {{
            background: rgba(255,255,255,0.97);
            border: 1px solid rgba(160, 183, 214, 0.28);
            border-radius: 14px;
            padding: 0.3rem 0.4rem 0.1rem;
        }}

        .stPlotlyChart + div button,
        .stDownloadButton button {{
            border-radius: 999px !important;
            border: 1px solid rgba(160, 183, 214, 0.4) !important;
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(240,246,255,0.96)) !important;
            color: var(--text) !important;
            font-weight: 600 !important;
        }}

        h4 {{
            font-family: "Manrope", sans-serif;
            font-size: 0.98rem;
            letter-spacing: -0.02em;
            margin-bottom: 0.45rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(lang: str) -> None:
    signals = [
        t(lang, "hero_signal_upload"),
        t(lang, "hero_signal_resilient"),
        t(lang, "hero_signal_future"),
    ]
    signal_markup = "".join(
        f'<div class="pio-signal"><span class="pio-signal-dot"></span>{html.escape(signal)}</div>' for signal in signals
    )
    st.markdown(
        f"""
        <section class="pio-hero">
            <span class="pio-kicker">{html.escape(t(lang, "hero_kicker"))}</span>
            <h1 class="pio-title">{html.escape(t(lang, "hero_title"))}</h1>
            <p class="pio-subtitle">{html.escape(t(lang, "hero_subtitle"))}</p>
            <div class="pio-signal-row">{signal_markup}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card(label: str, value: str, footnote: str) -> None:
    st.markdown(
        f"""
        <div class="pio-kpi">
            <div class="pio-kpi-label">{html.escape(label)}</div>
            <div class="pio-kpi-value">{html.escape(value)}</div>
            <div class="pio-kpi-foot">{html.escape(footnote)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def panel_start(title: str, subtitle: str | None = None) -> None:
    subtitle_html = f'<p class="pio-subtitle" style="font-size:0.95rem; margin-bottom:0.4rem;">{html.escape(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f"""
        <section class="pio-panel">
            <h3>{html.escape(title)}</h3>
            {subtitle_html}
        """,
        unsafe_allow_html=True,
    )


def panel_end() -> None:
    st.markdown("</section>", unsafe_allow_html=True)


def render_dataset_metadata(file_name: str, sheet_name: str, profile: dict[str, int], lang: str) -> None:
    items = {
        t(lang, "workbook"): file_name,
        t(lang, "worksheet"): sheet_name,
        t(lang, "header_row"): str(profile["header_row"]),
        t(lang, "header_depth"): str(profile["header_depth"]),
        t(lang, "metadata_rows"): f"{profile['row_count']:,}",
        t(lang, "metadata_columns"): f"{profile['column_count']:,}",
    }
    pills = "".join(
        f'<div class="pio-meta-pill"><span class="pio-meta-label">{html.escape(label)}</span><span class="pio-meta-value">{html.escape(value)}</span></div>'
        for label, value in items.items()
    )
    st.markdown(f'<div class="pio-metadata">{pills}</div>', unsafe_allow_html=True)
