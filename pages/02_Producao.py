import pandas as pd
import streamlit as st

from pathlib import Path
import sys

PAGES_DIR = Path(__file__).resolve().parent
if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from utils.shared import (
    PRODUCTION_COL,
    apply_theme,
    get_movements,
    monthly_production,
    no_data_message,
    production_caption,
    sidebar_filters,
)
from utils.charts import bar_chart, line_chart
from utils.display import display_dataframe

st.set_page_config(page_title="Produção | BI", page_icon="🏭", layout="wide")
apply_theme()
st.title("Produção por mês e setor")
production_caption()

df = sidebar_filters(get_movements(), key_prefix="production")
if not no_data_message(df):
    selected_sectors = st.session_state.get("production_Setor", [])
    production_df = df if len(selected_sectors) == 1 else df.loc[df["Setor"] == "EXPEDIÇÃO"]
    months_sectors = monthly_production(df, ["Setor"])
    sectors = months_sectors.groupby("Setor")[PRODUCTION_COL].sum().nlargest(12).index
    chart_data = (months_sectors.loc[months_sectors["Setor"].isin(sectors)]
                  .pivot(index="Mês", columns="Setor", values=PRODUCTION_COL).fillna(0))
    st.subheader("Produção mensal por setor")
    st.caption("Exibe os 12 setores com maior volume no período filtrado.")
    line_chart(chart_data, height=420)

    st.subheader("Matriz mês × setor")
    matrix = (months_sectors.pivot(index="Mês", columns="Setor", values=PRODUCTION_COL)
              .fillna(0).sort_index())
    display_dataframe(
        matrix,
        labels={column: str(column) for column in matrix.columns},
        number_formats={column: 0 for column in matrix.columns},
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Produção por coleção")
        collection = (production_df.groupby("Colecao", dropna=False)[PRODUCTION_COL]
                      .sum().sort_values(ascending=False))
        bar_chart(collection.head(20))
    with col2:
        st.subheader("Produção por grupo")
        group = (production_df.groupby("Grupo", dropna=False)[PRODUCTION_COL]
                 .sum().sort_values(ascending=False))
        bar_chart(group.head(20))

    st.subheader("Detalhamento mensal")
    detail = (months_sectors.rename(columns={PRODUCTION_COL: "Peças aprovadas"})
              .sort_values(["Mês", "Peças aprovadas"], ascending=[False, False]))
    detail["Mês"] = pd.to_datetime(detail["Mês"]).dt.strftime("%m/%Y")
    display_dataframe(
        detail,
        labels={"Mês": "Mês", "Setor": "Setor", "Peças aprovadas": "Peças aprovadas"},
        number_formats={"Peças aprovadas": 0},
        hide_index=True,
    )
