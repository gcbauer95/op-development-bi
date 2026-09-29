"""Helpers de apresentação para tabelas e números no padrão brasileiro."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import streamlit as st


def format_br_number(value: object, decimals: int = 0) -> str:
    """Formata um número com ponto para milhar e vírgula para decimais."""
    if value is None or pd.isna(value):
        return ""
    try:
        formatted = f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)
    return formatted.replace(",", "#").replace(".", ",").replace("#", ".")


def display_dataframe(
    data: pd.DataFrame,
    *,
    labels: Mapping[str, str] | None = None,
    number_formats: Mapping[str, int] | None = None,
    percent_formats: Mapping[str, int] | None = None,
    date_formats: Mapping[str, str] | None = None,
    hide_index: bool = False,
) -> None:
    """Renderiza uma cópia da tabela com rótulos e números amigáveis."""
    frame = data.copy()
    # Os valores permanecem numéricos para que a ordenação do usuário seja
    # quantitativa. A máscara é aplicada somente na camada visual do Streamlit.
    column_labels = dict(labels or {})
    frame = frame.rename(columns=column_labels)
    column_config = {}

    for column, decimals in (number_formats or {}).items():
        display_column = column_labels.get(column, column)
        if display_column in frame.columns:
            column_config[display_column] = st.column_config.NumberColumn(
                display_column,
                format="localized",
            )

    for column, decimals in (percent_formats or {}).items():
        display_column = column_labels.get(column, column)
        if display_column in frame.columns:
            column_config[display_column] = st.column_config.NumberColumn(
                display_column,
                # Percentuais do projeto são armazenados de 0 a 100.
                format=f"%.{decimals}f%%",
            )

    for column, date_format in (date_formats or {}).items():
        display_column = column_labels.get(column, column)
        if display_column in frame.columns:
            column_config[display_column] = st.column_config.DateColumn(
                display_column,
                format=date_format,
            )

    st.dataframe(frame, width="stretch", hide_index=hide_index, column_config=column_config)
