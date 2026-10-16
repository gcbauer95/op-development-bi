"""Visão de estoque pronta-entrega da coleção AV27."""

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

PAGES_DIR = Path(__file__).resolve().parent
if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from data.loader import load_data  # noqa: E402
from utils.charts import bar_chart  # noqa: E402
from utils.display import display_dataframe, format_br_number  # noqa: E402
from utils.shared import apply_theme  # noqa: E402


st.set_page_config(page_title="Estoque AV27 | PPCP", page_icon="📦", layout="wide")
apply_theme()
st.title("Estoque pronta-entrega — AV27")
st.caption("Disponibilidade por referência, grade, cor e SKU para apoiar decisões comerciais e de planejamento.")

stock = load_data("estoque_av27")
orders = load_data("pedidos_venda")
order_items = load_data("pedidos_itens")
if stock is None:
    st.info("Envie o Parquet gerado pelo etl-estoque.py para carregar a posição de estoque.")
    st.stop()

stock = stock.copy()
stock["estoque_pronta_entrega"] = pd.to_numeric(stock["estoque_pronta_entrega"], errors="coerce").fillna(0)
stock["ordem_grade"] = pd.to_numeric(stock["ordem_grade"], errors="coerce")

st.sidebar.header("Filtros de estoque")
selected_references = st.sidebar.multiselect("Referência", sorted(stock["referencia"].dropna().unique().tolist()))
selected_grades = st.sidebar.multiselect("Grade", sorted(stock["grade"].dropna().unique().tolist()))
selected_colors = st.sidebar.multiselect("Cor", sorted(stock["cor"].dropna().unique().tolist()))
only_available = st.sidebar.checkbox("Mostrar somente SKUs com estoque", value=False)

filtered = stock.copy()
if selected_references:
    filtered = filtered.loc[filtered["referencia"].isin(selected_references)]
if selected_grades:
    filtered = filtered.loc[filtered["grade"].isin(selected_grades)]
if selected_colors:
    filtered = filtered.loc[filtered["cor"].isin(selected_colors)]
if only_available:
    filtered = filtered.loc[filtered["estoque_pronta_entrega"] > 0]

if filtered.empty:
    st.warning("Nenhum SKU encontrado com os filtros selecionados.")
    st.stop()

total_stock = filtered["estoque_pronta_entrega"].sum()
total_skus = filtered["sku"].nunique()
available_skus = filtered.loc[filtered["estoque_pronta_entrega"] > 0, "sku"].nunique()
zero_skus = total_skus - available_skus

c1, c2, c3, c4 = st.columns(4)
c1.metric("Peças em estoque pronta-entrega", format_br_number(total_stock), help="Quantidade total de peças disponíveis para pronta-entrega.")
c2.metric("SKUs", format_br_number(total_skus), help="SKU é a combinação única de referência | grade | cor.")
c3.metric("SKUs disponíveis", format_br_number(available_skus), help="Combinações únicas de referência | grade | cor com pelo menos uma peça em estoque.")
c4.metric("SKUs sem estoque", format_br_number(zero_skus), help="Combinações únicas de referência | grade | cor sem nenhuma peça em estoque.")

st.subheader("Estoque por referência")
stock_reference = (
    filtered.groupby("referencia", as_index=False)
    .agg(ESTOQUE=("estoque_pronta_entrega", "sum"))
    .sort_values("ESTOQUE", ascending=False)
)
bar_chart(stock_reference.head(25), x="referencia", y="ESTOQUE", y_title="Peças")

st.subheader("Saldo devedor por referência")

if orders is None or order_items is None:
    st.info(
        "Envie também os Parquets de pedidos para calcular "
        "o saldo devedor por referência."
    )
else:
    orders_work = orders.copy()
    items_work = order_items.copy()

    orders_work["codpedido"] = pd.to_numeric(
        orders_work["codpedido"],
        errors="coerce",
    ).astype("Int64")

    items_work["codpedido"] = pd.to_numeric(
        items_work["codpedido"],
        errors="coerce",
    ).astype("Int64")

    orders_work["situacaopedido"] = (
        orders_work["situacaopedido"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    orders_work["bloq_fin"] = (
        orders_work["bloq_fin"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    items_work["referencia"] = (
        items_work["referencia"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    items_work["grade"] = (
        items_work["grade"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    items_work["cor"] = (
        items_work["cor"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    items_work["qtdepedida"] = pd.to_numeric(
        items_work["qtdepedida"],
        errors="coerce",
    ).fillna(0)

    items_work["qtdefaturado"] = pd.to_numeric(
        items_work["qtdefaturado"],
        errors="coerce",
    ).fillna(0)

    open_statuses = ["EM ANALISE", "PARCIAL"]

    released_order_ids = (
        orders_work.loc[
            orders_work["situacaopedido"].isin(open_statuses)
            & orders_work["bloq_fin"].ne("BLOQUEADO"),
            "codpedido",
        ]
        .dropna()
        .unique()
    )

    demand = items_work.loc[
        items_work["codpedido"].isin(released_order_ids)
    ].copy()

    if selected_references:
        demand = demand.loc[
            demand["referencia"].isin(selected_references)
        ]

    if selected_grades:
        demand = demand.loc[
            demand["grade"].isin(selected_grades)
        ]

    if selected_colors:
        demand = demand.loc[
            demand["cor"].isin(selected_colors)
        ]

    demand["QTD_PENDENTE"] = (
        demand["qtdepedida"]
        - demand["qtdefaturado"]
    ).clip(lower=0)

    demand_reference = (
        demand.groupby("referencia", as_index=False)
        .agg(
            PEDIDO_PENDENTE=("QTD_PENDENTE", "sum")
        )
    )

    debt_reference = stock_reference.merge(
        demand_reference,
        on="referencia",
        how="outer",
    )

    debt_reference["ESTOQUE"] = pd.to_numeric(
        debt_reference["ESTOQUE"],
        errors="coerce",
    ).fillna(0)

    debt_reference["PEDIDO_PENDENTE"] = pd.to_numeric(
        debt_reference["PEDIDO_PENDENTE"],
        errors="coerce",
    ).fillna(0)

    debt_reference["SALDO_DEVEDOR"] = (
        debt_reference["PEDIDO_PENDENTE"]
        - debt_reference["ESTOQUE"]
    )

    debt_reference = (
        debt_reference.loc[
            debt_reference["SALDO_DEVEDOR"] > 0
        ]
        .sort_values(
            "SALDO_DEVEDOR",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    st.caption(
        "Considera apenas pedidos em aberto e liberados pelo financeiro. "
        "Saldo devedor = quantidade pendente do pedido − estoque pronta-entrega."
    )

    if debt_reference.empty:
        st.success(
            "Não existem referências com saldo devedor "
            "considerando os pedidos liberados pelo financeiro."
        )
    else:
        bar_chart(
            debt_reference.head(25),
            x="referencia",
            y="SALDO_DEVEDOR",
            y_title="Peças faltantes",
        )

        display_dataframe(
            debt_reference,
            labels={
                "referencia": "Referência",
                "PEDIDO_PENDENTE": "Pedido pendente",
                "ESTOQUE": "Estoque",
                "SALDO_DEVEDOR": "Saldo devedor",
            },
            number_formats={
                "PEDIDO_PENDENTE": 0,
                "ESTOQUE": 0,
                "SALDO_DEVEDOR": 0,
            },
            hide_index=True,
        )

st.subheader("Disponibilidade por referência")
reference_summary = (
    filtered.groupby("referencia", as_index=False)
    .agg(
        ESTOQUE=("estoque_pronta_entrega", "sum"),
        SKUS=("sku", "nunique"),
        SKUS_DISPONIVEIS=("estoque_pronta_entrega", lambda values: (values > 0).sum()),
        CORES=("cor", "nunique"),
        GRADES=("grade", "nunique"),
    )
    .sort_values("ESTOQUE", ascending=False)
)
reference_summary["DISPONIBILIDADE"] = reference_summary["SKUS_DISPONIVEIS"].div(reference_summary["SKUS"].replace(0, pd.NA)).mul(100).fillna(0)
display_dataframe(
    reference_summary,
    labels={"referencia": "Referência", "ESTOQUE": "Estoque", "SKUS": "SKUs", "SKUS_DISPONIVEIS": "SKUs disponíveis", "CORES": "Cores", "GRADES": "Grades", "DISPONIBILIDADE": "Disponibilidade"},
    number_formats={"ESTOQUE": 0, "SKUS": 0, "SKUS_DISPONIVEIS": 0, "CORES": 0, "GRADES": 0},
    percent_formats={"DISPONIBILIDADE": 1},
    hide_index=True,
)

st.subheader("Detalhamento por SKU")
sku_detail = filtered.sort_values(["referencia", "cor", "ordem_grade"], ascending=[True, True, True])
display_dataframe(
    sku_detail,
    labels={"colecao": "Coleção", "referencia": "Referência", "grade": "Grade", "cor": "Cor", "estoque_pronta_entrega": "Estoque pronta-entrega", "ordem_grade": "Ordem da grade", "sku": "SKU"},
    number_formats={"estoque_pronta_entrega": 0, "ordem_grade": 0},
    hide_index=True,
)
