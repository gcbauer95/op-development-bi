"""Análise de necessidade de estoque por referência + cor.

Cruza:
- pedidos vendidos;
- demanda ainda não faturada;
- estoque disponível;
- ordens de fabricação em WIP;
- setor atual das OFs.

A análise principal ocorre por Referência + Cor.

IMPORTANTE:
O WIP possui referência, mas não possui cor.
Por isso, a quantidade em produção é consolidada por referência
e apresentada separadamente, sem rateio artificial entre cores.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# IMPORTS DO PROJETO
# ============================================================

PAGES_DIR = Path(__file__).resolve().parent

if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from data.loader import load_data  # noqa: E402
from utils.display import display_dataframe, format_br_number  # noqa: E402
from utils.shared import apply_theme, get_orders  # noqa: E402
from utils.styles import apply_chart_theme  # noqa: E402


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Necessidade de estoque | PPCP",
    page_icon="📦",
    layout="wide",
)

apply_theme()

st.title("Necessidade de estoque por referência e cor")

st.caption(
    "Análise integrada entre vendas, demanda pendente, "
    "estoque disponível e ordens de fabricação em processo."
)


# ============================================================
# FLUXO PRODUTIVO / WIP
# ============================================================

SETORES_PRE_CORTE = [
    "PCP",
    "COMPRAS",
    "LIBERADAS",
    "ENCAIXE",
]

SETORES_PRODUCAO = [
    "CORTE",
    "CD ANALISE",
    "ALMOXARIFADO",
    "CD COSTURA",
    "COSTURA",
    "LAVANDERIA",
    "ANALISE DE ACABAMENTO",
    "ACABAMENTO",
]

SETORES_WIP = (
    SETORES_PRE_CORTE
    + SETORES_PRODUCAO
)

ORDEM_SETORES = {
    setor: indice
    for indice, setor in enumerate(SETORES_WIP, start=1)
}


# ============================================================
# CARREGAMENTO DOS DADOS
# ============================================================

stock = load_data("estoque_av27")
orders = load_data("pedidos_venda")
order_items = load_data("pedidos_itens")
wip_raw = get_orders()


if stock is None:
    st.warning(
        "Base de estoque não encontrada."
    )
    st.stop()

if orders is None or order_items is None:
    st.warning(
        "Bases de pedidos não encontradas."
    )
    st.stop()

if wip_raw is None or wip_raw.empty:
    st.warning(
        "Base de WIP / ordens de fabricação não encontrada."
    )
    st.stop()


# ============================================================
# CÓPIAS DAS BASES
# ============================================================

stock = stock.copy()
orders = orders.copy()
order_items = order_items.copy()
wip = wip_raw.copy()


# ============================================================
# FUNÇÃO AUXILIAR
# ============================================================

def normalize_text(
    series: pd.Series,
) -> pd.Series:
    return (
        series
        .astype("string")
        .str.strip()
        .str.upper()
    )


# ============================================================
# NORMALIZAÇÃO DO ESTOQUE
# ============================================================

stock["referencia"] = normalize_text(
    stock["referencia"]
)

stock["cor"] = normalize_text(
    stock["cor"]
)

if "grade" in stock.columns:
    stock["grade"] = normalize_text(
        stock["grade"]
    )

stock["estoque_pronta_entrega"] = pd.to_numeric(
    stock["estoque_pronta_entrega"],
    errors="coerce",
).fillna(0)


# ============================================================
# NORMALIZAÇÃO DOS PEDIDOS
# ============================================================

orders["codpedido"] = pd.to_numeric(
    orders["codpedido"],
    errors="coerce",
).astype("Int64")

orders["codcliente"] = pd.to_numeric(
    orders["codcliente"],
    errors="coerce",
).astype("Int64")

orders["codproduto"] = normalize_text(
    orders["codproduto"]
)

orders["situacaopedido"] = normalize_text(
    orders["situacaopedido"]
)

if "codcolecao" in orders.columns:
    orders["codcolecao"] = normalize_text(
        orders["codcolecao"]
    )


# ============================================================
# NORMALIZAÇÃO DOS ITENS
# ============================================================

order_items["codpedido"] = pd.to_numeric(
    order_items["codpedido"],
    errors="coerce",
).astype("Int64")

order_items["referencia"] = normalize_text(
    order_items["referencia"]
)

order_items["cor"] = normalize_text(
    order_items["cor"]
)

if "grade" in order_items.columns:
    order_items["grade"] = normalize_text(
        order_items["grade"]
    )

for column in [
    "qtdepedida",
    "qtdesaldo",
    "qtdefaturado",
    "qtdecancelada",
    "valorunitariobruto",
]:
    if column in order_items.columns:
        order_items[column] = pd.to_numeric(
            order_items[column],
            errors="coerce",
        ).fillna(0)


# ============================================================
# SALDO EM ABERTO DOS PEDIDOS
# ============================================================

# Regra definida:
#
# quantidade em aberto =
# quantidade pedida - quantidade faturada

order_items["SALDO_ABERTO"] = (
    order_items["qtdepedida"]
    - order_items["qtdefaturado"]
).clip(lower=0)


# ============================================================
# NORMALIZAÇÃO DO WIP
# ============================================================

wip["OF"] = (
    wip["OF"]
    .astype("string")
    .str.strip()
)

wip["Referência"] = normalize_text(
    wip["Referência"]
)

wip["Desc. Setor Atual"] = normalize_text(
    wip["Desc. Setor Atual"]
)

if "Coleção" in wip.columns:
    wip["Coleção"] = normalize_text(
        wip["Coleção"]
    )

wip["Qt Pend."] = pd.to_numeric(
    wip["Qt Pend."],
    errors="coerce",
).fillna(0)

wip["Data Setor"] = pd.to_datetime(
    wip["Data Setor"],
    errors="coerce",
)


# ============================================================
# REMOVE OFs ENCERRADAS
# ============================================================

wip = wip.loc[
    wip["Desc. Setor Atual"].notna()
].copy()


# ============================================================
# MANTÉM POSIÇÃO MAIS RECENTE DA OF
# ============================================================

wip = (
    wip
    .sort_values(
        [
            "OF",
            "Data Setor",
        ],
        na_position="first",
    )
    .drop_duplicates(
        subset=["OF"],
        keep="last",
    )
    .copy()
)


# ============================================================
# SOMENTE WIP PRODUTIVO
# ============================================================

wip = wip.loc[
    wip["Desc. Setor Atual"].isin(
        SETORES_WIP
    )
].copy()


# ============================================================
# FILTROS
# ============================================================

st.sidebar.header("Filtros")


# ------------------------------------------------------------
# COLEÇÃO
# ------------------------------------------------------------

selected_collections = []

if "codcolecao" in orders.columns:

    collection_options = sorted(
        orders["codcolecao"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_collections = st.sidebar.multiselect(
        "Coleção",
        collection_options,
    )


# ------------------------------------------------------------
# REFERÊNCIA
# ------------------------------------------------------------

reference_options = sorted(
    set(
        stock["referencia"]
        .dropna()
        .tolist()
    )
    | set(
        order_items["referencia"]
        .dropna()
        .tolist()
    )
)

selected_references = st.sidebar.multiselect(
    "Referência",
    reference_options,
)


# ------------------------------------------------------------
# COR
# ------------------------------------------------------------

color_options = sorted(
    set(
        stock["cor"]
        .dropna()
        .tolist()
    )
    | set(
        order_items["cor"]
        .dropna()
        .tolist()
    )
)

selected_colors = st.sidebar.multiselect(
    "Cor",
    color_options,
)


# ------------------------------------------------------------
# SETOR
# ------------------------------------------------------------

sector_options = [
    setor
    for setor in SETORES_WIP
    if setor in wip["Desc. Setor Atual"].dropna().unique()
]

selected_sectors = st.sidebar.multiselect(
    "Setor",
    sector_options,
)


# ------------------------------------------------------------
# SOMENTE COM FALTA
# ------------------------------------------------------------

only_shortage = st.sidebar.checkbox(
    "Mostrar somente referências + cores com falta",
    value=False,
)


# ============================================================
# FILTRO DE COLEÇÃO NOS PEDIDOS
# ============================================================

orders_filtered = orders.copy()

if selected_collections:
    orders_filtered = orders_filtered.loc[
        orders_filtered["codcolecao"].isin(
            selected_collections
        )
    ].copy()


# ============================================================
# FILTRO DE COLEÇÃO NO WIP
# ============================================================

if (
    selected_collections
    and "Coleção" in wip.columns
):
    wip = wip.loc[
        wip["Coleção"].isin(
            selected_collections
        )
    ].copy()


# ============================================================
# REFERÊNCIAS PRESENTES NO(S) SETOR(ES) SELECIONADO(S)
# ============================================================

# Importante:
# o filtro de setor NÃO altera o WIP usado nos cálculos e na coluna
# "Posição das OFs". Ele serve apenas para identificar quais referências
# devem aparecer na tabela "Cobertura consolidada por referência".
selected_sector_references = None

if selected_sectors:
    selected_sector_references = (
        wip.loc[
            wip["Desc. Setor Atual"].isin(
                selected_sectors
            ),
            "Referência",
        ]
        .dropna()
        .unique()
    )


# ============================================================
# PEDIDOS VÁLIDOS
# ============================================================

# Cliente código 1 permanece desconsiderado.

valid_order_ids = (
    orders_filtered.loc[
        orders_filtered["codcliente"].ne(1),
        "codpedido",
    ]
    .dropna()
    .unique()
)


# ============================================================
# BASE DE ITENS PARA HISTÓRICO DE VENDAS
# ============================================================

sales_items = order_items.loc[
    order_items["codpedido"].isin(
        valid_order_ids
    )
].copy()


if selected_references:
    sales_items = sales_items.loc[
        sales_items["referencia"].isin(
            selected_references
        )
    ]

if selected_colors:
    sales_items = sales_items.loc[
        sales_items["cor"].isin(
            selected_colors
        )
    ]


# ============================================================
# DESCRIÇÃO DA REFERÊNCIA PARA EXIBIÇÃO
# ============================================================

# A descrição está na base de WIP, nas colunas
# "Referência" e "Descrição". O lookup é criado a partir
# da base original para não depender dos filtros de setor/WIP.

reference_description = None

if (
    "Referência" in wip_raw.columns
    and "Descrição" in wip_raw.columns
):
    reference_description = (
        wip_raw[
            [
                "Referência",
                "Descrição",
            ]
        ]
        .copy()
    )

    reference_description["Referência"] = normalize_text(
        reference_description["Referência"]
    )

    reference_description["Descrição"] = (
        reference_description["Descrição"]
        .astype("string")
        .str.strip()
    )

    reference_description = reference_description.loc[
        reference_description["Referência"].notna()
        & reference_description["Descrição"].notna()
        & reference_description["Descrição"].ne("")
    ]

    reference_description = (
        reference_description
        .drop_duplicates(
            subset=["Referência"],
            keep="first",
        )
        .rename(
            columns={
                "Referência": "referencia",
                "Descrição": "DESCRICAO",
            }
        )
    )


# Fallback: caso alguma versão da base não tenha "Descrição"
# no WIP, tenta localizar uma descrição nas demais bases.
if reference_description is None:

    description_candidates = [
        "descricao",
        "descrição",
        "descricao_produto",
        "desc_produto",
        "descricao_referencia",
        "desc_referencia",
        "descricaoproduto",
        "descproduto",
    ]

    for source_df in [
        order_items,
        stock,
        orders,
    ]:

        description_column = next(
            (
                column
                for column in description_candidates
                if column in source_df.columns
            ),
            None,
        )

        if (
            "referencia" not in source_df.columns
            or not description_column
        ):
            continue

        temp_description = (
            source_df[
                [
                    "referencia",
                    description_column,
                ]
            ]
            .copy()
        )

        temp_description[description_column] = (
            temp_description[description_column]
            .astype("string")
            .str.strip()
        )

        temp_description = temp_description.loc[
            temp_description["referencia"].notna()
            & temp_description[description_column].notna()
            & temp_description[description_column].ne("")
        ]

        if temp_description.empty:
            continue

        reference_description = (
            temp_description
            .drop_duplicates(
                subset=["referencia"],
                keep="first",
            )
            .rename(
                columns={
                    description_column: "DESCRICAO"
                }
            )
        )

        break


# ============================================================
# QUANTIDADE VENDIDA POR REFERÊNCIA + COR
# ============================================================

sales_reference_color = (
    sales_items
    .groupby(
        [
            "referencia",
            "cor",
        ],
        as_index=False,
    )
    .agg(
        QTD_VENDIDA=(
            "qtdepedida",
            "sum",
        ),
        QTD_FATURADA=(
            "qtdefaturado",
            "sum",
        ),
        PEDIDOS=(
            "codpedido",
            "nunique",
        ),
    )
)


# ============================================================
# DEMANDA EM ABERTO
# ============================================================

open_statuses = [
    "EM ANALISE",
    "PARCIAL",
]

open_order_ids = (
    orders_filtered.loc[
        orders_filtered["situacaopedido"].isin(
            open_statuses
        )
        & orders_filtered["codcliente"].ne(1),
        "codpedido",
    ]
    .dropna()
    .unique()
)

pending_items = order_items.loc[
    order_items["codpedido"].isin(
        open_order_ids
    )
].copy()


if selected_references:
    pending_items = pending_items.loc[
        pending_items["referencia"].isin(
            selected_references
        )
    ]

if selected_colors:
    pending_items = pending_items.loc[
        pending_items["cor"].isin(
            selected_colors
        )
    ]


# ============================================================
# DEMANDA PENDENTE POR REFERÊNCIA + COR
# ============================================================

pending_reference_color = (
    pending_items
    .groupby(
        [
            "referencia",
            "cor",
        ],
        as_index=False,
    )
    .agg(
        QTD_PEDIDA_ABERTA=(
            "qtdepedida",
            "sum",
        ),
        QTD_FATURADA_ABERTA=(
            "qtdefaturado",
            "sum",
        ),
        DEMANDA_PENDENTE=(
            "SALDO_ABERTO",
            "sum",
        ),
        PEDIDOS_ABERTOS=(
            "codpedido",
            "nunique",
        ),
    )
)


# ============================================================
# ESTOQUE POR REFERÊNCIA + COR
# ============================================================

stock_filtered = stock.copy()

if selected_references:
    stock_filtered = stock_filtered.loc[
        stock_filtered["referencia"].isin(
            selected_references
        )
    ]

if selected_colors:
    stock_filtered = stock_filtered.loc[
        stock_filtered["cor"].isin(
            selected_colors
        )
    ]


stock_reference_color = (
    stock_filtered
    .groupby(
        [
            "referencia",
            "cor",
        ],
        as_index=False,
    )
    .agg(
        ESTOQUE=(
            "estoque_pronta_entrega",
            "sum",
        )
    )
)


# ============================================================
# BASE CONSOLIDADA REFERÊNCIA + COR
# ============================================================

comparison = sales_reference_color.merge(
    pending_reference_color,
    on=[
        "referencia",
        "cor",
    ],
    how="outer",
)

comparison = comparison.merge(
    stock_reference_color,
    on=[
        "referencia",
        "cor",
    ],
    how="outer",
)


numeric_columns = [
    "QTD_VENDIDA",
    "QTD_FATURADA",
    "PEDIDOS",
    "QTD_PEDIDA_ABERTA",
    "QTD_FATURADA_ABERTA",
    "DEMANDA_PENDENTE",
    "PEDIDOS_ABERTOS",
    "ESTOQUE",
]

for column in numeric_columns:

    if column not in comparison.columns:
        comparison[column] = 0

    comparison[column] = pd.to_numeric(
        comparison[column],
        errors="coerce",
    ).fillna(0)


# ============================================================
# NECESSIDADE PARA ESTOQUE
# ============================================================

comparison["SALDO_APOS_PEDIDOS"] = (
    comparison["ESTOQUE"]
    - comparison["DEMANDA_PENDENTE"]
)

comparison["FALTA_ATUAL"] = (
    -comparison["SALDO_APOS_PEDIDOS"]
).clip(lower=0)

comparison["SOBRA_ATUAL"] = (
    comparison["SALDO_APOS_PEDIDOS"]
).clip(lower=0)


comparison["SITUACAO_ESTOQUE"] = comparison[
    "SALDO_APOS_PEDIDOS"
].map(
    lambda value: (
        "FALTA"
        if value < 0
        else "SOBRA"
        if value > 0
        else "EQUILIBRADO"
    )
)


# ============================================================
# RANKING DE VENDA
# ============================================================

comparison["RANK_VENDA"] = (
    comparison["QTD_VENDIDA"]
    .rank(
        method="dense",
        ascending=False,
    )
    .astype("Int64")
)


# ============================================================
# WIP POR REFERÊNCIA E SETOR
# ============================================================

if selected_references:
    wip = wip.loc[
        wip["Referência"].isin(
            selected_references
        )
    ].copy()


wip["ORDEM_SETOR"] = (
    wip["Desc. Setor Atual"]
    .map(ORDEM_SETORES)
)


wip_reference_sector = (
    wip
    .groupby(
        [
            "Referência",
            "ORDEM_SETOR",
            "Desc. Setor Atual",
        ],
        as_index=False,
    )
    .agg(
        OFS=(
            "OF",
            "nunique",
        ),
        QTD_WIP=(
            "Qt Pend.",
            "sum",
        ),
    )
    .sort_values(
        [
            "Referência",
            "ORDEM_SETOR",
        ]
    )
)


# ============================================================
# TOTAL WIP POR REFERÊNCIA
# ============================================================

wip_reference = (
    wip
    .groupby(
        "Referência",
        as_index=False,
    )
    .agg(
        OFS_ABERTAS=(
            "OF",
            "nunique",
        ),
        WIP_TOTAL=(
            "Qt Pend.",
            "sum",
        ),
    )
    .rename(
        columns={
            "Referência": "referencia",
        }
    )
)


# ============================================================
# TEXTO DOS SETORES POR REFERÊNCIA
# ============================================================

sector_text = (
    wip_reference_sector
    .assign(
        SETOR_INFO=lambda data: (
            data["Desc. Setor Atual"]
            + ": "
            + data["QTD_WIP"]
            .round(0)
            .astype("Int64")
            .astype("string")
        )
    )
    .groupby(
        "Referência",
        as_index=False,
    )
    .agg(
        SETORES_WIP=(
            "SETOR_INFO",
            lambda values: " | ".join(values),
        )
    )
    .rename(
        columns={
            "Referência": "referencia",
        }
    )
)


wip_reference = wip_reference.merge(
    sector_text,
    on="referencia",
    how="left",
)


# ============================================================
# ADICIONA WIP À VISÃO REFERÊNCIA + COR
# ============================================================

comparison = comparison.merge(
    wip_reference,
    on="referencia",
    how="left",
)

comparison["OFS_ABERTAS"] = pd.to_numeric(
    comparison["OFS_ABERTAS"],
    errors="coerce",
).fillna(0)

comparison["WIP_TOTAL"] = pd.to_numeric(
    comparison["WIP_TOTAL"],
    errors="coerce",
).fillna(0)

comparison["SETORES_WIP"] = (
    comparison["SETORES_WIP"]
    .fillna("-")
)


# ============================================================
# ADICIONA DESCRIÇÃO À VISÃO PARA EXIBIÇÃO
# ============================================================

if reference_description is not None:
    comparison = comparison.merge(
        reference_description,
        on="referencia",
        how="left",
    )

    comparison["DESCRICAO"] = (
        comparison["DESCRICAO"]
        .astype("string")
        .fillna("")
        .str.strip()
    )
else:
    comparison["DESCRICAO"] = ""


# ============================================================
# FILTRO SOMENTE COM FALTA
# ============================================================

if only_shortage:
    comparison = comparison.loc[
        comparison["FALTA_ATUAL"] > 0
    ].copy()


# ============================================================
# ORDENAÇÃO PRINCIPAL
# ============================================================

comparison = (
    comparison
    .sort_values(
        [
            "FALTA_ATUAL",
            "QTD_VENDIDA",
            "referencia",
            "cor",
        ],
        ascending=[
            False,
            False,
            True,
            True,
        ],
    )
    .reset_index(drop=True)
)


# ============================================================
# KPIs
# ============================================================

total_pending = comparison[
    "DEMANDA_PENDENTE"
].sum()

total_stock = comparison[
    "ESTOQUE"
].sum()

total_shortage = comparison[
    "FALTA_ATUAL"
].sum()

references_shortage = comparison.loc[
    comparison["FALTA_ATUAL"] > 0,
    "referencia",
].nunique()


c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Demanda pendente",
    format_br_number(
        total_pending
    ),
)

c2.metric(
    "Estoque disponível",
    format_br_number(
        total_stock
    ),
)

c3.metric(
    "Falta atual",
    format_br_number(
        total_shortage
    ),
)

c4.metric(
    "Referências com falta",
    format_br_number(
        references_shortage
    ),
)


# ============================================================
# PRINCIPAL: REFERÊNCIA + COR
# ============================================================

st.subheader(
    "Necessidade por referência + cor"
)

st.caption(
    "Ranking baseado na quantidade vendida. "
    "A falta atual considera estoque disponível menos "
    "a quantidade ainda não faturada dos pedidos em aberto."
)

display_dataframe(
    comparison[
        [
            "RANK_VENDA",
            "referencia",
            "DESCRICAO",
            "cor",
            "QTD_VENDIDA",
            "PEDIDOS",
            "DEMANDA_PENDENTE",
            "ESTOQUE",
            "SALDO_APOS_PEDIDOS",
            "FALTA_ATUAL",
            "SOBRA_ATUAL",
            "SITUACAO_ESTOQUE",
            "OFS_ABERTAS",
            "WIP_TOTAL",
            "SETORES_WIP",
        ]
    ],
    labels={
        "RANK_VENDA": "Rank venda",
        "referencia": "Referência",
        "DESCRICAO": "Descrição",
        "cor": "Cor",
        "QTD_VENDIDA": "Qtd. vendida",
        "PEDIDOS": "Pedidos",
        "DEMANDA_PENDENTE": "Pendente",
        "ESTOQUE": "Estoque",
        "SALDO_APOS_PEDIDOS": "Saldo após pedidos",
        "FALTA_ATUAL": "Falta atual",
        "SOBRA_ATUAL": "Sobra",
        "SITUACAO_ESTOQUE": "Situação",
        "OFS_ABERTAS": "OFs abertas",
        "WIP_TOTAL": "WIP da referência",
        "SETORES_WIP": "Posição do WIP",
    },
    number_formats={
        "RANK_VENDA": 0,
        "QTD_VENDIDA": 0,
        "PEDIDOS": 0,
        "DEMANDA_PENDENTE": 0,
        "ESTOQUE": 0,
        "SALDO_APOS_PEDIDOS": 0,
        "FALTA_ATUAL": 0,
        "SOBRA_ATUAL": 0,
        "OFS_ABERTAS": 0,
        "WIP_TOTAL": 0,
    },
    hide_index=True,
)


# ============================================================
# TOP REFERÊNCIA + COR POR VENDA
# ============================================================

st.subheader(
    "Referências + cores mais vendidas"
)

top_sales = (
    comparison
    .sort_values(
        "QTD_VENDIDA",
        ascending=False,
    )
    .head(20)
    .copy()
)

top_sales["REF_COR"] = top_sales.apply(
    lambda row: (
        f"{row['referencia']} - {row['DESCRICAO']} | {row['cor']}"
        if row["DESCRICAO"]
        else f"{row['referencia']} | {row['cor']}"
    ),
    axis=1,
)

fig_sales = go.Figure()

fig_sales.add_trace(
    go.Bar(
        y=top_sales["REF_COR"],
        x=top_sales["QTD_VENDIDA"],
        orientation="h",
        name="Qtd. vendida",
        text=top_sales["QTD_VENDIDA"].map(
            lambda value: format_br_number(
                value,
                0,
            )
        ),
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Vendido: %{x:,.0f}"
            "<extra></extra>"
        ),
    )
)

fig_sales.update_layout(
    xaxis_title="Quantidade vendida",
    yaxis_title="Referência + cor",
    yaxis=dict(
        autorange="reversed",
    ),
    height=650,
    showlegend=False,
    margin=dict(
        l=20,
        r=40,
        t=30,
        b=50,
    ),
)

apply_chart_theme(
    fig_sales
)

st.plotly_chart(
    fig_sales,
    width="stretch",
)


# ============================================================
# RESUMO POR REFERÊNCIA
# ============================================================

st.subheader(
    "Cobertura consolidada por referência"
)

st.caption(
    "Nesta visão o WIP pode ser usado matematicamente, "
    "porque pedidos, estoque e produção estão consolidados "
    "no mesmo nível: referência."
)


reference_summary = (
    comparison
    .groupby(
        "referencia",
        as_index=False,
    )
    .agg(
        DESCRICAO=(
            "DESCRICAO",
            "first",
        ),
        QTD_VENDIDA=(
            "QTD_VENDIDA",
            "sum",
        ),
        DEMANDA_PENDENTE=(
            "DEMANDA_PENDENTE",
            "sum",
        ),
        ESTOQUE=(
            "ESTOQUE",
            "sum",
        ),
        FALTA_ATUAL=(
            "FALTA_ATUAL",
            "sum",
        ),
    )
)


reference_summary = reference_summary.merge(
    wip_reference[
        [
            "referencia",
            "OFS_ABERTAS",
            "WIP_TOTAL",
            "SETORES_WIP",
        ]
    ],
    on="referencia",
    how="left",
)


# ============================================================
# APLICA FILTRO DE SETOR À COBERTURA CONSOLIDADA
# ============================================================

# O setor filtra as LINHAS da tabela pela existência de OF naquele setor.
# Depois que a referência é selecionada, continuam sendo exibidos todos os
# setores da referência na coluna "Posição das OFs".
if selected_sector_references is not None:
    reference_summary = reference_summary.loc[
        reference_summary["referencia"].isin(
            selected_sector_references
        )
    ].copy()


for column in [
    "OFS_ABERTAS",
    "WIP_TOTAL",
]:
    reference_summary[column] = pd.to_numeric(
        reference_summary[column],
        errors="coerce",
    ).fillna(0)


reference_summary["SETORES_WIP"] = (
    reference_summary["SETORES_WIP"]
    .fillna("-")
)


# ============================================================
# PROJEÇÃO COM PRODUÇÃO
# ============================================================

reference_summary["DISPONIVEL_COM_WIP"] = (
    reference_summary["ESTOQUE"]
    + reference_summary["WIP_TOTAL"]
)

reference_summary["SALDO_PROJETADO"] = (
    reference_summary["DISPONIVEL_COM_WIP"]
    - reference_summary["DEMANDA_PENDENTE"]
)

reference_summary["FALTA_APOS_WIP"] = (
    -reference_summary["SALDO_PROJETADO"]
).clip(lower=0)

reference_summary["SOBRA_APOS_WIP"] = (
    reference_summary["SALDO_PROJETADO"]
).clip(lower=0)


reference_summary["SITUACAO_PROJETADA"] = (
    reference_summary["SALDO_PROJETADO"]
    .map(
        lambda value: (
            "FALTA MESMO COM WIP"
            if value < 0
            else "COBERTO COM WIP"
        )
    )
)


reference_summary = reference_summary.sort_values(
    [
        "FALTA_APOS_WIP",
        "QTD_VENDIDA",
    ],
    ascending=[
        False,
        False,
    ],
)


display_dataframe(
    reference_summary,
    labels={
        "referencia": "Referência",
        "DESCRICAO": "Descrição",
        "QTD_VENDIDA": "Qtd. vendida",
        "DEMANDA_PENDENTE": "Pedidos pendentes",
        "ESTOQUE": "Estoque",
        "FALTA_ATUAL": "Falta atual",
        "OFS_ABERTAS": "OFs abertas",
        "WIP_TOTAL": "WIP",
        "DISPONIVEL_COM_WIP": "Estoque + WIP",
        "SALDO_PROJETADO": "Saldo projetado",
        "FALTA_APOS_WIP": "Falta após WIP",
        "SOBRA_APOS_WIP": "Sobra após WIP",
        "SITUACAO_PROJETADA": "Situação projetada",
        "SETORES_WIP": "Posição das OFs",
    },
    number_formats={
        "QTD_VENDIDA": 0,
        "DEMANDA_PENDENTE": 0,
        "ESTOQUE": 0,
        "FALTA_ATUAL": 0,
        "OFS_ABERTAS": 0,
        "WIP_TOTAL": 0,
        "DISPONIVEL_COM_WIP": 0,
        "SALDO_PROJETADO": 0,
        "FALTA_APOS_WIP": 0,
        "SOBRA_APOS_WIP": 0,
    },
    hide_index=True,
)


# ============================================================
# WIP DETALHADO POR REFERÊNCIA E SETOR
# ============================================================

st.subheader(
    "Produção em aberto por referência e setor"
)

display_dataframe(
    wip_reference_sector[
        [
            "Referência",
            "Desc. Setor Atual",
            "OFS",
            "QTD_WIP",
        ]
    ],
    labels={
        "Referência": "Referência",
        "Desc. Setor Atual": "Setor atual",
        "OFS": "OFs",
        "QTD_WIP": "Qtd. pendente no WIP",
    },
    number_formats={
        "OFS": 0,
        "QTD_WIP": 0,
    },
    hide_index=True,
)


# ============================================================
# CONSULTA / DETALHAMENTO DAS OFs
# ============================================================

st.subheader(
    "Consulta da situação atual das OFs"
)

st.caption(
    "Informe uma ou mais referências ou OFs. "
    "Separe múltiplos valores por vírgula, ponto e vírgula "
    "ou quebra de linha."
)


# ------------------------------------------------------------
# FUNÇÃO PARA TRATAR MÚLTIPLOS VALORES
# ------------------------------------------------------------

def parse_search_values(
    value: str,
) -> list[str]:

    if not value:
        return []

    normalized = (
        value
        .replace(";", ",")
        .replace("\n", ",")
    )

    return [
        item.strip().upper()
        for item in normalized.split(",")
        if item.strip()
    ]


# ------------------------------------------------------------
# CAMPOS DE PESQUISA
# ------------------------------------------------------------

col_ref, col_of = st.columns(2)

with col_ref:

    search_references_text = st.text_area(
        "Referência(s)",
        placeholder=(
            "Exemplo:\n"
            "12345\n"
            "12346\n"
            "12347"
        ),
        height=110,
        key="consulta_of_referencias",
    )


with col_of:

    search_ofs_text = st.text_area(
        "OF(s)",
        placeholder=(
            "Exemplo:\n"
            "123456\n"
            "123457\n"
            "123458"
        ),
        height=110,
        key="consulta_of_numeros",
    )


search_references = parse_search_values(
    search_references_text
)

search_ofs = parse_search_values(
    search_ofs_text
)


# ------------------------------------------------------------
# COLUNAS DO DETALHAMENTO
# ------------------------------------------------------------

wip_detail_columns = [
    "OF",
    "Referência",
    "Desc. Setor Atual",
    "Qt Pend.",
]

for optional_column in [
    "Coleção",
    "Desc. Coleção",
    "Desc. Tipo OP",
    "Emissão",
    "Data Setor",
    "Prev. Término",
]:

    if optional_column in wip.columns:

        wip_detail_columns.append(
            optional_column
        )


# ------------------------------------------------------------
# BASE PARA CONSULTA
# ------------------------------------------------------------

wip_detail = wip[
    wip_detail_columns
].copy()


# ------------------------------------------------------------
# NORMALIZA CAMPOS PARA PESQUISA
# ------------------------------------------------------------

wip_detail["_OF_SEARCH"] = (
    wip_detail["OF"]
    .astype("string")
    .str.strip()
    .str.upper()
)

wip_detail["_REF_SEARCH"] = (
    wip_detail["Referência"]
    .astype("string")
    .str.strip()
    .str.upper()
)


# ------------------------------------------------------------
# FILTRO POR REFERÊNCIA E/OU OF
#
# Caso os dois campos sejam preenchidos:
# REFERÊNCIA OU OF
# ------------------------------------------------------------

has_search = (
    bool(search_references)
    or bool(search_ofs)
)


if has_search:

    mask = pd.Series(
        False,
        index=wip_detail.index,
    )

    if search_references:

        mask = (
            mask
            | wip_detail["_REF_SEARCH"].isin(
                search_references
            )
        )

    if search_ofs:

        mask = (
            mask
            | wip_detail["_OF_SEARCH"].isin(
                search_ofs
            )
        )

    wip_detail = wip_detail.loc[
        mask
    ].copy()


# ------------------------------------------------------------
# REMOVE COLUNAS AUXILIARES
# ------------------------------------------------------------

wip_detail = wip_detail.drop(
    columns=[
        "_OF_SEARCH",
        "_REF_SEARCH",
    ],
    errors="ignore",
)


# ------------------------------------------------------------
# ORDENAÇÃO
# ------------------------------------------------------------

wip_detail = (
    wip_detail
    .sort_values(
        [
            "Referência",
            "Desc. Setor Atual",
            "OF",
        ]
    )
    .reset_index(drop=True)
)


# ------------------------------------------------------------
# RESULTADO
# ------------------------------------------------------------

if has_search:

    if wip_detail.empty:

        st.warning(
            "Nenhuma OF encontrada para os critérios informados."
        )

    else:

        total_ofs = (
            wip_detail["OF"]
            .nunique()
        )

        total_referencias = (
            wip_detail["Referência"]
            .nunique()
        )

        total_pendente = (
            pd.to_numeric(
                wip_detail["Qt Pend."],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        )


        kpi1, kpi2, kpi3 = st.columns(3)

        kpi1.metric(
            "OFs encontradas",
            format_br_number(
                total_ofs
            ),
        )

        kpi2.metric(
            "Referências",
            format_br_number(
                total_referencias
            ),
        )

        kpi3.metric(
            "Qtd. pendente",
            format_br_number(
                total_pendente
            ),
        )


        display_dataframe(
            wip_detail,
            labels={
                "OF": "OF",
                "Referência": "Referência",
                "Desc. Setor Atual": "Setor atual",
                "Qt Pend.": "Qtd. pendente",
                "Coleção": "Coleção",
                "Desc. Coleção": "Descrição coleção",
                "Desc. Tipo OP": "Tipo OP",
                "Emissão": "Emissão",
                "Data Setor": "Data setor",
                "Prev. Término": "Prev. término",
            },
            number_formats={
                "Qt Pend.": 0,
            },
            date_formats={
                "Emissão": "DD/MM/YYYY",
                "Data Setor": "DD/MM/YYYY",
                "Prev. Término": "DD/MM/YYYY",
            },
            hide_index=True,
        )

else:

    st.info(
        "Informe pelo menos uma Referência ou OF "
        "para consultar a situação atual."
    )
