"""Consulta estoque de produtos por coleção na API Excia."""

import asyncio
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from conn_excie_api import ExciaError, create_excia_client  # noqa: E402
from utils.charts import bar_chart  # noqa: E402
from utils.display import display_dataframe, format_br_number  # noqa: E402
from utils.shared import apply_theme  # noqa: E402


DEFAULT_DEPOSIT = "0000"
STOCK_TYPE = "P"


st.set_page_config(page_title="Estoque por coleção | PPCP", page_icon="📦", layout="wide")
apply_theme()
st.title("Estoque por coleção — API Excia")
st.caption(
    "Consulta produtos da coleção pela data informada e cruza suas referências "
    "com o estoque do depósito 0000."
)


def response_records(response: Any, endpoint: str) -> list[dict[str, Any]]:
    """Valida respostas de listagem sem supor wrappers não documentados."""
    if response is None:
        return []
    if isinstance(response, list) and all(isinstance(row, dict) for row in response):
        return response
    raise ValueError(
        f"Formato inesperado na resposta de {endpoint}; era esperada uma lista de objetos."
    )


def field_value(row: dict[str, Any], *names: str) -> Any:
    """Localiza um campo aceitando variações de caixa do nome da API."""
    by_casefold = {str(key).casefold(): value for key, value in row.items()}
    for name in names:
        value = by_casefold.get(name.casefold())
        if value is not None and str(value).strip() != "":
            return value
    return None


def normalized_code(value: Any) -> str:
    return str(value or "").strip().casefold()


def api_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        normalized = value.strip()
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        return float(normalized)
    return float(value)


@st.cache_data(ttl=3600, show_spinner=False)
def load_collection_options() -> pd.DataFrame:
    async def fetch() -> Any:
        async with create_excia_client() as client:
            return await client.get("/ColecaoLista", include_empresa=False)

    records = response_records(asyncio.run(fetch()), "/ColecaoLista")
    rows = []
    for record in records:
        code = field_value(record, "codigo")
        description = field_value(record, "descricao")
        if code is not None:
            rows.append({"codigo": str(code).strip(), "descricao": str(description or "").strip()})
    return (
        pd.DataFrame(rows, columns=["codigo", "descricao"])
        .drop_duplicates(subset=["codigo"])
        .sort_values(["codigo", "descricao"], kind="stable")
        .reset_index(drop=True)
    )


async def fetch_stock_data(collection_code: str, product_date: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with create_excia_client() as client:
        products = await client.paginate(
            "/Produto",
            params={
                "data": product_date.strftime("%d/%m/%Y") + " 00:00:00",
                "colecao": collection_code,
            },
            page_param="pagina",
            page_size=300,
            include_empresa=False,
        )
        if not all(isinstance(row, dict) for row in products):
            raise ValueError("Formato inesperado na resposta de /Produto.")

        product_references = {
            normalized_code(field_value(row, "codigo", "codreferencia", "referencia"))
            for row in products
        }
        product_references.discard("")
        if not product_references:
            return products, []

        # Uma consulta paginada única evita uma chamada de estoque por referência.
        stock = await client.paginate(
            "/Estoque",
            params={
                "tipo": STOCK_TYPE,
                "deposito": DEFAULT_DEPOSIT,
                "estoque": "0",
            },
            page_param="pagina",
            page_size=300,
            include_empresa=False,
        )
        if not all(isinstance(row, dict) for row in stock):
            raise ValueError("Formato inesperado na resposta de /Estoque.")

    return products, stock


def build_dataframes(
    collection_code: str,
    products: list[dict[str, Any]],
    stock_records: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    product_rows = []
    for product in products:
        reference = field_value(product, "codigo", "codreferencia", "referencia")
        if reference is None:
            continue
        product_rows.append(
            {
                "colecao": collection_code,
                "referencia": str(reference).strip(),
                "descricao": str(field_value(product, "descricao", "nome") or "").strip(),
            }
        )

    products_df = pd.DataFrame(
        product_rows,
        columns=["colecao", "referencia", "descricao"],
    )
    if not products_df.empty:
        products_df = (
            products_df.loc[products_df["referencia"].ne("")]
            .drop_duplicates()
            .reset_index(drop=True)
        )

    reference_keys = {
        normalized_code(reference)
        for reference in products_df.get("referencia", pd.Series(dtype="string"))
    }
    stock_rows = []
    quantity_fields = (
        "qtdprontaentrega",
        "quantidade",
        "qtd",
        "estoque",
        "saldo",
        "saldoestoque",
        "qtde",
        "disponivel",
    )

    for record in stock_records:
        # A documentação descreve codigo2 como referência; codigo é alternativa
        # para retornos que já identifiquem o produto diretamente por referência.
        reference = field_value(
            record,
            "codigo2",
            "referencia",
            "codreferencia",
            "codigo",
        )
        if reference is None or normalized_code(reference) not in reference_keys:
            continue

        quantity_value = field_value(record, *quantity_fields)
        if quantity_value is None:
            if products_df.empty:
                continue
            raise ValueError(
                "A resposta de /Estoque não contém um campo de quantidade reconhecido. "
                "Campos recebidos: " + ", ".join(str(key) for key in record.keys())
            )
        try:
            quantity = api_number(quantity_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("A API retornou uma quantidade de estoque inválida.") from exc

        reference = str(reference).strip()
        size = str(field_value(record, "tamanho", "tam", "grade", "seqtamanho") or "").strip()
        color = str(field_value(record, "cor", "desc_cor", "seqsortimento") or "").strip()
        stock_rows.append(
            {
                "colecao": collection_code,
                "referencia": reference,
                "grade": size,
                "cor": color,
                "sku": f"{reference}|{size}|{color}",
                "estoque_pronta_entrega": quantity,
            }
        )

    stock_df = pd.DataFrame(
        stock_rows,
        columns=[
            "colecao", "referencia", "grade", "cor", "sku",
            "estoque_pronta_entrega",
        ],
    )
    return products_df, stock_df


def build_reference_summary(
    products: pd.DataFrame,
    stock: pd.DataFrame,
) -> pd.DataFrame:
    if products.empty:
        return pd.DataFrame(
            columns=["referencia", "descricao", "estoque_pronta_entrega", "skus"]
        )

    reference_data = (
        products.groupby("referencia", as_index=False)
        .agg(descricao=("descricao", "first"))
    )
    if stock.empty:
        reference_data["estoque_pronta_entrega"] = pd.NA
        reference_data["skus"] = pd.NA
        return reference_data

    stock_summary = (
        stock.groupby("referencia", as_index=False)
        .agg(
            estoque_pronta_entrega=("estoque_pronta_entrega", "sum"),
            skus=("sku", "nunique"),
        )
    )
    return reference_data.merge(stock_summary, on="referencia", how="left")


st.sidebar.header("Filtros de estoque")
if st.sidebar.button("Atualizar lista de coleções"):
    load_collection_options.clear()

try:
    with st.spinner("Carregando coleções da API Excia..."):
        collections_df = load_collection_options()
except (ExciaError, ValueError) as exc:
    st.error(f"Não foi possível carregar as coleções: {exc}")
    st.stop()

if collections_df.empty:
    st.warning("A API não retornou coleções disponíveis.")
    st.stop()

with st.expander("Coleções disponíveis (código e descrição)"):
    st.dataframe(collections_df, hide_index=True, width="stretch")

collection_options = collections_df.to_dict("records")
selected_collection = st.selectbox(
    "Coleção",
    options=collection_options,
    format_func=lambda row: f"{row['codigo']} | {row['descricao']}",
    key="estoque_api_collection",
)

with st.form("consulta_estoque_api"):
    product_date = st.date_input(
        "Consultar produtos atualizados a partir de",
        value=datetime(2026, 1, 1).date(),
        format="DD/MM/YYYY",
        help="Parâmetro `data` obrigatório da API /Produto.",
    )
    submitted = st.form_submit_button("Buscar estoque", type="primary")

if submitted:
    st.session_state.pop("excia_stock_api_result", None)
    try:
        with st.spinner("Consultando produtos e estoque na API Excia..."):
            products, raw_stock = asyncio.run(
                fetch_stock_data(selected_collection["codigo"], product_date)
            )
        products_df, stock_df = build_dataframes(
            selected_collection["codigo"],
            products,
            raw_stock,
        )
        st.session_state["excia_stock_api_result"] = {
            "products": products_df,
            "stock": stock_df,
            "reference_summary": build_reference_summary(products_df, stock_df),
            "product_date": product_date,
            "collection": selected_collection,
            "stock_rows_returned": len(raw_stock),
        }
    except (ExciaError, ValueError) as exc:
        st.error(f"Não foi possível consultar o estoque: {exc}")

result = st.session_state.get("excia_stock_api_result")
if (
    result is not None
    and result["collection"].get("codigo") != selected_collection["codigo"]
):
    st.session_state.pop("excia_stock_api_result", None)
    result = None
if result is None:
    st.info("Selecione a coleção e a data e clique em **Buscar estoque**.")
    st.stop()

products_df = result["products"]
stock_df = result["stock"]
reference_summary = result["reference_summary"]
selected_references = st.sidebar.multiselect(
    "Referência",
    sorted(reference_summary["referencia"].dropna().unique().tolist()),
)
selected_grades = st.sidebar.multiselect(
    "Grade",
    sorted(stock_df["grade"].dropna().unique().tolist()) if not stock_df.empty else [],
)
selected_colors = st.sidebar.multiselect(
    "Cor",
    sorted(stock_df["cor"].dropna().unique().tolist()) if not stock_df.empty else [],
)
only_available = st.sidebar.checkbox("Mostrar somente SKUs com estoque", value=False)

filtered = stock_df.copy()
if selected_references:
    filtered = filtered.loc[filtered["referencia"].isin(selected_references)]
if selected_grades:
    filtered = filtered.loc[filtered["grade"].isin(selected_grades)]
if selected_colors:
    filtered = filtered.loc[filtered["cor"].isin(selected_colors)]
if only_available:
    filtered = filtered.loc[filtered["estoque_pronta_entrega"] > 0]

filtered_references = reference_summary.copy()
if selected_references:
    filtered_references = filtered_references.loc[
        filtered_references["referencia"].isin(selected_references)
    ]
if selected_grades or selected_colors or only_available:
    if filtered.empty:
        filtered_references = filtered_references.iloc[0:0]
    else:
        filtered_references = filtered_references.loc[
            filtered_references["referencia"].isin(filtered["referencia"].unique())
        ]

st.caption(
    f"Coleção: {result['collection']['codigo']} — {result['collection']['descricao']} · "
    f"Data usada em /Produto: {result['product_date'].strftime('%d/%m/%Y')} · "
    f"Depósito: {DEFAULT_DEPOSIT} · Tipo: {STOCK_TYPE}"
)
st.caption(
    f"Referências retornadas por /Produto: {format_br_number(len(products_df))} · "
    f"Linhas recebidas por /Estoque: {format_br_number(result['stock_rows_returned'])} · "
    f"Linhas de estoque correspondentes à coleção: {format_br_number(len(stock_df))}"
)

stock_total = filtered["estoque_pronta_entrega"].sum() if not filtered.empty else 0
sku_total = filtered["sku"].nunique() if not filtered.empty else 0
available_skus = (
    filtered.loc[filtered["estoque_pronta_entrega"] > 0, "sku"].nunique()
    if not filtered.empty else 0
)
matched_references = (
    stock_df["referencia"].nunique() if not stock_df.empty else 0
)
references_without_stock_row = max(reference_summary["referencia"].nunique() - matched_references, 0)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Peças em estoque", format_br_number(stock_total))
c2.metric("SKUs retornados", format_br_number(sku_total))
c3.metric("SKUs com saldo positivo", format_br_number(available_skus))
c4.metric("Referências sem linha no estoque", format_br_number(references_without_stock_row))

st.subheader("Estoque por referência")
if filtered_references.empty:
    st.info("Nenhuma referência encontrada com os filtros selecionados.")
else:
    chart_data = filtered_references.dropna(subset=["estoque_pronta_entrega"])
    if chart_data.empty:
        st.info("A API não retornou linhas de estoque para as referências consultadas.")
    else:
        chart_data = chart_data.sort_values("estoque_pronta_entrega", ascending=False)
        bar_chart(chart_data.head(25), x="referencia", y="estoque_pronta_entrega", y_title="Peças")

    display_dataframe(
        filtered_references.sort_values(
            "estoque_pronta_entrega",
            ascending=False,
            na_position="last",
        ),
        labels={
            "referencia": "Referência",
            "descricao": "Descrição do produto",
            "estoque_pronta_entrega": "Estoque pronta-entrega",
            "skus": "SKUs retornados",
        },
        number_formats={"estoque_pronta_entrega": 0, "skus": 0},
        hide_index=True,
    )

st.subheader("Detalhamento por SKU")
if filtered.empty:
    st.info("A API não retornou SKUs correspondentes aos filtros selecionados.")
else:
    sku_detail = filtered.sort_values(
        ["referencia", "cor", "grade"],
        ascending=[True, True, True],
    )
    display_dataframe(
        sku_detail,
        labels={
            "colecao": "Coleção",
            "referencia": "Referência",
            "grade": "Grade",
            "cor": "Cor",
            "sku": "SKU",
            "estoque_pronta_entrega": "Estoque pronta-entrega",
        },
        number_formats={"estoque_pronta_entrega": 0},
        hide_index=True,
    )
