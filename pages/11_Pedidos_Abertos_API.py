"""Consulta pedidos pendentes da API Excia e apresenta análises no Streamlit."""

import asyncio
from datetime import date
import os
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

PAGES_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PAGES_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from conn_excie_api import ExciaError, create_excia_client  # noqa: E402
from utils.shared import apply_theme  # noqa: E402
from utils.display import display_dataframe, format_br_number  # noqa: E402


COLLECTION_ALIASES = {
    "iv27": "in27",
}


st.set_page_config(
    page_title="Pedidos em aberto | PPCP",
    page_icon="🧾",
    layout="wide",
)
apply_theme()

st.title("Pedidos em aberto por coleção")
st.caption(
    "Consulta pedidos pendentes na API Excia e resume quantidades, valores, "
    "referências, SKUs e situação financeira."
)


def default_start_date() -> date:
    configured = os.getenv("EXCIA_PEDIDOS_DATA_INICIAL", "").strip()
    if configured:
        try:
            return datetime.strptime(configured, "%d/%m/%Y").date()
        except ValueError:
            st.warning(
                "EXCIA_PEDIDOS_DATA_INICIAL deve usar o formato DD/MM/AAAA."
            )
    return datetime.today().date()


def normalize_selected_collections(
    value: str,
    collections: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> set[str] | None:
    requested = {
        item.strip().casefold()
        for item in value.split(",")
        if item.strip()
    }
    if not requested:
        return None

    names_to_codes: dict[str, str] = {}
    for collection in collections:
        code = str(collection.get("codigo", "")).strip()
        description = str(collection.get("descricao", "")).strip()
        if code:
            names_to_codes[code.casefold()] = code
            if description:
                names_to_codes[description.casefold()] = code

    order_codes = {
        str(order.get("colecao", "")).strip()
        for order in orders
        if str(order.get("colecao", "")).strip()
    }
    names_to_codes.update({code.casefold(): code for code in order_codes})

    resolved: set[str] = set()
    unresolved: list[str] = []
    for name in requested:
        canonical = COLLECTION_ALIASES.get(name, name)
        code = names_to_codes.get(canonical)
        if code:
            resolved.add(code)
        else:
            unresolved.append(name)

    if unresolved:
        raise ValueError(
            "Coleções não encontradas na API: "
            + ", ".join(sorted(unresolved))
            + ". Use `python3 etl-pedidos-excia.py --listar-colecoes` "
            "para consultar os códigos disponíveis."
        )

    return resolved


def api_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        normalized = value.strip()
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        return float(normalized)
    return float(value)


def build_open_items_dataframe(
    payload: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for collection in payload.get("colecoes", []):
        collection_code = str(collection.get("codigo", "")).strip()
        collection_name = str(
            collection.get("descricao") or collection_code
        ).strip()

        for order in collection.get("pedidos", []):
            emitted_at = pd.to_datetime(
                order.get("dt_emissao") or order.get("dataemissao"),
                dayfirst=True,
                errors="coerce",
            )
            emission_date = (
                emitted_at.normalize()
                if not pd.isna(emitted_at)
                else pd.NaT
            )

            order_number = str(order.get("numero") or "").strip()
            finance_code = str(order.get("financeiro", "")).strip()
            if finance_code == "0":
                finance_status = "BLOQUEADO"
            elif finance_code == "1":
                finance_status = "LIBERADO"
            else:
                finance_status = "NÃO INFORMADO"

            for item in order.get("itens", []):
                try:
                    # No retorno de BuscarPedido, `qtde` representa o saldo
                    # atual; itens faturados aparecem com qtde igual a zero.
                    open_quantity = max(api_number(item.get("qtde")), 0)
                    unit_price_value = item.get("preco_orig")
                    if unit_price_value is None:
                        unit_price_value = item.get("preco") or 0
                    unit_price = api_number(unit_price_value)
                except (TypeError, ValueError):
                    continue

                if open_quantity <= 0:
                    continue

                reference = str(item.get("codigo") or "").strip()
                size = str(item.get("tam") or "").strip()
                color = str(
                    item.get("desc_cor") or item.get("cor") or ""
                ).strip()

                rows.append(
                    {
                        "data_emissao": emission_date,
                        "codcolecao": collection_code,
                        "colecao": collection_name,
                        "pedido": order_number,
                        "referencia": reference,
                        "produto": str(item.get("descricao") or "").strip(),
                        "grade": size,
                        "cor": color,
                        "sku": f"{reference}|{size}|{color}",
                        "quantidade_em_aberto": open_quantity,
                        "valor_unitario": unit_price,
                        "valor_em_aberto": open_quantity * unit_price,
                        "financeiro": finance_status,
                    }
                )

    return pd.DataFrame(
        rows,
        columns=[
            "data_emissao",
            "codcolecao",
            "colecao",
            "pedido",
            "referencia",
            "produto",
            "grade",
            "cor",
            "sku",
            "quantidade_em_aberto",
            "valor_unitario",
            "valor_em_aberto",
            "financeiro",
        ],
    )


def build_daily_collection_dataframe(items: pd.DataFrame) -> pd.DataFrame:
    if items.empty:
        return pd.DataFrame(
            columns=[
                "data_emissao", "codcolecao", "colecao",
                "quantidade_em_aberto", "valor_em_aberto",
            ]
        )

    dated_items = items.loc[items["data_emissao"].notna()]
    if dated_items.empty:
        return pd.DataFrame(
            columns=[
                "data_emissao", "codcolecao", "colecao",
                "quantidade_em_aberto", "valor_em_aberto",
            ]
        )

    return (
        dated_items.groupby(
            ["data_emissao", "codcolecao", "colecao"],
            as_index=False,
        )
        .agg(
            quantidade_em_aberto=("quantidade_em_aberto", "sum"),
            valor_em_aberto=("valor_em_aberto", "sum"),
        )
        .sort_values(["data_emissao", "colecao"])
        .reset_index(drop=True)
    )


def build_ranking(
    items: pd.DataFrame,
    group_by: str,
    *,
    include_product_description: bool = False,
) -> pd.DataFrame:
    ranked_items = items.loc[items[group_by].fillna("").astype(str).str.strip().ne("")]
    group_columns = [group_by]
    if include_product_description:
        group_columns.append("produto")
    if ranked_items.empty:
        return pd.DataFrame(
            columns=[
                *group_columns,
                "pedidos",
                "quantidade_em_aberto",
                "valor_em_aberto",
            ]
        )
    ranking = (
        ranked_items.groupby(group_columns, as_index=False, dropna=False)
        .agg(
            pedidos=("pedido", "nunique"),
            quantidade_em_aberto=("quantidade_em_aberto", "sum"),
            valor_em_aberto=("valor_em_aberto", "sum"),
        )
    )
    return ranking.sort_values(
        ["quantidade_em_aberto", "valor_em_aberto"],
        ascending=[False, False],
    ).reset_index(drop=True)


async def fetch_json_payload(
    start_date: str,
    collection_filter: str,
) -> dict[str, Any]:
    async with create_excia_client() as client:
        orders = await client.paginate(
            "/PedidoLista",
            params={
                "dt_emissao_ini": start_date,
                "situacao": "P",
            },
            page_param="pagina",
            page_size=300,
        )
        if not isinstance(orders, list) or any(
            not isinstance(order, dict)
            for order in orders
        ):
            raise ValueError(
                "A API retornou um formato inesperado em PedidoLista."
            )

        collections = await client.listar_colecoes()
        if not isinstance(collections, list) or any(
            not isinstance(collection, dict)
            for collection in collections
        ):
            raise ValueError(
                "A API retornou um formato inesperado em ColecaoLista."
            )

        selected_codes = normalize_selected_collections(
            collection_filter,
            collections,
            orders,
        )
        if selected_codes is not None:
            orders = [
                order
                for order in orders
                if str(order.get("colecao", "")).strip() in selected_codes
            ]

        collection_names = {
            str(collection.get("codigo", "")).strip(): str(
                collection.get("descricao", "")
            ).strip()
            for collection in collections
            if str(collection.get("codigo", "")).strip()
        }

        semaphore = asyncio.Semaphore(5)

        async def fetch_detail(order: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            number = order.get("numero")
            if number is None or not str(number).strip():
                raise ValueError(
                    "Pedido retornado sem o campo 'numero'."
                )
            async with semaphore:
                response = await client.buscar_pedido(number)
            if isinstance(response, list) and response and isinstance(response[0], dict):
                detail = response[0]
            elif isinstance(response, dict):
                detail = response
            else:
                raise ValueError(
                    f"Formato inesperado ao consultar o pedido {number}."
                )
            return order, detail

        pairs = await asyncio.gather(
            *(fetch_detail(order) for order in orders)
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for order, detail in pairs:
        code = str(
            detail.get("colecao") or order.get("colecao") or ""
        ).strip()
        grouped.setdefault(code, []).append({**order, **detail})

    result_collections = [
        {
            "codigo": code,
            "descricao": collection_names.get(code, code),
            "pedidos": grouped[code],
        }
        for code in sorted(grouped)
    ]

    return {
        "data_emissao_inicial": start_date,
        "situacao_consultada": "P (pendente)",
        "quantidade_pedidos": sum(
            len(collection["pedidos"])
            for collection in result_collections
        ),
        "colecoes": result_collections,
    }


st.subheader("Parâmetros da consulta")
with st.form("consulta_pedidos_excia"):
    start_date = st.date_input(
        "Pedidos emitidos a partir de",
        value=default_start_date(),
        format="DD/MM/YYYY",
    )
    collection_filter = st.text_input(
        "Coleções",
        value=os.getenv("EXCIA_PEDIDOS_COLECOES", ""),
        placeholder="AV27, IV27 (em branco consulta todas)",
        help=(
            "Informe códigos ou descrições separados por vírgula. "
            "IV27 é aceito como atalho para IN27 (INVERNO 27)."
        ),
    )
    submitted = st.form_submit_button(
        "Consultar pedidos",
        type="primary",
    )

if submitted:
    formatted_date = start_date.strftime("%d/%m/%Y")
    st.session_state.pop("excia_open_orders_data", None)
    try:
        with st.spinner("Consultando pedidos e itens na API Excia..."):
            payload = asyncio.run(
                fetch_json_payload(
                    formatted_date,
                    collection_filter,
                )
            )
        open_items = build_open_items_dataframe(payload)
        st.session_state["excia_open_orders_data"] = {
            "items": open_items,
            "daily": build_daily_collection_dataframe(open_items),
            "orders_count": sum(
                len(collection.get("pedidos", []))
                for collection in payload.get("colecoes", [])
            ),
            "collections_count": len(payload.get("colecoes", [])),
        }
    except (ExciaError, ValueError) as exc:
        st.error(f"Não foi possível consultar os pedidos: {exc}")

query_data = st.session_state.get("excia_open_orders_data")
if query_data is not None:
    open_items = query_data["items"]
    daily_collection = query_data["daily"]
    orders_count = query_data["orders_count"]
    total_pieces = open_items["quantidade_em_aberto"].sum()
    total_value = open_items["valor_em_aberto"].sum()
    blocked_value = open_items.loc[
        open_items["financeiro"].eq("BLOQUEADO"), "valor_em_aberto"
    ].sum()
    released_value = open_items.loc[
        open_items["financeiro"].eq("LIBERADO"), "valor_em_aberto"
    ].sum()
    unknown_finance_value = open_items.loc[
        open_items["financeiro"].eq("NÃO INFORMADO"), "valor_em_aberto"
    ].sum()

    st.caption(
        f"Pedidos retornados: {format_br_number(orders_count)} · "
        f"Coleções: {format_br_number(query_data['collections_count'])}"
    )

    kpis = st.columns(4)
    kpis[0].metric("Pedidos em aberto", format_br_number(orders_count))
    kpis[1].metric("Peças em aberto", format_br_number(total_pieces))
    kpis[2].metric("Valor em aberto", f"R$ {format_br_number(total_value, 2)}")
    kpis[3].metric("Bloqueado no financeiro", f"R$ {format_br_number(blocked_value, 2)}")

    kpis = st.columns(4)
    kpis[0].metric(
        "Liberado no financeiro",
        f"R$ {format_br_number(released_value, 2)}",
    )
    kpis[1].metric(
        "Financeiro não informado",
        f"R$ {format_br_number(unknown_finance_value, 2)}",
    )

    reference_ranking = build_ranking(
        open_items,
        "referencia",
        include_product_description=True,
    )
    sku_ranking = build_ranking(
        open_items,
        "sku",
        include_product_description=True,
    )
    top_reference = (
        reference_ranking.iloc[0] if not reference_ranking.empty else None
    )
    top_sku = sku_ranking.iloc[0] if not sku_ranking.empty else None
    kpis[2].metric(
        "Referência mais vendida*",
        str(top_reference["referencia"])
        if top_reference is not None else "—",
        f"{format_br_number(top_reference['quantidade_em_aberto'])} peças"
        if top_reference is not None
        else None,
    )
    kpis[3].metric(
        "SKU mais vendido*",
        str(top_sku["sku"]) if top_sku is not None else "—",
        f"{format_br_number(top_sku['quantidade_em_aberto'])} peças"
        if top_sku is not None
        else None,
    )
    st.caption(
        "* Ranking por quantidade atualmente em aberto. Valores financeiros "
        "calculados como saldo (`qtde`) × preço unitário (`preco_orig`, com "
        "`preco` como alternativa). `financeiro=0` significa bloqueado e "
        "`financeiro=1` liberado; outros valores ficam não informados."
    )

    st.subheader("Valor de peças em aberto por dia e coleção")
    st.caption(
        "O valor diário usa a data de emissão do pedido e o saldo atual "
        "informado pela API."
    )

    if daily_collection.empty:
        st.info(
            "Não há itens com saldo em aberto e data de emissão válida "
            "para os filtros selecionados."
        )
    else:
        chart_data = daily_collection.pivot(
            index="data_emissao",
            columns="colecao",
            values="valor_em_aberto",
        ).fillna(0)
        st.line_chart(chart_data, y_label="Valor em aberto (R$)")
        display_dataframe(
            daily_collection,
            labels={
                "data_emissao": "Data de emissão",
                "codcolecao": "Código da coleção",
                "colecao": "Coleção",
                "quantidade_em_aberto": "Peças em aberto",
                "valor_em_aberto": "Valor em aberto (R$)",
            },
            number_formats={
                "quantidade_em_aberto": 0,
                "valor_em_aberto": 2,
            },
            date_formats={"data_emissao": "DD/MM/YYYY"},
            hide_index=True,
        )

    reference_filter = st.text_input(
        "Filtrar tabelas por referência",
        placeholder="Digite parte ou o código completo da referência",
        help=(
            "A busca atualiza as tabelas de referências e SKUs. "
            "Os indicadores gerais permanecem referentes à consulta completa."
        ),
    ).strip()
    ranking_items = open_items
    if reference_filter:
        ranking_items = open_items.loc[
            open_items["referencia"]
            .astype(str)
            .str.contains(reference_filter, case=False, regex=False, na=False)
        ]
    filtered_reference_ranking = build_ranking(
        ranking_items,
        "referencia",
        include_product_description=True,
    )
    filtered_sku_ranking = build_ranking(
        ranking_items,
        "sku",
        include_product_description=True,
    )

    st.subheader("Referências mais vendidas")
    if filtered_reference_ranking.empty:
        st.info("Nenhuma referência corresponde ao filtro.")
    else:
        display_dataframe(
            filtered_reference_ranking,
            labels={
                "referencia": "Referência",
                "produto": "Descrição do produto",
                "pedidos": "Pedidos",
                "quantidade_em_aberto": "Peças em aberto",
                "valor_em_aberto": "Valor em aberto (R$)",
            },
            number_formats={
                "pedidos": 0,
                "quantidade_em_aberto": 0,
                "valor_em_aberto": 2,
            },
            hide_index=True,
        )

    st.subheader("SKUs mais vendidos (referência | grade | cor)")
    if filtered_sku_ranking.empty:
        st.info("Nenhum SKU corresponde ao filtro.")
    else:
        display_dataframe(
            filtered_sku_ranking,
            labels={
                "sku": "SKU",
                "produto": "Descrição do produto",
                "pedidos": "Pedidos",
                "quantidade_em_aberto": "Peças em aberto",
                "valor_em_aberto": "Valor em aberto (R$)",
            },
            number_formats={
                "pedidos": 0,
                "quantidade_em_aberto": 0,
                "valor_em_aberto": 2,
            },
            hide_index=True,
        )

    st.subheader("Saldo em aberto por coleção e financeiro")
    if open_items.empty:
        st.info("A consulta não retornou itens com saldo em aberto.")
    else:
        finance_summary = (
            open_items.groupby(["colecao", "financeiro"], as_index=False)
            .agg(
                pedidos=("pedido", "nunique"),
                pecas=("quantidade_em_aberto", "sum"),
                valor=("valor_em_aberto", "sum"),
            )
            .sort_values(["colecao", "financeiro"])
        )
        display_dataframe(
            finance_summary,
            labels={
                "colecao": "Coleção",
                "financeiro": "Financeiro",
                "pedidos": "Pedidos",
                "pecas": "Peças em aberto",
                "valor": "Valor em aberto (R$)",
            },
            number_formats={"pedidos": 0, "pecas": 0, "valor": 2},
            hide_index=True,
        )
