import streamlit as st

from pathlib import Path
import sys

PAGES_DIR = Path(__file__).resolve().parent
if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from utils.shared import (
    PRODUCTION_COL,
    FLOW_ORDER,
    apply_theme,
    get_movements,
    monthly_production,
    no_data_message,
    production_caption,
    sidebar_filters,
)
from utils.charts import bar_chart, line_chart
from utils.display import display_dataframe

st.set_page_config(page_title="Visão Geral | Produção", page_icon="📊", layout="wide")
apply_theme()
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
    line_chart(monthly[PRODUCTION_COL])

    left, right = st.columns(2)
    with left:
        st.subheader("Produção por setor")
        by_sector = df.groupby("Setor", dropna=False)[PRODUCTION_COL].sum().nlargest(15).to_frame()
        by_sector["_ordem_fluxo"] = by_sector.index.map(FLOW_ORDER).fillna(len(FLOW_ORDER) + 1)
        by_sector = by_sector.assign(_setor=by_sector.index.astype("string")) \
            .sort_values(["_ordem_fluxo", "_setor"]) \
            .drop(columns=["_ordem_fluxo", "_setor"])[PRODUCTION_COL]
        bar_chart(by_sector)
    with right:
        st.subheader("Produção por coleção")
        by_collection = (production_df.groupby("Colecao", dropna=False)[PRODUCTION_COL]
                         .sum().sort_values(ascending=False).head(15))
        bar_chart(by_collection)

    st.subheader("Resumo por grupo")
    summary = (production_df.groupby("Grupo", dropna=False)
               .agg(**{"Peças aprovadas": (PRODUCTION_COL, "sum"), "OFs": ("OF", "nunique"), "Referências": ("Referência", "nunique")})
               .sort_values("Peças aprovadas", ascending=False))
    display_dataframe(
        summary,
        labels={"Peças aprovadas": "Peças aprovadas", "OFs": "OFs", "Referências": "Referências"},
        number_formats={"Peças aprovadas": 0, "OFs": 0, "Referências": 0},
    )
