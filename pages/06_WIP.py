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

from utils.shared import FLOW_ORDER, FLOW_SEQUENCE, apply_theme, get_orders
from utils.styles import apply_chart_theme
from utils.display import display_dataframe, format_br_number


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="WIP e Aging",
    layout="wide",
)
apply_theme()

st.title("WIP e Aging")

st.caption(
    "Posição atual das ordens de fabricação, estoque em processo, "
    "aging e acompanhamento de prazo."
)


# ============================================================
# 1. CONFIGURAÇÃO DO FLUXO
# ============================================================

FLUXO = FLOW_SEQUENCE

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

ORDEM_FLUXO = FLOW_ORDER


# ============================================================
# 2. CARREGAR ORDENS
# ============================================================

df = get_orders()

if df is None or df.empty:
    st.warning("Nenhuma ordem disponível.")
    st.stop()

df = df.copy()


# ============================================================
# 3. NORMALIZAÇÕES
# ============================================================

df["OF"] = (
    df["OF"]
    .astype("string")
    .str.strip()
)

df["Desc. Setor Atual"] = (
    df["Desc. Setor Atual"]
    .astype("string")
    .str.strip()
    .str.upper()
)

if "Coleção" in df.columns:
    df["Coleção"] = (
        df["Coleção"]
        .astype("string")
        .str.strip()
    )

if "Desc. Coleção" in df.columns:
    df["Desc. Coleção"] = (
        df["Desc. Coleção"]
        .astype("string")
        .str.strip()
    )

if "Desc. Tipo OP" in df.columns:
    df["Desc. Tipo OP"] = (
        df["Desc. Tipo OP"]
        .astype("string")
        .str.strip()
    )


# ------------------------------------------------------------
# Datas
# ------------------------------------------------------------

for column in [
    "Emissão",
    "Data Setor",
    "Prev. Término",
]:
    if column in df.columns:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce",
        )


# ------------------------------------------------------------
# Quantidades
# ------------------------------------------------------------

for column in [
    "Qt Orig.",
    "Qt Aprovada",
    "Qt Pend.",
]:
    if column in df.columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)


# ============================================================
# 4. REMOVER OFs ENCERRADAS
# ============================================================
#
# Regra:
# Setor atual nulo = OF encerrada.
# ============================================================

df = df[
    df["Desc. Setor Atual"].notna()
].copy()


# ============================================================
# 5. GARANTIR UMA LINHA POR OF
# ============================================================

df = (
    df
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
# 6. POSIÇÃO NO FLUXO
# ============================================================

df["ORDEM_FLUXO"] = (
    df["Desc. Setor Atual"]
    .map(ORDEM_FLUXO)
)


# ============================================================
# 7. CLASSIFICAÇÃO DA FASE
# ============================================================

def classificar_fase(setor):

    if pd.isna(setor):
        return "ENCERRADA"

    if setor in SETORES_PRE_CORTE:
        return "PRÉ-CORTE"

    if setor in SETORES_PRODUCAO:
        return "PRODUÇÃO"

    if setor == "EXPEDIÇÃO":
        return "EXPEDIÇÃO"

    return "FORA DO FLUXO"


df["FASE"] = (
    df["Desc. Setor Atual"]
    .apply(classificar_fase)
)


# ============================================================
# 8. DATA DE REFERÊNCIA
# ============================================================

HOJE = pd.Timestamp.today().normalize()


# ============================================================
# 9. AGING DA OF
# ============================================================

df["AGING_OF_DIAS"] = (
    HOJE
    - df["Emissão"].dt.normalize()
).dt.days


# ============================================================
# 10. AGING NO SETOR
# ============================================================

df["AGING_SETOR_DIAS"] = (
    HOJE
    - df["Data Setor"].dt.normalize()
).dt.days


# ============================================================
# 11. PRAZO
# ============================================================

df["DIAS_PARA_PRAZO"] = (
    df["Prev. Término"].dt.normalize()
    - HOJE
).dt.days


def classificar_prazo(dias):

    if pd.isna(dias):
        return "SEM PRAZO"

    if dias < 0:
        return "ATRASADA"

    if dias == 0:
        return "VENCE HOJE"

    return "NO PRAZO"


df["STATUS_PRAZO"] = (
    df["DIAS_PARA_PRAZO"]
    .apply(classificar_prazo)
)


# ============================================================
# 12. IDENTIFICAR WIP
# ============================================================
#
# WIP = PCP até ACABAMENTO.
#
# EXPEDIÇÃO não entra no WIP.
# ============================================================

wip = df[
    df["Desc. Setor Atual"].isin(
        SETORES_WIP
    )
].copy()


# ============================================================
# 13. FILTROS
# ============================================================

st.sidebar.header("Filtros")


# ------------------------------------------------------------
# Coleção
# ------------------------------------------------------------

if {
    "Coleção",
    "Desc. Coleção",
}.issubset(wip.columns):

    colecoes = (
        wip[
            [
                "Coleção",
                "Desc. Coleção",
            ]
        ]
        .dropna(subset=["Coleção"])
        .drop_duplicates()
        .sort_values("Coleção")
        .copy()
    )

    colecoes["LABEL"] = (
        colecoes["Coleção"]
        + " - "
        + colecoes["Desc. Coleção"].fillna("")
    )

    mapa_colecoes = dict(
        zip(
            colecoes["Coleção"],
            colecoes["LABEL"],
        )
    )

    selected_colecoes = st.sidebar.multiselect(
        "Coleção",
        options=colecoes["Coleção"].tolist(),
        format_func=lambda codigo: mapa_colecoes.get(
            codigo,
            codigo,
        ),
    )

    if selected_colecoes:
        wip = wip[
            wip["Coleção"].isin(
                selected_colecoes
            )
        ].copy()


# ------------------------------------------------------------
# Tipo OP
# ------------------------------------------------------------

if "Desc. Tipo OP" in wip.columns:

    tipos_op = sorted(
        wip["Desc. Tipo OP"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_tipo = st.sidebar.multiselect(
        "Tipo OP",
        tipos_op,
    )

    if selected_tipo:
        wip = wip[
            wip["Desc. Tipo OP"].isin(
                selected_tipo
            )
        ].copy()


# ------------------------------------------------------------
# Fase
# ------------------------------------------------------------

fases_disponiveis = [
    fase
    for fase in [
        "PRÉ-CORTE",
        "PRODUÇÃO",
    ]
    if fase in wip["FASE"].unique()
]

selected_fase = st.sidebar.multiselect(
    "Fase",
    fases_disponiveis,
)

if selected_fase:
    wip = wip[
        wip["FASE"].isin(
            selected_fase
        )
    ].copy()


# ------------------------------------------------------------
# Setor atual
# ------------------------------------------------------------

setores_disponiveis = [
    setor
    for setor in SETORES_WIP
    if setor in wip["Desc. Setor Atual"].unique()
]

selected_setor = st.sidebar.multiselect(
    "Setor atual",
    setores_disponiveis,
)

if selected_setor:
    wip = wip[
        wip["Desc. Setor Atual"].isin(
            selected_setor
        )
    ].copy()


# ============================================================
# 14. SUBGRUPOS
# ============================================================

wip_pre_corte = wip[
    wip["Desc. Setor Atual"].isin(
        SETORES_PRE_CORTE
    )
].copy()

wip_producao = wip[
    wip["Desc. Setor Atual"].isin(
        SETORES_PRODUCAO
    )
].copy()


# ============================================================
# 15. FUNÇÕES AUXILIARES
# ============================================================

def total_ofs(data):
    return data["OF"].nunique()


def total_pecas(data):
    return data["Qt Pend."].sum()


def format_number(value):
    return (
        f"{value:,.0f}"
        .replace(",", ".")
    )


def format_days(value):

    if pd.isna(value):
        return "-"

    return (
        f"{value:,.1f} dias"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


# ============================================================
# 16. WIP
# ============================================================

st.subheader("WIP")

c1, c2, c3 = st.columns(3)

c1.metric(
    "WIP Total",
    format_number(
        total_pecas(wip)
    ),
    help=f"{total_ofs(wip)} OFs",
)

c2.metric(
    "WIP Pré-Corte",
    format_number(
        total_pecas(wip_pre_corte)
    ),
    help=f"{total_ofs(wip_pre_corte)} OFs",
)

c3.metric(
    "WIP Produção",
    format_number(
        total_pecas(wip_producao)
    ),
    help=f"{total_ofs(wip_producao)} OFs",
)

st.caption(
    "WIP em peças = soma de Qt Pend. das OFs atualmente "
    "posicionadas entre PCP e ACABAMENTO."
)


# ============================================================
# 17. VALIDAÇÃO DO WIP
# ============================================================

total_validacao = (
    total_pecas(wip_pre_corte)
    + total_pecas(wip_producao)
)

if total_validacao != total_pecas(wip):

    st.warning(
        "WIP Total diferente da soma de "
        "Pré-Corte + Produção."
    )


# ============================================================
# 18. AGING
# ============================================================

st.subheader("Aging")

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Aging médio da OF",
    format_days(
        wip["AGING_OF_DIAS"].mean()
    ),
)

c2.metric(
    "Aging mediano da OF",
    format_days(
        wip["AGING_OF_DIAS"].median()
    ),
)

c3.metric(
    "Aging médio no setor",
    format_days(
        wip["AGING_SETOR_DIAS"].mean()
    ),
)

c4.metric(
    "Aging mediano no setor",
    format_days(
        wip["AGING_SETOR_DIAS"].median()
    ),
)


# ============================================================
# 19. PREPARAR WIP POR SETOR
# ============================================================
#
# Essa agregação é criada antes do gráfico e da tabela.
# ============================================================

wip_setor = (
    wip
    .groupby(
        [
            "ORDEM_FLUXO",
            "Desc. Setor Atual",
        ],
        as_index=False,
    )
    .agg(
        OFS=(
            "OF",
            "nunique",
        ),
        PECAS=(
            "Qt Pend.",
            "sum",
        ),
        AGING_MEDIO=(
            "AGING_SETOR_DIAS",
            "mean",
        ),
        AGING_MEDIANO=(
            "AGING_SETOR_DIAS",
            "median",
        ),
    )
    .sort_values(
        "ORDEM_FLUXO"
    )
)

wip_setor["AGING_MEDIO"] = (
    wip_setor["AGING_MEDIO"]
    .round(1)
)

wip_setor["AGING_MEDIANO"] = (
    wip_setor["AGING_MEDIANO"]
    .round(1)
)

wip_setor = wip_setor.rename(
    columns={
        "Desc. Setor Atual": "SETOR",
    }
)


# ============================================================
# 20. GRÁFICO WIP + AGING POR SETOR
# ============================================================

st.subheader(
    "WIP e Aging por setor"
)

fig_wip = go.Figure()


# ------------------------------------------------------------
# Barras - WIP
# ------------------------------------------------------------

fig_wip.add_trace(
    go.Bar(
        x=wip_setor["SETOR"],
        y=wip_setor["PECAS"],
        name="Peças em WIP",
        text=wip_setor["PECAS"].map(lambda value: format_br_number(value, 0)),
        texttemplate="%{text}",
        textposition="outside",
        cliponaxis=False,
        yaxis="y",
        hovertemplate=(
            "<b>%{x}</b><br>"
            "WIP: %{y:,.0f} peças"
            "<extra></extra>"
        ),
    )
)


# ------------------------------------------------------------
# Linha - Aging médio
# ------------------------------------------------------------

fig_wip.add_trace(
    go.Scatter(
        x=wip_setor["SETOR"],
        y=wip_setor["AGING_MEDIO"],
        name="Aging médio",
        mode="lines+markers",
        yaxis="y2",
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Aging médio: %{y:.1f} dias"
            "<extra></extra>"
        ),
    )
)


fig_wip.update_layout(
    xaxis=dict(
        title="Setor",
        categoryorder="array",
        categoryarray=SETORES_WIP,
        tickangle=-35,
    ),
    yaxis=dict(
        title="Peças em WIP",
        rangemode="tozero",
    ),
    yaxis2=dict(
        title="Aging médio (dias)",
        overlaying="y",
        side="right",
        rangemode="tozero",
        showgrid=False,
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.08,
        xanchor="left",
        x=0,
    ),
    margin=dict(
        l=20,
        r=20,
        t=96,
        b=96,
    ),
    height=480,
    hovermode="closest",
)
apply_chart_theme(fig_wip)
fig_wip.update_layout(
    margin=dict(l=48, r=48, t=96, b=112),
    height=480,
    hoverlabel=dict(align="left", namelength=-1),
    separators=",.",
)

st.plotly_chart(
    fig_wip,
    width="stretch",
)


# ============================================================
# 21. TABELA WIP POR SETOR
# ============================================================

display_dataframe(
    wip_setor[["SETOR", "OFS", "PECAS", "AGING_MEDIO", "AGING_MEDIANO"]],
    labels={"SETOR": "Setor", "OFS": "OFs", "PECAS": "Peças", "AGING_MEDIO": "Aging médio (dias)", "AGING_MEDIANO": "Aging mediano (dias)"},
    number_formats={"OFS": 0, "PECAS": 0, "AGING_MEDIO": 1, "AGING_MEDIANO": 1},
    hide_index=True,
)


# ============================================================
# 22. DISTRIBUIÇÃO DO WIP POR AGING
# ============================================================

st.subheader(
    "Distribuição do WIP por Aging"
)

wip_aging = wip.copy()

wip_aging["FAIXA_AGING"] = pd.cut(
    wip_aging["AGING_SETOR_DIAS"],
    bins=[
        -1,
        2,
        5,
        10,
        20,
        float("inf"),
    ],
    labels=[
        "0–2 dias",
        "3–5 dias",
        "6–10 dias",
        "11–20 dias",
        "> 20 dias",
    ],
)

aging_faixa = (
    wip_aging
    .groupby(
        "FAIXA_AGING",
        observed=True,
        as_index=False,
    )
    .agg(
        OFS=(
            "OF",
            "nunique",
        ),
        PECAS=(
            "Qt Pend.",
            "sum",
        ),
    )
)


fig_aging = go.Figure()

fig_aging.add_trace(
    go.Bar(
        x=aging_faixa["FAIXA_AGING"],
        y=aging_faixa["PECAS"],
        name="Peças",
        text=aging_faixa["PECAS"].map(lambda value: format_br_number(value, 0)),
        texttemplate="%{text}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "%{y:,.0f} peças"
            "<extra></extra>"
        ),
    )
)

fig_aging.update_layout(
    xaxis=dict(
        title="Aging no setor",
    ),
    yaxis=dict(
        title="Peças em WIP",
        rangemode="tozero",
    ),
    showlegend=False,
    margin=dict(
        l=20,
        r=20,
        t=64,
        b=48,
    ),
    height=360,
)
apply_chart_theme(fig_aging)
fig_aging.update_layout(
    margin=dict(l=48, r=48, t=64, b=64),
    height=360,
    hovermode="closest",
    hoverlabel=dict(align="left", namelength=-1),
    separators=",.",
)

st.plotly_chart(
    fig_aging,
    width="stretch",
)


# ============================================================
# 23. WIP POR FASE
# ============================================================

st.subheader("WIP por fase")

ordem_fase = {
    "PRÉ-CORTE": 1,
    "PRODUÇÃO": 2,
}

wip_fase = (
    wip
    .groupby(
        "FASE",
        as_index=False,
    )
    .agg(
        OFS=(
            "OF",
            "nunique",
        ),
        PECAS=(
            "Qt Pend.",
            "sum",
        ),
        AGING_MEDIO=(
            "AGING_SETOR_DIAS",
            "mean",
        ),
        AGING_MEDIANO=(
            "AGING_SETOR_DIAS",
            "median",
        ),
    )
)

wip_fase["ORDEM"] = (
    wip_fase["FASE"]
    .map(ordem_fase)
)

wip_fase = (
    wip_fase
    .sort_values("ORDEM")
    .drop(columns="ORDEM")
)

wip_fase["AGING_MEDIO"] = (
    wip_fase["AGING_MEDIO"]
    .round(1)
)

wip_fase["AGING_MEDIANO"] = (
    wip_fase["AGING_MEDIANO"]
    .round(1)
)

display_dataframe(
    wip_fase,
    labels={"FASE": "Fase", "OFS": "OFs", "PECAS": "Peças", "AGING_MEDIO": "Aging médio (dias)", "AGING_MEDIANO": "Aging mediano (dias)"},
    number_formats={"OFS": 0, "PECAS": 0, "AGING_MEDIO": 1, "AGING_MEDIANO": 1},
    hide_index=True,
)


# ============================================================
# 24. SITUAÇÃO DOS PRAZOS
# ============================================================

# st.subheader(
#     "Situação dos prazos"
# )

# atrasadas = wip[
#     wip["STATUS_PRAZO"] == "ATRASADA"
# ].copy()

# vence_hoje = wip[
#     wip["STATUS_PRAZO"] == "VENCE HOJE"
# ].copy()

# no_prazo = wip[
#     wip["STATUS_PRAZO"] == "NO PRAZO"
# ].copy()

# sem_prazo = wip[
#     wip["STATUS_PRAZO"] == "SEM PRAZO"
# ].copy()


# c1, c2, c3, c4 = st.columns(4)

# c1.metric(
#     "OFs atrasadas",
#     format_number(
#         total_ofs(atrasadas)
#     ),
# )

# c2.metric(
#     "Vencem hoje",
#     format_number(
#         total_ofs(vence_hoje)
#     ),
# )

# c3.metric(
#     "No prazo",
#     format_number(
#         total_ofs(no_prazo)
#     ),
# )

# c4.metric(
#     "Sem prazo",
#     format_number(
#         total_ofs(sem_prazo)
#     ),
# )


# c1, c2, c3 = st.columns(3)

# c1.metric(
#     "Peças atrasadas",
#     format_number(
#         total_pecas(atrasadas)
#     ),
# )

# c2.metric(
#     "Peças vencendo hoje",
#     format_number(
#         total_pecas(vence_hoje)
#     ),
# )

# c3.metric(
#     "Peças no prazo",
#     format_number(
#         total_pecas(no_prazo)
#     ),
# )


# ============================================================
# 25. WIP POR SETOR E SITUAÇÃO DO PRAZO
# ============================================================

# st.subheader(
#     "WIP por setor e situação do prazo"
# )

# prazo_setor = (
#     wip
#     .groupby(
#         [
#             "ORDEM_FLUXO",
#             "Desc. Setor Atual",
#             "STATUS_PRAZO",
#         ],
#         as_index=False,
#     )
#     .agg(
#         PECAS=(
#             "Qt Pend.",
#             "sum",
#         )
#     )
#     .sort_values(
#         "ORDEM_FLUXO"
#     )
# )


# ordem_status = [
#     "NO PRAZO",
#     "VENCE HOJE",
#     "ATRASADA",
#     "SEM PRAZO",
# ]

# fig_prazo = go.Figure()

# for status in ordem_status:

#     dados_status = prazo_setor[
#         prazo_setor["STATUS_PRAZO"] == status
#     ]

#     if dados_status.empty:
#         continue

#     fig_prazo.add_trace(
#         go.Bar(
#             x=dados_status[
#                 "Desc. Setor Atual"
#             ],
#             y=dados_status[
#                 "PECAS"
#             ],
#             name=status.title(),
#             hovertemplate=(
#                 "<b>%{x}</b><br>"
#                 "%{y:,.0f} peças"
#                 "<extra></extra>"
#             ),
#         )
#     )


# fig_prazo.update_layout(
#     barmode="stack",
#     xaxis=dict(
#         title="Setor",
#         categoryorder="array",
#         categoryarray=SETORES_WIP,
#         tickangle=-35,
#     ),
#     yaxis=dict(
#         title="Peças em WIP",
#         rangemode="tozero",
#     ),
#     legend=dict(
#         orientation="h",
#         yanchor="bottom",
#         y=1.08,
#         xanchor="left",
#         x=0,
#     ),
#     margin=dict(
#         l=20,
#         r=20,
#         t=70,
#         b=80,
#     ),
#     hovermode="x unified",
# )

# st.plotly_chart(
#     fig_prazo,
#     width="stretch",
# )


# ============================================================
# 26. OFs COM MAIOR AGING NO SETOR
# ============================================================

st.subheader(
    "OFs com maior Aging no setor"
)

top_aging = (
    wip
    .sort_values(
        "AGING_SETOR_DIAS",
        ascending=False,
    )
    .head(20)
)

columns_top = [
    "OF",
    "Desc. Setor Atual",
    "Qt Pend.",
    "Data Setor",
    "AGING_SETOR_DIAS",
    "Prev. Término",
    "DIAS_PARA_PRAZO",
]

if "Desc. Tipo OP" in top_aging.columns:
    columns_top.insert(
        1,
        "Desc. Tipo OP",
    )

if "Desc. Coleção" in top_aging.columns:
    columns_top.insert(
        2,
        "Desc. Coleção",
    )


display_dataframe(
    top_aging[columns_top],
    labels={"OF": "OF", "Desc. Tipo OP": "Tipo OP", "Desc. Coleção": "Coleção", "Desc. Setor Atual": "Setor atual", "Qt Pend.": "Qt. pendente", "Data Setor": "Data setor", "AGING_SETOR_DIAS": "Aging setor (dias)", "Prev. Término": "Prev. término", "DIAS_PARA_PRAZO": "Dias p/ prazo"},
    number_formats={"Qt Pend.": 0, "AGING_SETOR_DIAS": 0, "DIAS_PARA_PRAZO": 0},
    date_formats={"Data Setor": "DD/MM/YYYY", "Prev. Término": "DD/MM/YYYY"},
    hide_index=True,
)


# ============================================================
# 27. DETALHAMENTO DAS OFs EM WIP
# ============================================================

st.subheader(
    "Detalhamento das OFs em WIP"
)

columns_detail = [
    "OF",
    "FASE",
    "Desc. Setor Atual",
    "Qt Orig.",
    "Qt Aprovada",
    "Qt Pend.",
    "Emissão",
    "Data Setor",
    "AGING_OF_DIAS",
    "AGING_SETOR_DIAS",
    "Prev. Término",
    "DIAS_PARA_PRAZO",
    "STATUS_PRAZO",
]

if "Desc. Tipo OP" in wip.columns:
    columns_detail.insert(
        1,
        "Desc. Tipo OP",
    )

if "Desc. Coleção" in wip.columns:
    columns_detail.insert(
        2,
        "Desc. Coleção",
    )


detail = (
    wip[
        columns_detail
    ]
    .sort_values(
        "AGING_SETOR_DIAS",
        ascending=False,
    )
)


display_dataframe(
    detail,
    labels={"OF": "OF", "Desc. Tipo OP": "Tipo OP", "Desc. Coleção": "Coleção", "FASE": "Fase", "Desc. Setor Atual": "Setor atual", "Qt Orig.": "Qt. original", "Qt Aprovada": "Qt. aprovada", "Qt Pend.": "Qt. pendente", "Emissão": "Emissão", "Data Setor": "Data setor", "AGING_OF_DIAS": "Aging OF (dias)", "AGING_SETOR_DIAS": "Aging setor (dias)", "Prev. Término": "Prev. término", "DIAS_PARA_PRAZO": "Dias p/ prazo", "STATUS_PRAZO": "Status prazo"},
    number_formats={"Qt Orig.": 0, "Qt Aprovada": 0, "Qt Pend.": 0, "AGING_OF_DIAS": 0, "AGING_SETOR_DIAS": 0, "DIAS_PARA_PRAZO": 0},
    date_formats={"Emissão": "DD/MM/YYYY", "Data Setor": "DD/MM/YYYY", "Prev. Término": "DD/MM/YYYY"},
    hide_index=True,
)


# ============================================================
# 28. REGISTROS FORA DO FLUXO
# ============================================================

fora_fluxo = df[
    df["FASE"] == "FORA DO FLUXO"
].copy()

if not fora_fluxo.empty:

    with st.expander(
        (
            "Setores fora do fluxo definido "
            f"({len(fora_fluxo):,.0f} registros)"
        ).replace(",", ".")
    ):

        resumo_fora = (
            fora_fluxo
            .groupby(
                "Desc. Setor Atual",
                dropna=False,
                as_index=False,
            )
            .agg(
                OFS=(
                    "OF",
                    "nunique",
                ),
                PECAS=(
                    "Qt Pend.",
                    "sum",
                ),
            )
            .sort_values(
                "OFS",
                ascending=False,
            )
        )

        display_dataframe(
            resumo_fora,
            labels={"Desc. Setor Atual": "Setor", "OFS": "OFs", "PECAS": "Peças"},
            number_formats={"OFS": 0, "PECAS": 0},
            hide_index=True,
        )
