import streamlit as st

from data.loader import load_data
from utils.styles import apply_theme
from utils.display import display_dataframe


st.set_page_config(
    page_title="BI Produção",
    layout="wide",
)
apply_theme()


df = load_data("movimentacao", refresh=True)
orders = load_data("ops_geradas", refresh=True)


if df is None or orders is None:
	st.stop()


st.success(
    f"Dados carregados: {len(df):,} movimentações e {len(orders):,} ordens geradas"
)


display_dataframe(
    df,
    labels={
        "OF": "OF",
        "Referência": "Referência",
        "Descrição": "Descrição",
        "Tamanho": "Tamanho",
        "Data Entrada": "Data de entrada",
        "Data Saída": "Data de saída",
        "Prev Saída": "Previsão de saída",
        "Qt OF": "Qt. OF",
        "Qt Aprovada": "Qt. aprovada",
        "CodSetor": "Código do setor",
        "Setor": "Setor",
        "Colecao": "Coleção",
        "Desc_Colecao": "Descrição da coleção",
        "CodFacção": "Código da facção",
        "Facção": "Facção",
        "CodGrupo": "Código do grupo",
        "Grupo": "Grupo",
    },
    number_formats={"Qt OF": 0, "Qt Aprovada": 0, "CodSetor": 0, "CodFacção": 0, "CodGrupo": 0},
    date_formats={"Data Entrada": "DD/MM/YYYY", "Data Saída": "DD/MM/YYYY", "Prev Saída": "DD/MM/YYYY"},
)
