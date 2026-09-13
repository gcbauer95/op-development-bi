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

st.set_page_config(page_title="Produção | BI", page_icon="🏭", layout="wide")
st.title("Produção por mês e setor")
production_caption()

df = sidebar_filters(get_movements(), key_prefix="production")
if not no_data_message(df):
    months_sectors = monthly_production(df, ["Setor"])
    sectors = months_sectors.groupby("Setor")[PRODUCTION_COL].sum().nlargest(12).index
    chart_data = (months_sectors.loc[months_sectors["Setor"].isin(sectors)]
                  .pivot(index="Mês", columns="Setor", values=PRODUCTION_COL).fillna(0))
    st.subheader("Produção mensal por setor")
    st.caption("Exibe os 12 setores com maior volume no período filtrado.")
    st.line_chart(chart_data)

    st.subheader("Matriz mês × setor")
    matrix = (months_sectors.pivot(index="Mês", columns="Setor", values=PRODUCTION_COL)
              .fillna(0).sort_index())
    st.dataframe(matrix.style.format("{0:,.0f}"), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Produção por coleção")
        collection = df.groupby("Colecao", dropna=False)[PRODUCTION_COL].sum().sort_values(ascending=False)
        st.bar_chart(collection.head(20))
    with col2:
        st.subheader("Produção por grupo")
        group = df.groupby("Grupo", dropna=False)[PRODUCTION_COL].sum().sort_values(ascending=False)
        st.bar_chart(group.head(20))

    st.subheader("Detalhamento mensal")
    detail = (months_sectors.rename(columns={PRODUCTION_COL: "Peças aprovadas"})
              .sort_values(["Mês", "Peças aprovadas"], ascending=[False, False]))
    detail["Mês"] = pd.to_datetime(detail["Mês"]).dt.strftime("%m/%Y")
    st.dataframe(detail, use_container_width=True, hide_index=True)
