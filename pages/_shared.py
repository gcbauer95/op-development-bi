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
ORDER_TYPE_DESC_COL = "Desc. Tipo OP"


def _normalize_order_dimension(orders: pd.DataFrame) -> pd.DataFrame | None:
    """Valida e reduz a base de ordens a uma classificação única por OF."""
    work = orders[["OF", "Tipo OP", ORDER_TYPE_DESC_COL]].copy()
    work["OF"] = work["OF"].astype("string").str.strip()
    work["Tipo OP"] = pd.to_numeric(work["Tipo OP"], errors="coerce").astype("Int64").astype("string")
    work[ORDER_TYPE_DESC_COL] = work[ORDER_TYPE_DESC_COL].astype("string").str.strip()

    conflicts = (
        work.assign(
            _type_key=work["Tipo OP"].fillna("<SEM>"),
            _desc_key=work[ORDER_TYPE_DESC_COL].fillna("<SEM>"),
        )
        .groupby("OF", dropna=False)
        .agg(_types=("_type_key", "nunique"), _descriptions=("_desc_key", "nunique"))
    )
    conflicts = conflicts.loc[(conflicts["_types"] > 1) | (conflicts["_descriptions"] > 1)]
    if not conflicts.empty:
        st.error(
            "A base de ordens geradas possui classificações conflitantes para uma mesma OF. "
            f"OFs afetadas: {', '.join(conflicts.index.astype('string').tolist()[:10])}."
        )
        return None

    return work.drop_duplicates("OF", keep="first")


def get_movements() -> pd.DataFrame | None:
    """Carrega, padroniza e enriquece movimentos com a classificação da OF."""
    movements = load_data("movimentacao")
    orders = load_data("ops_geradas")
    if movements is None or orders is None:
        return None

    order_dimension = _normalize_order_dimension(orders)
    if order_dimension is None:
        return None

    df = movements.copy()
    df["OF"] = df["OF"].astype("string").str.strip()
    try:
        df = df.merge(order_dimension, on="OF", how="left", validate="many_to_one")
    except (KeyError, pd.errors.MergeError) as error:
        st.error(f"Não foi possível relacionar as bases de movimentação e ordens: {error}")
        return None

    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df["Data Entrada"] = pd.to_datetime(df["Data Entrada"], errors="coerce")
    df[PRODUCTION_COL] = pd.to_numeric(df[PRODUCTION_COL], errors="coerce").fillna(0)
    df["Qt OF"] = pd.to_numeric(df["Qt OF"], errors="coerce").fillna(0)
    df[ORDER_TYPE_DESC_COL] = df[ORDER_TYPE_DESC_COL].fillna("SEM CLASSIFICAÇÃO")
    df["Mês"] = df[DATE_COL].dt.to_period("M").astype("string")
    st.session_state["data_movimentacao_enriched"] = df
    return df


def _options(df: pd.DataFrame, column: str) -> list:
    return sorted(df[column].dropna().unique().tolist(), key=lambda value: str(value))

def get_orders() -> pd.DataFrame | None:
    orders = load_data("ops_geradas")

    if orders is None:
        return None

    df = orders.copy()

    df["OF"] = df["OF"].astype("string").str.strip()

    for column in [
        "Emissão",
        "Data Setor",
        "Prev. Término",
    ]:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce",
        )

    for column in [
        "Qt Orig.",
        "Qt Aprovada",
        "Qt Pend.",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    return df


def sidebar_filters(
    df: pd.DataFrame | None,
    *,
    key_prefix: str,
    include_sector: bool = True,
    include_faction: bool = False,
    default_excluded_factions: list[str] | None = None,
    date_column: str = DATE_COL,
) -> pd.DataFrame:
    """Aplica filtros globais sem criar cópias até o final."""
    if df is None:
        return pd.DataFrame()
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

    if ORDER_TYPE_DESC_COL in df.columns:
        selected = st.sidebar.multiselect(
            "Tipo OP",
            _options(df, ORDER_TYPE_DESC_COL),
            key=f"{key_prefix}_TipoOP",
        )
        if selected:
            df = df.loc[df[ORDER_TYPE_DESC_COL].isin(selected)]

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
