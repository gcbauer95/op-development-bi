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

st.set_page_config(page_title="Visão Geral | Produção", page_icon="📊", layout="wide")
st.title("Visão geral da produção")
production_caption()

df = sidebar_filters(get_movements(), key_prefix="overview", include_faction=True)
if not no_data_message(df):
    selected_sectors = st.session_state.get("overview_Setor", [])
    is_single_sector = len(selected_sectors) == 1
    if is_single_sector:
        total = df[PRODUCTION_COL].sum()
        total_label = "Peças aprovadas"
        production_df = df
    else:
        production_df = df.loc[df["Setor"] == "EXPEDIÇÃO"]
        total = production_df[PRODUCTION_COL].sum()
        total_label = "Total produzido (Expedição)"
    orders = df["OF"].nunique()
    references = df["Referência"].nunique()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(total_label, f"{total:,.0f}".replace(",", "."))
    c2.metric("OFs", f"{orders:,.0f}".replace(",", "."))
    c3.metric("Referências", f"{references:,.0f}".replace(",", "."))
    c4.metric("Peças por referência", f"{(total / references if references else 0):,.1f}".replace(",", "."))

    monthly = monthly_production(production_df).set_index("Mês")
    st.subheader("Evolução mensal")
    st.line_chart(monthly[PRODUCTION_COL])

    left, right = st.columns(2)
    with left:
        st.subheader("Produção por setor")
        by_sector = df.groupby("Setor", dropna=False)[PRODUCTION_COL].sum().sort_values(ascending=False).head(15)
        st.bar_chart(by_sector)
    with right:
        st.subheader("Produção por coleção")
        by_collection = (production_df.groupby("Colecao", dropna=False)[PRODUCTION_COL]
                         .sum().sort_values(ascending=False).head(15))
        st.bar_chart(by_collection)

    st.subheader("Resumo por grupo")
    summary = (production_df.groupby("Grupo", dropna=False)
               .agg(**{"Peças aprovadas": (PRODUCTION_COL, "sum"), "OFs": ("OF", "nunique"), "Referências": ("Referência", "nunique")})
               .sort_values("Peças aprovadas", ascending=False))
    st.dataframe(summary, use_container_width=True)
