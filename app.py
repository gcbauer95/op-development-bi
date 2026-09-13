import streamlit as st

from data.loader import load_data


st.set_page_config(
    page_title="BI Produção",
    layout="wide",
)


df = load_data("movimentacao")


if df is None:
    st.stop()


st.success(
    f"Dados carregados: {len(df):,} registros"
)


st.dataframe(
    df,
    use_container_width=True,
)
