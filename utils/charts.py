from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.styles import apply_chart_theme
from utils.display import format_br_number


def _series_frame(data: pd.Series | pd.DataFrame) -> tuple[pd.DataFrame, str, list[str]]:
    if isinstance(data, pd.Series):
        frame = data.rename(data.name or "Valor").reset_index()
    else:
        frame = data.reset_index()
    x_column = frame.columns[0]
    value_columns = [str(column) for column in frame.columns[1:]]
    return frame, x_column, value_columns


def line_chart(
    data: pd.Series | pd.DataFrame,
    *,
    height: int = 360,
    y_title: str | None = None,
    value_decimals: int = 0,
    value_prefix: str = "",
) -> None:
    frame, x_column, value_columns = _series_frame(data)
    fig = go.Figure()
    for column in value_columns:
        formatted_values = frame[column].map(lambda value: format_br_number(value, value_decimals))
        fig.add_trace(
            go.Scatter(
                x=frame[x_column],
                y=frame[column],
                name=column,
                mode="lines+markers",
                connectgaps=False,
                customdata=formatted_values,
                hovertemplate=f"<b>%{{x}}</b><br>{column}: {value_prefix}%{{customdata}}<extra></extra>",
            )
        )
    fig.update_layout(
        height=height,
        xaxis_title=None,
        yaxis_title=y_title,
        # O modo closest mantém a caixa de dados dentro da área disponível,
        # inclusive em gráficos com muitas séries e legenda inferior.
        hovermode="closest",
        showlegend=len(value_columns) > 1,
        legend=(
            {
                "orientation": "h",
                "yanchor": "top",
                "y": -0.28,
                "xanchor": "left",
                "x": 0,
            }
            if len(value_columns) > 1
            else {}
        ),
        margin={"l": 72, "r": 24, "t": 24, "b": 120 if len(value_columns) > 1 else 64},
        separators=",.",
    )
    apply_chart_theme(fig)
    fig.update_layout(
        margin={"l": 72, "r": 24, "t": 24, "b": 120 if len(value_columns) > 1 else 64},
        height=height,
        separators=",.",
        hoverlabel={"align": "left", "namelength": -1},
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def bar_chart(
    data: pd.Series | pd.DataFrame,
    *,
    x: str | None = None,
    y: str | Sequence[str] | None = None,
    height: int = 360,
    y_title: str | None = None,
) -> None:
    if isinstance(data, pd.Series):
        frame = data.rename(data.name or "Valor").reset_index()
        x_column = frame.columns[0]
        y_columns = [frame.columns[1]]
    else:
        frame = data.reset_index(drop=True)
        x_column = x or frame.columns[0]
        y_columns = [y] if isinstance(y, str) else list(y or frame.columns[1:])

    fig = go.Figure()
    for column in y_columns:
        formatted_values = frame[column].map(lambda value: format_br_number(value, 0))
        fig.add_trace(
            go.Bar(
                x=frame[x_column],
                y=frame[column],
                name=str(column),
                cliponaxis=False,
                text=formatted_values,
                texttemplate="%{text}",
                customdata=formatted_values,
                hovertemplate=f"<b>%{{x}}</b><br>{column}: %{{customdata}}<extra></extra>",
            )
        )
    fig.update_layout(
        height=height,
        barmode="group",
        yaxis_title=y_title,
        showlegend=len(y_columns) > 1,
        margin={"l": 72, "r": 24, "t": 24, "b": 88},
        separators=",.",
    )
    apply_chart_theme(fig)
    fig.update_layout(
        margin={"l": 72, "r": 24, "t": 24, "b": 88},
        height=height,
        separators=",.",
        hovermode="closest",
        hoverlabel={"align": "left", "namelength": -1},
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
