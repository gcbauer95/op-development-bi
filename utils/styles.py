from __future__ import annotations

from pathlib import Path

import streamlit as st


CSS_PATH = Path(__file__).resolve().parents[1] / "assets" / "css" / "style.css"


@st.cache_data(show_spinner=False)
def _read_css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def apply_theme() -> None:
    """Carrega o design system visual compartilhado do dashboard."""
    st.markdown(f"<style>{_read_css()}</style>", unsafe_allow_html=True)


def apply_chart_theme(fig):
    """Aplica a paleta OpenCode a uma figura Plotly, quando usada no projeto."""
    fig.update_layout(
        paper_bgcolor="#fdfcfc",
        plot_bgcolor="#fdfcfc",
        font={
            "family": '"Berkeley Mono", "SFMono-Regular", "Roboto Mono", monospace',
            "color": "#201d1d",
            "size": 14,
        },
        margin={"l": 16, "r": 16, "t": 20, "b": 16},
        hoverlabel={
            "bgcolor": "#201d1d",
            "font": {"color": "#fdfcfc"},
        },
    )
    fig.update_xaxes(
        gridcolor="rgba(15,0,0,0.12)",
        linecolor="#646262",
        zerolinecolor="rgba(15,0,0,0.12)",
    )
    fig.update_yaxes(
        gridcolor="rgba(15,0,0,0.12)",
        linecolor="#646262",
        zerolinecolor="rgba(15,0,0,0.12)",
    )
    return fig
