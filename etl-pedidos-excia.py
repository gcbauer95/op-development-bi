"""Consulta pedidos pendentes na API Excia e gera Excel por coleção.

Configuração obrigatória no ambiente ou em ``.env``:
    EXCIA_BASE_URL
    EXCIA_TOKEN
    EXCIA_EMPRESA
    EXCIA_PEDIDOS_DATA_INICIAL (DD/MM/AAAA)

Execução:
    python etl-pedidos-excia.py
    python etl-pedidos-excia.py --data-inicial 01/01/2024
    python etl-pedidos-excia.py --colecoes AV27,IV27

A API lista pedidos a partir de uma data inicial e limita cada página a
300 registros. O script busca o detalhe de cada pedido pendente e salva
um Excel com resumo por coleção, pedidos por referência e itens por SKU.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from conn_excie_api import ExciaClient, ExciaError, create_excia_client


OUTPUT_DIR = Path("processed")
OUTPUT_FILE = OUTPUT_DIR / "pedidos-em-aberto-por-colecao.xlsx"
PAGE_SIZE = 300
COLLECTION_ALIASES = {
    "iv27": "in27",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consulta pedidos pendentes na API Excia e gera um Excel."
    )
    parser.add_argument(
        "--data-inicial",
        help=(
            "Data inicial de emissão no formato DD/MM/AAAA. "
            "Se omitida, usa EXCIA_PEDIDOS_DATA_INICIAL do .env."
        ),
    )
    parser.add_argument(
        "--colecoes",
        help=(
            "Códigos ou descrições de coleção separados por vírgula. "
            "Se omitido, inclui todas as coleções retornadas pela API."
        ),
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=OUTPUT_FILE,
        help=f"Caminho do Excel gerado (padrão: {OUTPUT_FILE}).",
    )
    parser.add_argument(
        "--listar-colecoes",
        action="store_true",
        help="Lista os códigos e descrições de coleção retornados pela API.",
    )
    return parser.parse_args()


def resolve_start_date(argument: str | None) -> str:
    value = (
        argument
        or os.getenv("EXCIA_PEDIDOS_DATA_INICIAL")
        or ""
    ).strip()

    if not value:
        raise ValueError(
            "Informe --data-inicial ou configure "
            "EXCIA_PEDIDOS_DATA_INICIAL no .env. "
            "A API Excia exige uma data inicial para listar pedidos."
        )

    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(
            "A data inicial deve estar no formato DD/MM/AAAA."
        ) from exc

    return value


def parse_collections(argument: str | None) -> set[str] | None:
    raw_value = argument or os.getenv("EXCIA_PEDIDOS_COLECOES")

    if not raw_value or not raw_value.strip():
        return None

    values = {
        value.strip().casefold()
        for value in raw_value.split(",")
        if value.strip()
    }
    normalized = {
        COLLECTION_ALIASES.get(value, value)
        for value in values
    }
    return normalized or None


def as_records(value: Any, *, resource: str) -> list[dict[str, Any]]:
    """Valida o formato de lista usado nos endpoints de consulta da Excia."""

    if value is None:
        return []

    if isinstance(value, dict):
        value = [value]

    if not isinstance(value, list) or any(
        not isinstance(record, dict)
        for record in value
    ):
        raise ValueError(
            f"Formato inesperado na resposta de {resource}; "
            "era esperada uma lista de objetos."
        )

    return value


def api_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        normalized = value.strip()
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        return float(normalized)
    return float(value)


async def fetch_pending_orders(
    client: ExciaClient,
    start_date: str,
) -> list[dict[str, Any]]:
    return await client.paginate(
        "/PedidoLista",
        params={
            "dt_emissao_ini": start_date,
            "situacao": "P",
        },
        page_param="pagina",
        page_size=PAGE_SIZE,
    )


async def fetch_order_details(
    client: ExciaClient,
    order: dict[str, Any],
) -> dict[str, Any]:
    number = order.get("numero")
    if number is None or not str(number).strip():
        raise ValueError(
            "Pedido retornado por PedidoLista sem o campo 'numero'."
        )

    detail = as_records(
        await client.buscar_pedido(number),
        resource=f"BuscarPedido ({number})",
    )
    if not detail:
        raise ValueError(
            f"A API não retornou detalhe para o pedido {number}."
        )

    return detail[0]


def select_collections(
    orders: list[dict[str, Any]],
    collections: list[dict[str, Any]],
    selected: set[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Filtra por código ou descrição e resolve o nome da coleção."""

    collection_names: dict[str, str] = {}
    selection_codes: set[str] = set()
    known_collection_names: set[str] = set()

    for collection in collections:
        code = str(collection.get("codigo", "")).strip()
        description = str(collection.get("descricao", "")).strip()
        if code:
            known_collection_names.add(code.casefold())
            if description:
                known_collection_names.add(description.casefold())
            collection_names[code] = description or code
            if selected and (
                code.casefold() in selected
                or description.casefold() in selected
            ):
                selection_codes.add(code)

    if selected:
        # Algumas instalações retornam o código da coleção diretamente em
        # PedidoLista, mas não incluem esse valor em ColecaoLista.
        order_codes = {
            str(order.get("colecao", "")).strip()
            for order in orders
            if str(order.get("colecao", "")).strip()
        }
        order_codes_by_casefold = {
            code.casefold(): code
            for code in order_codes
        }
        unmatched = selected - known_collection_names
        for collection in unmatched.copy():
            direct_code = order_codes_by_casefold.get(collection)
            if direct_code:
                selection_codes.add(direct_code)
                unmatched.remove(collection)
        if unmatched:
            print(
                "Aviso: coleção(ões) sem correspondência no cadastro nem "
                "nos pedidos retornados: "
                + ", ".join(sorted(unmatched)),
                file=sys.stderr,
            )

    filtered = []
    for order in orders:
        code = str(order.get("colecao", "")).strip()
        if selected is None or code.casefold() in {
            selected_code.casefold()
            for selected_code in selection_codes
        }:
            filtered.append(order)

    return filtered, collection_names


def parse_api_date(value: Any) -> pd.Timestamp | pd.NaT:
    return pd.to_datetime(
        value,
        format="%d/%m/%Y",
        errors="coerce",
    )


def build_dataframes(
    orders: list[dict[str, Any]],
    details: list[dict[str, Any]],
    collection_names: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    order_rows: list[dict[str, Any]] = []
    item_rows: list[dict[str, Any]] = []

    for order, detail in zip(orders, details, strict=True):
        order_number = str(detail.get("numero") or order.get("numero") or "").strip()
        collection_code = str(
            detail.get("colecao") or order.get("colecao") or ""
        ).strip()
        collection_name = collection_names.get(
            collection_code,
            collection_code,
        )

        item_records = as_records(
            detail.get("itens", []),
            resource=f"itens do pedido {order_number}",
        )

        open_items = []
        for item in item_records:
            open_quantity = max(api_number(item.get("qtde")), 0)
            invoiced = api_number(item.get("faturado"))
            cancelled = api_number(item.get("cancelado"))
            requested = open_quantity + invoiced + cancelled
            if open_quantity <= 0:
                continue

            reference = str(item.get("codigo") or "").strip()
            size = str(item.get("tam") or "").strip()
            color = str(
                item.get("desc_cor") or item.get("cor") or ""
            ).strip()
            unit_price_value = item.get("preco_orig")
            if unit_price_value is None:
                unit_price_value = item.get("preco") or 0
            unit_price = api_number(unit_price_value)
            open_items.append(
                {
                    "referencia": reference,
                    "nomeproduto": str(item.get("descricao") or "").strip(),
                    "qtdepedida": requested,
                    "qtdesaldo": open_quantity,
                    "qtdefaturado": invoiced,
                    "qtdecancelada": cancelled,
                    "valorunitariobruto": unit_price,
                    "grade": size,
                    "cor": color,
                    "codpedido": order_number,
                    "sku": f"{reference}|{size}|{color}",
                    "valor_total_pedido": requested * unit_price,
                    "valor_em_aberto": open_quantity * unit_price,
                }
            )

        if not open_items:
            continue

        notes = as_records(
            detail.get("notas", []),
            resource=f"notas do pedido {order_number}",
        )
        latest_note = max(
            notes,
            key=lambda note: parse_api_date(note.get("dt_emissao"))
            if not pd.isna(parse_api_date(note.get("dt_emissao")))
            else pd.Timestamp.min,
            default={},
        )

        common = {
            "codcolecao": collection_code,
            "colecao_descricao": collection_name,
            "dataemissao": parse_api_date(
                detail.get("dt_emissao") or order.get("dt_emissao")
            ),
            "codcliente": str(detail.get("codcli") or order.get("codcli") or "").strip(),
            "nomecliente": str(detail.get("nome") or order.get("nome") or "").strip(),
            "codpedido": order_number,
            "dataprevfaturamento": parse_api_date(
                detail.get("entrega") or order.get("entrega")
            ),
            "situacaopedido": "PENDENTE",
            "dataultimanf": parse_api_date(latest_note.get("dt_emissao")),
            "numeroultimanf": str(latest_note.get("fatura") or "").strip(),
            "bloq_fin": (
                "BLOQUEADO"
                if str(detail.get("financeiro", order.get("financeiro", "1"))).strip() == "0"
                else "LIBERADO"
            ),
            "bloq_com": (
                "BLOQUEADO"
                if str(detail.get("bloqueio", order.get("bloqueio", "1"))).strip() == "0"
                else "LIBERADO"
            ),
            "pagto": str(detail.get("pgto") or order.get("pgto") or "").strip(),
        }

        # A base de cabeçalho atual do dashboard possui uma linha por
        # pedido + referência. Consolida os tamanhos e cores nessa chave.
        by_reference: dict[str, dict[str, Any]] = {}
        for item in open_items:
            reference = item["referencia"]
            summary = by_reference.setdefault(
                reference,
                {
                    "codproduto": reference,
                    "quantidade": 0.0,
                    "quantidade_aberta": 0.0,
                },
            )
            summary["quantidade"] += item["qtdepedida"]
            summary["quantidade_aberta"] += item["qtdesaldo"]

        for reference_row in by_reference.values():
            order_rows.append(
                {
                    **common,
                    **reference_row,
                }
            )

        item_rows.extend(
            {
                **common,
                **item,
            }
            for item in open_items
        )

    orders_df = pd.DataFrame(order_rows)
    items_df = pd.DataFrame(item_rows)

    if orders_df.empty:
        orders_df = pd.DataFrame(
            columns=[
                "codcolecao", "colecao_descricao", "dataemissao", "codcliente",
                "nomecliente", "codproduto", "quantidade", "quantidade_aberta",
                "codpedido", "dataprevfaturamento", "situacaopedido", "dataultimanf",
                "numeroultimanf", "bloq_fin", "bloq_com", "pagto",
            ]
        )
    if items_df.empty:
        items_df = pd.DataFrame(
            columns=[
                "referencia", "nomeproduto", "qtdepedida", "qtdesaldo",
                "qtdefaturado", "qtdecancelada", "valorunitariobruto", "grade", "cor",
                "codpedido", "sku", "valor_total_pedido", "valor_em_aberto",
            ]
        )

    return orders_df, items_df, make_collection_summary(orders_df, items_df)


def make_collection_summary(
    orders: pd.DataFrame,
    items: pd.DataFrame,
) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(
            columns=[
                "codcolecao", "colecao_descricao", "situacaopedido",
                "pedidos", "referencias", "quantidade_em_aberto", "valor_em_aberto",
            ]
        )

    order_summary = (
        orders.groupby(
            ["codcolecao", "colecao_descricao", "situacaopedido"],
            as_index=False,
        )
        .agg(
            pedidos=("codpedido", "nunique"),
            referencias=("codproduto", "nunique"),
            quantidade_em_aberto=("quantidade_aberta", "sum"),
        )
    )

    if items.empty:
        value_summary = pd.DataFrame(
            columns=["codcolecao", "valor_em_aberto"]
        )
    elif "codcolecao" in items.columns:
        value_summary = (
            items.groupby("codcolecao", as_index=False)
            .agg(valor_em_aberto=("valor_em_aberto", "sum"))
        )
    else:
        value_summary = (
            items.merge(
                orders[["codpedido", "codcolecao"]].drop_duplicates(),
                on="codpedido",
                how="left",
            )
            .groupby("codcolecao", as_index=False)
            .agg(valor_em_aberto=("valor_em_aberto", "sum"))
        )

    return (
        order_summary.merge(value_summary, on="codcolecao", how="left")
        .assign(valor_em_aberto=lambda frame: frame["valor_em_aberto"].fillna(0))
        .sort_values(["codcolecao", "situacaopedido"])
        .reset_index(drop=True)
    )


def save_excel(
    summary: pd.DataFrame,
    orders: pd.DataFrame,
    items: pd.DataFrame,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
        datetime_format="dd/mm/yyyy",
    ) as writer:
        summary.to_excel(writer, index=False, sheet_name="Resumo")
        orders.to_excel(writer, index=False, sheet_name="Pedidos")
        items.to_excel(writer, index=False, sheet_name="Itens")

        for worksheet in writer.sheets.values():
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions


async def run(
    start_date: str,
    selected: set[str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    async with create_excia_client() as client:
        pending_orders = as_records(
            await fetch_pending_orders(client, start_date),
            resource="PedidoLista",
        )
        collections = as_records(
            await client.listar_colecoes(),
            resource="ColecaoLista",
        )
        pending_orders, collection_names = select_collections(
            pending_orders,
            collections,
            selected,
        )

        semaphore = asyncio.Semaphore(5)

        async def limited_detail(order: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await fetch_order_details(client, order)

        details = await asyncio.gather(
            *(limited_detail(order) for order in pending_orders)
        )

    return build_dataframes(
        pending_orders,
        details,
        collection_names,
    )


async def fetch_collection_catalog() -> list[dict[str, Any]]:
    async with create_excia_client() as client:
        return as_records(
            await client.listar_colecoes(),
            resource="ColecaoLista",
        )


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.listar_colecoes:
        try:
            collections = asyncio.run(fetch_collection_catalog())
        except ExciaError as exc:
            raise SystemExit(
                f"Falha ao consultar coleções na API Excia: {exc}"
            ) from exc

        print("Código\tDescrição")
        for collection in sorted(
            collections,
            key=lambda row: str(row.get("codigo", "")),
        ):
            print(
                f"{str(collection.get('codigo', '')).strip()}\t"
                f"{str(collection.get('descricao', '')).strip()}"
            )
        return

    start_date = resolve_start_date(args.data_inicial)
    selected = parse_collections(args.colecoes)

    try:
        orders, items, summary = asyncio.run(
            run(start_date, selected)
        )
    except ExciaError as exc:
        raise SystemExit(f"Falha na consulta à API Excia: {exc}") from exc

    save_excel(summary, orders, items, args.saida)
    print(f"Pedidos em aberto consultados desde {start_date}.")
    print(f"Pedidos: {orders['codpedido'].nunique():,}")
    print(f"Itens em aberto: {len(items):,}")
    print(f"Excel gerado: {args.saida}")


if __name__ == "__main__":
    main()
