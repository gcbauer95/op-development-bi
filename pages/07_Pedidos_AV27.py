"""Visão comercial dos pedidos vendidos por coleção."""

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

PAGES_DIR = Path(__file__).resolve().parent
if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from utils.charts import bar_chart, line_chart  # noqa: E402
from utils.display import display_dataframe, format_br_number  # noqa: E402
from utils.shared import apply_theme  # noqa: E402
from data.loader import load_data  # noqa: E402


st.set_page_config(
    page_title="Pedidos | PPCP",
    page_icon="🧾",
    layout="wide",
)

apply_theme()

st.title("Pedidos vendidos")
st.caption(
    "Acompanhamento de pedidos, SKUs, vendas por data, "
    "coleções e bloqueios financeiros."
)


# ============================================================
# CARREGAMENTO DOS DADOS
# ============================================================

orders = load_data("pedidos_venda")
items = load_data("pedidos_itens")

if orders is None or items is None:
    st.info(
        "Envie os dois arquivos Parquet processados "
        "para carregar a visão de pedidos."
    )
    st.stop()


# ============================================================
# PREPARAÇÃO DOS DADOS
# ============================================================

orders = orders.copy()
items = items.copy()

orders["codcolecao"] = (
    orders["codcolecao"]
    .astype("string")
    .str.strip()
)

orders["dataemissao"] = pd.to_datetime(
    orders["dataemissao"],
    errors="coerce",
)

orders["dataprevfaturamento"] = pd.to_datetime(
    orders["dataprevfaturamento"],
    errors="coerce",
)

orders["quantidade"] = pd.to_numeric(
    orders["quantidade"],
    errors="coerce",
).fillna(0)

orders["codpedido"] = pd.to_numeric(
    orders["codpedido"],
    errors="coerce",
).astype("Int64")

orders["codcliente"] = pd.to_numeric(
    orders["codcliente"],
    errors="coerce",
).astype("Int64")

items["codpedido"] = pd.to_numeric(
    items["codpedido"],
    errors="coerce",
).astype("Int64")


# ============================================================
# OPÇÕES DOS FILTROS
# ============================================================

open_statuses = [
    "EM ANALISE",
    "PARCIAL",
]

collection_options = sorted(
    orders["codcolecao"]
    .dropna()
    .unique()
    .tolist()
)

status_options = sorted(
    orders["situacaopedido"]
    .dropna()
    .unique()
    .tolist()
)

finance_options = sorted(
    orders["bloq_fin"]
    .dropna()
    .unique()
    .tolist()
)

reference_options = sorted(
    orders["codproduto"]
    .dropna()
    .unique()
    .tolist()
)


# ============================================================
# FILTROS DA SIDEBAR
# ============================================================

st.sidebar.header("Filtros de pedidos")

selected_collections = st.sidebar.multiselect(
    "Coleção",
    collection_options,
    placeholder="Todas as coleções",
)

selected_status = st.sidebar.multiselect(
    "Situação do pedido",
    status_options,
    default=[
        status
        for status in open_statuses
        if status in status_options
    ],
)

exclude_customer_onca = st.sidebar.checkbox(
    "Desconsiderar cliente ONCA PRETA DENIM LTDA",
    value=True,
    help=(
        "Remove o cliente ONCA PRETA DENIM LTDA "
        "(codcliente = 1) dos indicadores, gráficos e tabelas."
    ),
)

selected_finance = st.sidebar.multiselect(
    "Bloqueio financeiro",
    finance_options,
)

selected_references = st.sidebar.multiselect(
    "Referência",
    reference_options,
)


# ============================================================
# FILTRO DE DATA
# ============================================================

valid_dates = orders["dataemissao"].dropna()

if not valid_dates.empty:
    selected_dates = st.sidebar.date_input(
        "Período de emissão",
        value=(
            valid_dates.min().date(),
            valid_dates.max().date(),
        ),
        min_value=valid_dates.min().date(),
        max_value=valid_dates.max().date(),
        format="DD/MM/YYYY",
    )
else:
    selected_dates = ()


# ============================================================
# APLICAÇÃO DOS FILTROS
# ============================================================

filtered = orders.copy()

if selected_collections:
    filtered = filtered.loc[
        filtered["codcolecao"].isin(selected_collections)
    ]

if exclude_customer_onca:
    customer_code = (
        filtered["codcliente"]
        .astype("string")
        .str.strip()
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
    )

    filtered = filtered.loc[
        customer_code.ne("1")
    ]

if selected_status:
    filtered = filtered.loc[
        filtered["situacaopedido"].isin(selected_status)
    ]

if selected_finance:
    filtered = filtered.loc[
        filtered["bloq_fin"].isin(selected_finance)
    ]

if selected_references:
    filtered = filtered.loc[
        filtered["codproduto"].isin(selected_references)
    ]

if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start = pd.Timestamp(selected_dates[0])
    end = pd.Timestamp(selected_dates[1])

    filtered = filtered.loc[
        filtered["dataemissao"].between(
            start,
            end
            + pd.Timedelta(days=1)
            - pd.Timedelta(nanoseconds=1),
        )
    ]


# ============================================================
# VALIDAÇÃO DO RESULTADO
# ============================================================

if filtered.empty:
    st.warning(
        "Nenhum pedido encontrado com os filtros selecionados."
    )
    st.stop()


# ============================================================
# INFORMAÇÕES SOBRE FILTROS ATIVOS
# ============================================================

if selected_collections:
    collections_text = ", ".join(
        str(collection)
        for collection in selected_collections
    )

    st.caption(
        f"Coleção selecionada: {collections_text}"
        if len(selected_collections) == 1
        else f"Coleções selecionadas: {collections_text}"
    )

if exclude_customer_onca:
    excluded_rows = len(orders) - len(
        orders.loc[
            ~(
                orders["codcliente"]
                .astype("string")
                .str.strip()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True,
                )
                .eq("1")
            )
        ]
    )

    st.caption(
        (
            "Filtro ativo: cliente ONCA PRETA DENIM LTDA "
            f"(código 1) desconsiderado "
            f"({excluded_rows:,.0f} linhas removidas)."
        ).replace(",", ".")
    )


# ============================================================
# FILTRAGEM DOS ITENS
# ============================================================

# Mantém exatamente os mesmos pares pedido + referência que
# estão na base filtrada.
#
# Filtrar apenas pelo pedido incluiria itens de outras
# situações ou referências do mesmo pedido e quebraria
# a conciliação financeira.

filtered_pairs = (
    filtered[
        [
            "codpedido",
            "codproduto",
        ]
    ]
    .drop_duplicates()
    .rename(
        columns={
            "codproduto": "referencia",
        }
    )
)

filtered_items = items.merge(
    filtered_pairs,
    on=[
        "codpedido",
        "referencia",
    ],
    how="inner",
)


# ============================================================
# SALDO EM ABERTO DOS ITENS
# ============================================================

# Para indicadores de quantidade em aberto, deve ser utilizado:
#
# saldo aberto = quantidade pedida - quantidade faturada
#
# O cálculo é realizado no nível dos itens/SKUs.

filtered_items["qtdepedida"] = pd.to_numeric(
    filtered_items["qtdepedida"],
    errors="coerce",
).fillna(0)

filtered_items["qtdefaturado"] = pd.to_numeric(
    filtered_items["qtdefaturado"],
    errors="coerce",
).fillna(0)

filtered_items["saldo_aberto"] = (
    filtered_items["qtdepedida"]
    - filtered_items["qtdefaturado"]
).clip(lower=0)


# Consolida o saldo por pedido + referência para relacionar
# novamente com a base principal de pedidos.

open_quantity_by_reference = (
    filtered_items.groupby(
        [
            "codpedido",
            "referencia",
        ],
        as_index=False,
    )
    .agg(
        quantidade_aberta=(
            "saldo_aberto",
            "sum",
        )
    )
)


# ============================================================
# UNIDADE DE ANÁLISE
# ============================================================

analysis_unit = st.radio(
    "Unidade dos indicadores e do gráfico",
    [
        "Quantidade",
        "Valor (R$)",
    ],
    horizontal=True,
    help=(
        "Alterna a unidade exibida no total diário, "
        "nos indicadores e no gráfico."
    ),
)


# ============================================================
# VALOR FINANCEIRO POR PEDIDO / REFERÊNCIA
# ============================================================

item_values = (
    items.groupby(
        [
            "codpedido",
            "referencia",
        ],
        as_index=False,
    )["valor_total_pedido"]
    .sum()
    .rename(
        columns={
            "valor_total_pedido": "valor_venda",
        }
    )
)

chart_base = filtered.merge(
    item_values,
    left_on=[
        "codpedido",
        "codproduto",
    ],
    right_on=[
        "codpedido",
        "referencia",
    ],
    how="left",
)

chart_base["valor_venda"] = (
    chart_base["valor_venda"]
    .fillna(0)
)

metric_column = (
    "quantidade"
    if analysis_unit == "Quantidade"
    else "valor_venda"
)

metric_title = (
    "Quantidade"
    if analysis_unit == "Quantidade"
    else "Valor (R$)"
)

metric_decimals = (
    0
    if analysis_unit == "Quantidade"
    else 2
)

metric_prefix = (
    ""
    if analysis_unit == "Quantidade"
    else "R$ "
)


# ============================================================
# PEDIDOS EM ABERTO / BLOQUEADOS
# ============================================================

open_orders = filtered.loc[
    filtered["situacaopedido"].isin(
        open_statuses
    )
].copy()

blocked_orders = filtered.loc[
    filtered["bloq_fin"].eq(
        "BLOQUEADO"
    )
]


# ============================================================
# SALDO DOS PEDIDOS EM ABERTO
# ============================================================

# Relaciona o saldo calculado nos itens com os pedidos que
# possuem situação EM ANALISE ou PARCIAL.

open_orders = open_orders.merge(
    open_quantity_by_reference,
    left_on=[
        "codpedido",
        "codproduto",
    ],
    right_on=[
        "codpedido",
        "referencia",
    ],
    how="left",
)

open_orders["quantidade_aberta"] = (
    open_orders["quantidade_aberta"]
    .fillna(0)
)


# Valor financeiro permanece utilizando a lógica já existente.
open_value = chart_base.loc[
    chart_base["situacaopedido"].isin(
        open_statuses
    ),
    "valor_venda",
].sum()


# Quando a análise for por quantidade, utiliza o saldo:
#
# qtdepedida - qtdefaturado
#
# Quando for por valor, mantém o cálculo financeiro existente.

open_metric = (
    open_orders["quantidade_aberta"].sum()
    if analysis_unit == "Quantidade"
    else open_value
)


# ============================================================
# INDICADORES
# ============================================================

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Pedidos em aberto",
    format_br_number(
        open_orders["codpedido"].nunique()
    ),
)

c2.metric(
    "SKUs em aberto",
    format_br_number(
        filtered_items.loc[
            filtered_items["saldo_aberto"].gt(0),
            "sku",
        ].nunique()
    ),
)

c3.metric(
    f"{metric_title} em aberto",
    (
        f"{metric_prefix}"
        f"{format_br_number(open_metric, metric_decimals)}"
    ),
)

c4.metric(
    "Pedidos bloqueados no financeiro",
    format_br_number(
        blocked_orders["codpedido"].nunique()
    ),
)


# ============================================================
# PEDIDOS EM ABERTO POR COLEÇÃO
# ============================================================

st.subheader("Pedidos em aberto por coleção")

open_collection = (
    open_orders.groupby(
        [
            "codcolecao",
            "situacaopedido",
        ],
        as_index=False,
    )
    .agg(
        PEDIDOS=(
            "codpedido",
            "nunique",
        ),
        QUANTIDADE=(
            "quantidade_aberta",
            "sum",
        ),
    )
    .sort_values(
        [
            "codcolecao",
            "QUANTIDADE",
        ],
        ascending=[
            True,
            False,
        ],
    )
)

display_dataframe(
    open_collection,
    labels={
        "codcolecao": "Coleção",
        "situacaopedido": "Situação",
        "PEDIDOS": "Pedidos",
        "QUANTIDADE": "Quantidade em aberto",
    },
    number_formats={
        "PEDIDOS": 0,
        "QUANTIDADE": 0,
    },
    hide_index=True,
)


# ============================================================
# VENDA POR DIA E REFERÊNCIA
# ============================================================

st.subheader("Venda por dia e referência")

# Este gráfico representa a venda original.
# Por isso, permanece utilizando a quantidade vendida
# registrada no cabeçalho do pedido.

top_references = (
    chart_base.groupby(
        "codproduto"
    )[metric_column]
    .sum()
    .nlargest(8)
    .index
    .tolist()
)

chart_references = (
    selected_references
    or top_references
)

daily_reference = (
    chart_base.loc[
        chart_base["codproduto"].isin(
            chart_references
        )
    ]
    .groupby(
        [
            "dataemissao",
            "codproduto",
        ],
        as_index=False,
    )[metric_column]
    .sum()
    .pivot(
        index="dataemissao",
        columns="codproduto",
        values=metric_column,
    )
    .fillna(0)
    .sort_index()
)

daily_reference = daily_reference.rename_axis(
    "Data"
)

daily_reference["Total do dia"] = (
    chart_base.groupby(
        "dataemissao"
    )[metric_column]
    .sum()
    .reindex(
        daily_reference.index
    )
    .fillna(0)
)

line_chart(
    daily_reference,
    height=430,
    y_title=metric_title,
    value_decimals=metric_decimals,
    value_prefix=metric_prefix,
)

st.caption(
    f"Unidade exibida: {analysis_unit}. "
    "Sem referências selecionadas, o gráfico mostra "
    "as oito referências com maior valor no período."
)


# ============================================================
# FILTRO POR DIA ESPECÍFICO
# ============================================================

selected_day_text = st.text_input(
    "Dia específico da emissão",
    placeholder="DD/MM/AAAA",
    help=(
        "Opcional. Digite um dia para detalhar somente "
        "os pedidos emitidos nessa data."
    ),
)

daily_filtered = filtered.copy()

if selected_day_text.strip():
    selected_day = pd.to_datetime(
        selected_day_text.strip(),
        dayfirst=True,
        errors="coerce",
    )

    if pd.isna(selected_day):
        st.error(
            "Informe o dia no formato DD/MM/AAAA."
        )
    else:
        daily_filtered = daily_filtered.loc[
            daily_filtered["dataemissao"]
            .dt.date
            .eq(selected_day.date())
        ]


# ============================================================
# PEDIDOS DETALHADOS
# ============================================================

st.subheader(
    "Pedidos detalhados por dia de emissão"
)

daily_orders = (
    daily_filtered.sort_values(
        [
            "dataemissao",
            "codpedido",
            "codproduto",
        ],
        ascending=[
            False,
            True,
            True,
        ],
    )[
        [
            "dataemissao",
            "codpedido",
            "nomecliente",
            "codproduto",
            "quantidade",
            "situacaopedido",
            "bloq_fin",
            "dataprevfaturamento",
        ]
    ]
)

display_dataframe(
    daily_orders.head(500),
    labels={
        "dataemissao": "Data de emissão",
        "codpedido": "Pedido",
        "nomecliente": "Cliente",
        "codproduto": "Referência",
        "quantidade": "Quantidade",
        "situacaopedido": "Situação",
        "bloq_fin": "Financeiro",
        "dataprevfaturamento": (
            "Previsão de faturamento"
        ),
    },
    number_formats={
        "codpedido": 0,
        "quantidade": 0,
    },
    date_formats={
        "dataemissao": "DD/MM/YYYY",
        "dataprevfaturamento": "DD/MM/YYYY",
    },
    hide_index=True,
)


# ============================================================
# PEDIDOS BLOQUEADOS NO FINANCEIRO
# ============================================================

st.subheader(
    "Pedidos bloqueados no financeiro"
)

blocked_detail = (
    blocked_orders.groupby(
        [
            "codpedido",
            "nomecliente",
            "dataemissao",
            "dataprevfaturamento",
            "bloq_fin",
        ],
        as_index=False,
    )
    .agg(
        REFERENCIAS=(
            "codproduto",
            "nunique",
        ),
        QUANTIDADE=(
            "quantidade",
            "sum",
        ),
    )
    .sort_values(
        [
            "dataemissao",
            "QUANTIDADE",
        ],
        ascending=[
            False,
            False,
        ],
    )
)

display_dataframe(
    blocked_detail,
    labels={
        "codpedido": "Pedido",
        "nomecliente": "Cliente",
        "dataemissao": "Data de emissão",
        "dataprevfaturamento": (
            "Previsão de faturamento"
        ),
        "bloq_fin": "Financeiro",
        "REFERENCIAS": "Referências",
        "QUANTIDADE": "Quantidade",
    },
    number_formats={
        "codpedido": 0,
        "REFERENCIAS": 0,
        "QUANTIDADE": 0,
    },
    date_formats={
        "dataemissao": "DD/MM/YYYY",
        "dataprevfaturamento": "DD/MM/YYYY",
    },
    hide_index=True,
)


# ============================================================
# DETALHAMENTO POR SKU
# ============================================================

st.subheader("Detalhamento por SKU")

sku_detail = (
    filtered_items.groupby(
        [
            "sku",
            "referencia",
            "grade",
            "cor",
            "nomeproduto",
        ],
        as_index=False,
    )
    .agg(
        PEDIDOS=(
            "codpedido",
            "nunique",
        ),
        QTD_PEDIDA=(
            "qtdepedida",
            "sum",
        ),
        SALDO=(
            "saldo_aberto",
            "sum",
        ),
        FATURADO=(
            "qtdefaturado",
            "sum",
        ),
        CANCELADO=(
            "qtdecancelada",
            "sum",
        ),
        VALOR_TOTAL=(
            "valor_total_pedido",
            "sum",
        ),
    )
    .sort_values(
        [
            "SALDO",
            "QTD_PEDIDA",
        ],
        ascending=[
            False,
            False,
        ],
    )
)

display_dataframe(
    sku_detail,
    labels={
        "sku": "SKU",
        "referencia": "Referência",
        "grade": "Grade",
        "cor": "Cor",
        "nomeproduto": "Produto",
        "PEDIDOS": "Pedidos",
        "QTD_PEDIDA": "Qtd. pedida",
        "SALDO": "Saldo em aberto",
        "FATURADO": "Faturado",
        "CANCELADO": "Cancelado",
        "VALOR_TOTAL": "Valor total",
    },
    number_formats={
        "PEDIDOS": 0,
        "QTD_PEDIDA": 0,
        "SALDO": 0,
        "FATURADO": 0,
        "CANCELADO": 0,
        "VALOR_TOTAL": 2,
    },
    hide_index=True,
)
