import pandas as pd
import streamlit as st

from pathlib import Path
import sys

PAGES_DIR = Path(__file__).resolve().parent
if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from _shared import (
    PRODUCTION_COL,
    get_movements,
    monthly_production,
    no_data_message,
    production_caption,
    sidebar_filters,
)

st.set_page_config(page_title="Coleções e Referências | BI", page_icon="🏷️", layout="wide")
st.title("Coleções e referências")
production_caption()

df = sidebar_filters(get_movements(), key_prefix="collections", include_sector=True)
if not no_data_message(df):
    selected_sectors = st.session_state.get("collections_Setor", [])
    production_df = df if len(selected_sectors) == 1 else df.loc[df["Setor"] == "EXPEDIÇÃO"]
    dated = df.dropna(subset=["Data Saída"]).copy()
    dated["Mês"] = dated["Data Saída"].dt.to_period("M").dt.to_timestamp()
    references_by_month = dated.groupby("Mês")["Referência"].nunique()
    total_references = df["Referência"].nunique()
    total_production = df[PRODUCTION_COL].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Referências distintas", f"{total_references:,.0f}".replace(",", "."))
    c2.metric("Peças por referência", f"{(total_production / total_references if total_references else 0):,.1f}".replace(",", "."))
    c3.metric("Coleções", df["Colecao"].nunique())

    st.subheader("Quantidade de referências por mês")
    st.line_chart(references_by_month)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Produção por coleção")
        production_collection = (production_df.groupby("Colecao")[PRODUCTION_COL]
                                 .sum().sort_values(ascending=False))
        st.bar_chart(production_collection.head(20))
    with col2:
        st.subheader("Coleção × grupo")
        collection_group = pd.pivot_table(production_df, index="Colecao", columns="Grupo", values=PRODUCTION_COL, aggfunc="sum", fill_value=0)
        st.dataframe(collection_group, use_container_width=True)

    st.subheader("Ranking e Pareto de referências")
    reference_ranking = (production_df.groupby(["Referência", "Descrição"], dropna=False)
                         .agg(**{"Peças aprovadas": (PRODUCTION_COL, "sum"), "OFs": ("OF", "nunique"), "Coleções": ("Colecao", "nunique")})
                         .sort_values("Peças aprovadas", ascending=False)
                         .reset_index())
    ranking_total = reference_ranking["Peças aprovadas"].sum()
    reference_ranking["% acumulado"] = reference_ranking["Peças aprovadas"].cumsum().div(ranking_total if ranking_total else 1).mul(100)
    st.dataframe(reference_ranking.head(100), use_container_width=True, hide_index=True,
                 column_config={"% acumulado": st.column_config.NumberColumn(format="%.1f%%")})
