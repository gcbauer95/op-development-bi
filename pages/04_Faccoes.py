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
st.set_page_config(page_title="Facções | BI", page_icon="🧵", layout="wide")
apply_theme()
st.title("Análise de facções")
production_caption()

df = sidebar_filters(
    get_movements(),
    key_prefix="factions",
    include_faction=True,
    default_excluded_factions=["ONCA PRETA DENIM LTDA"],
)
if not no_data_message(df):
    known = df.dropna(subset=["Facção"]).copy()
    total = known[PRODUCTION_COL].sum()
    factions = known["Facção"].nunique()
    c1, c2, c3 = st.columns(3)
    c1.metric("Peças aprovadas em facções", f"{total:,.0f}".replace(",", "."))
    c2.metric("Facções ativas", factions)
    c3.metric("Peças por facção", f"{(total / factions if factions else 0):,.1f}".replace(",", "."))

    ranking = (known.groupby(["CodFacção", "Facção"], dropna=False)
               .agg(**{"Peças aprovadas": (PRODUCTION_COL, "sum"), "OFs": ("OF", "nunique"), "Setores": ("Setor", "nunique"), "Coleções": ("Colecao", "nunique")})
               .sort_values("Peças aprovadas", ascending=False))
    st.subheader("Ranking de facções")
    ranking_chart = ranking.reset_index().head(20)

    bar_chart(
        ranking_chart,
        x="Facção",
        y="Peças aprovadas",
    )
    display_dataframe(
        ranking,
        labels={"CodFacção": "Código da facção", "Facção": "Facção", "Peças aprovadas": "Peças aprovadas", "OFs": "OFs", "Setores": "Setores", "Coleções": "Coleções"},
        number_formats={"CodFacção": 0, "Peças aprovadas": 0, "OFs": 0, "Setores": 0, "Coleções": 0},
    )

    st.subheader("Facção × setor")
    faction_sector = pd.pivot_table(known, index="Facção", columns="Setor", values=PRODUCTION_COL, aggfunc="sum", fill_value=0)
    faction_sector = faction_sector.rename_axis("Facção")
    faction_sector = faction_sector.loc[
        faction_sector.sum(axis=1).sort_values(ascending=False).index
    ]
    display_dataframe(
        faction_sector,
        number_formats={column: 0 for column in faction_sector.columns},
    )

    st.subheader("Evolução mensal das principais facções")
    monthly = monthly_production(known, ["Facção"])
    top = monthly.groupby("Facção")[PRODUCTION_COL].sum().nlargest(12).index
    chart = monthly.loc[monthly["Facção"].isin(top)].pivot(index="Mês", columns="Facção", values=PRODUCTION_COL).fillna(0)
    line_chart(chart, height=420)
