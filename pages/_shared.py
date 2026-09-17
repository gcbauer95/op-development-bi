"""Funções compartilhadas pelas páginas do BI de movimentação."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.loader import load_data  # noqa: E402


PRODUCTION_COL = "Qt Aprovada"
DATE_COL = "Data Saída"


@st.cache_data(show_spinner="Carregando dados de movimentação...")
def get_movements() -> pd.DataFrame:
    """Carrega e padroniza somente os campos usados nas análises."""
    df = load_data("movimentacao").copy()
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df["Data Entrada"] = pd.to_datetime(df["Data Entrada"], errors="coerce")
    df[PRODUCTION_COL] = pd.to_numeric(df[PRODUCTION_COL], errors="coerce").fillna(0)
    df["Qt OF"] = pd.to_numeric(df["Qt OF"], errors="coerce").fillna(0)
    df["Mês"] = df[DATE_COL].dt.to_period("M").astype("string")
    return df


def _options(df: pd.DataFrame, column: str) -> list:
    return sorted(df[column].dropna().unique().tolist(), key=lambda value: str(value))


def sidebar_filters(
    df: pd.DataFrame,
    *,
    key_prefix: str,
    include_sector: bool = True,
    include_faction: bool = False,
    default_excluded_factions: list[str] | None = None,
    date_column: str = DATE_COL,
) -> pd.DataFrame:
    """Aplica filtros globais sem criar cópias até o final."""
    st.sidebar.header("Filtros")
    valid_dates = df[date_column].dropna()
    if not valid_dates.empty:
        selected_dates = st.sidebar.date_input(
            "Período (Data Saída)",
            value=(valid_dates.min().date(), valid_dates.max().date()),
            min_value=valid_dates.min().date(),
            max_value=valid_dates.max().date(),
            format="DD/MM/YYYY",
            key=f"{key_prefix}_dates",
        )
        if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
            start, end = pd.Timestamp(selected_dates[0]), pd.Timestamp(selected_dates[1])
            df = df.loc[df[date_column].between(start, end + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1))]

    for column, label in (("Colecao", "Coleção"), ("Grupo", "Grupo")):
        selected = st.sidebar.multiselect(label, _options(df, column), key=f"{key_prefix}_{column}")
        if selected:
            df = df.loc[df[column].isin(selected)]

    if include_sector:
        selected = st.sidebar.multiselect("Setor", _options(df, "Setor"), key=f"{key_prefix}_Setor")
        if selected:
            df = df.loc[df["Setor"].isin(selected)]
    if include_faction:
        faction_options = _options(df, "Facção")
        default_factions = [
            faction
            for faction in faction_options
            if faction not in (default_excluded_factions or [])
        ]
        selected = st.sidebar.multiselect(
            "Facção",
            faction_options,
            default=default_factions,
            key=f"{key_prefix}_Faccao",
        )
        if selected:
            df = df.loc[df["Facção"].isin(selected)]
    return df


def monthly_production(df: pd.DataFrame, dimensions: list[str] | None = None) -> pd.DataFrame:
    dimensions = dimensions or []
    work = df.dropna(subset=[DATE_COL]).copy()
    work["Mês"] = work[DATE_COL].dt.to_period("M").dt.to_timestamp()
    return work.groupby(["Mês", *dimensions], dropna=False, as_index=False)[PRODUCTION_COL].sum()


def no_data_message(df: pd.DataFrame) -> bool:
    if df.empty:
        st.warning("Nenhum registro encontrado com os filtros selecionados.")
        return True
    return False


def production_caption() -> None:
    st.caption("Métrica principal de produção: soma de **Qt Aprovada**, usando **Data Saída** como referência temporal.")
