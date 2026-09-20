import streamlit as st

from data.loader import load_data


st.set_page_config(
    page_title="BI Produção",
    layout="wide",
)


df = load_data("movimentacao", refresh=True)
orders = load_data("ops_geradas", refresh=True)


if df is None or orders is None:
	st.stop()


st.success(
    f"Dados carregados: {len(df):,} movimentações e {len(orders):,} ordens geradas"
)


st.dataframe(
    df,
    use_container_width=True,
)
