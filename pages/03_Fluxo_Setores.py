import pandas as pd
import streamlit as st
from pathlib import Path
import sys

PAGES_DIR = Path(__file__).resolve().parent
if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from utils.shared import (
    PRODUCTION_COL,
    FLOW_ORDER,
    FLOW_SEQUENCE,
    apply_theme,
    get_movements,
    no_data_message,
    production_caption,
    sidebar_filters,
)
from utils.charts import bar_chart
from utils.display import display_dataframe

st.set_page_config(page_title="Fluxo de Setores | BI", page_icon="🔄", layout="wide")
apply_theme()
st.title("Fluxo entre setores")
production_caption()
st.caption("As transições são inferidas pela ordem de Data Saída dentro da mesma OF, referência e tamanho. Empates de data não permitem estabelecer uma sequência confiável.")

df = sidebar_filters(get_movements(), key_prefix="flow", include_sector=False)
if not no_data_message(df):
    ordered = df.dropna(subset=["OF", "Referência", "Setor", "Data Saída"])
    ordered = ordered.sort_values(["OF", "Referência", "Tamanho", "Data Saída", "CodSetor"])
    ordered = ordered[["OF", "Referência", "Tamanho", "Setor", "Data Saída", PRODUCTION_COL]].copy()
    flow_keys = ["OF", "Referência", "Tamanho"]
    ordered["Próximo setor"] = ordered.groupby(flow_keys, dropna=False)["Setor"].shift(-1)
    ordered["Próxima data"] = ordered.groupby(flow_keys, dropna=False)["Data Saída"].shift(-1)
    transitions = ordered.loc[(ordered["Próximo setor"].notna()) & (ordered["Setor"] != ordered["Próximo setor"])
                              & (ordered["Data Saída"] < ordered["Próxima data"])]

    c1, c2, c3 = st.columns(3)
    c1.metric("Setores movimentados", df["Setor"].nunique())
    c2.metric("Transições identificadas", len(transitions))
    c3.metric("Peças em transições", f"{transitions[PRODUCTION_COL].sum():,.0f}".replace(",", "."))

    if transitions.empty:
        st.info("Não houve transições sequenciais identificáveis com os filtros atuais.")
    else:
        routes = (transitions.groupby(["Setor", "Próximo setor"], as_index=False)
                  .agg(**{"Peças aprovadas": (PRODUCTION_COL, "sum"), "Ocorrências": ("OF", "size")})
                  .sort_values("Peças aprovadas", ascending=False))
        st.subheader("Principais transições")
        display_dataframe(
            routes.head(30),
            labels={"Setor": "Setor atual", "Próximo setor": "Próximo setor", "Peças aprovadas": "Peças aprovadas", "Ocorrências": "Ocorrências"},
            number_formats={"Peças aprovadas": 0, "Ocorrências": 0},
            hide_index=True,
        )

        st.subheader("Matriz de transição")
        matrix = (routes.pivot(index="Setor", columns="Próximo setor", values="Peças aprovadas")
                  .fillna(0))
        unknown_order = len(FLOW_SEQUENCE) + 1
        matrix = matrix.reindex(
            index=sorted(matrix.index, key=lambda value: (FLOW_ORDER.get(str(value), unknown_order), str(value))),
            columns=sorted(matrix.columns, key=lambda value: (FLOW_ORDER.get(str(value), unknown_order), str(value))),
        )
        display_dataframe(
            matrix,
            number_formats={column: 0 for column in matrix.columns},
        )

    st.subheader("Volume por setor")
    sector_volume = df.groupby("Setor")[PRODUCTION_COL].sum().sort_values(ascending=False)
    bar_chart(sector_volume)
