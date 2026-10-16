"""ETL das vendas e itens de pedidos de múltiplas coleções.

Lê os dois Excel exportados do ERP, normaliza os tipos, permite processar
uma ou várias coleções, cria a chave de SKU (referência + grade + cor),
grava cópias tratadas em ``processed`` e arquivos Parquet para carga
posterior no Streamlit.

Configuração:
    COLLECTIONS = None
        Processa todas as coleções encontradas no arquivo.

    COLLECTIONS = ["AV27", "IV27"]
        Processa apenas as coleções informadas.
"""

from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURAÇÕES
# ============================================================

# None = todas as coleções disponíveis.
#
# Exemplos:
# COLLECTIONS = None
# COLLECTIONS = ["AV27"]
# COLLECTIONS = ["AV27", "IV27"]
# COLLECTIONS = ["AV27", "IV27", "AV26"]

COLLECTIONS: list[str] | None = None

RAW_SALES = Path("raw/pedidos-cabecalho-1510.xlsx")
RAW_ITEMS = Path("raw/pedidos-detalhado-1510.xlsx")

PROCESSED_DIR = Path("processed")
PARQUET_DIR = Path("parquet")


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def clean_text(
    series: pd.Series,
    *,
    upper: bool = False,
) -> pd.Series:
    """Remove espaços e opcionalmente converte texto para maiúsculas."""

    result = (
        series
        .astype("string")
        .str.strip()
    )

    return (
        result.str.upper()
        if upper
        else result
    )


def normalize_collections(
    collections: list[str] | None,
) -> list[str] | None:
    """Normaliza a lista de coleções configuradas."""

    if collections is None:
        return None

    normalized = [
        str(collection).strip().upper()
        for collection in collections
        if str(collection).strip()
    ]

    # Remove duplicidades mantendo a ordem.
    return list(dict.fromkeys(normalized))


def read_source(path: Path) -> pd.DataFrame:
    """Lê a primeira aba do Excel exportado pelo ERP."""

    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    # As exportações possuem abas auxiliares vazias.
    # A primeira aba contém os dados relevantes.
    return pd.read_excel(
        path,
        sheet_name=0,
    )


# ============================================================
# PREPARAÇÃO DA BASE DE PEDIDOS
# ============================================================

def prepare_sales(
    df: pd.DataFrame,
    collections: list[str] | None = None,
) -> pd.DataFrame:
    """Normaliza e filtra a base principal de pedidos."""

    required = {
        "codcolecao",
        "dataemissao",
        "codcliente",
        "nomecliente",
        "codproduto",
        "quantidade",
        "codpedido",
        "dataprevfaturamento",
        "situacaopedido",
        "dataultimanf",
        "numeroultimanf",
        "bloq_fin",
        "bloq_com",
        "pagto",
    }

    missing = required.difference(df.columns)

    if missing:
        raise ValueError(
            "Colunas ausentes na base de pedidos: "
            f"{sorted(missing)}"
        )

    result = df.copy()

    # --------------------------------------------------------
    # Normalização textual
    # --------------------------------------------------------

    result["codcolecao"] = clean_text(
        result["codcolecao"],
        upper=True,
    )

    result["codproduto"] = clean_text(
        result["codproduto"],
        upper=True,
    )

    result["nomecliente"] = clean_text(
        result["nomecliente"]
    )

    result["situacaopedido"] = clean_text(
        result["situacaopedido"],
        upper=True,
    )

    result["bloq_fin"] = clean_text(
        result["bloq_fin"],
        upper=True,
    )

    result["bloq_com"] = clean_text(
        result["bloq_com"],
        upper=True,
    )

    result["pagto"] = clean_text(
        result["pagto"]
    )

    # --------------------------------------------------------
    # Filtro de coleções
    # --------------------------------------------------------

    collections = normalize_collections(
        collections
    )

    if collections is not None:
        available_collections = set(
            result["codcolecao"]
            .dropna()
            .unique()
            .tolist()
        )

        invalid_collections = [
            collection
            for collection in collections
            if collection not in available_collections
        ]

        if invalid_collections:
            print(
                "AVISO - Coleções não encontradas: "
                + ", ".join(invalid_collections)
            )

        result = result.loc[
            result["codcolecao"].isin(collections)
        ].copy()

    # --------------------------------------------------------
    # Datas
    # --------------------------------------------------------

    for column in [
        "dataemissao",
        "dataprevfaturamento",
        "dataultimanf",
    ]:
        result[column] = pd.to_datetime(
            result[column],
            errors="coerce",
        )

    # --------------------------------------------------------
    # Valores numéricos
    # --------------------------------------------------------

    for column in [
        "codcliente",
        "quantidade",
        "codpedido",
        "numeroultimanf",
    ]:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result["quantidade"] = (
        result["quantidade"]
        .fillna(0)
    )

    result["codpedido"] = (
        result["codpedido"]
        .astype("Int64")
    )

    return (
        result
        .sort_values(
            [
                "codcolecao",
                "dataemissao",
                "codpedido",
                "codproduto",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# PREPARAÇÃO DOS ITENS
# ============================================================

def prepare_items(
    df: pd.DataFrame,
    order_ids,
) -> pd.DataFrame:
    """Normaliza os itens pertencentes aos pedidos selecionados."""

    required = {
        "coditem",
        "codproduto",
        "nomeproduto",
        "qtdepedida",
        "qtdesaldo",
        "qtdefaturado",
        "qtdecancelada",
        "valorunitariobruto",
        "seqtamanho",
        "seqsortimento",
        "codpedido",
    }

    missing = required.difference(df.columns)

    if missing:
        raise ValueError(
            "Colunas ausentes na base detalhada: "
            f"{sorted(missing)}"
        )

    result = df.copy()

    # --------------------------------------------------------
    # Pedido
    # --------------------------------------------------------

    result["codpedido"] = pd.to_numeric(
        result["codpedido"],
        errors="coerce",
    ).astype("Int64")

    # Mantém somente itens pertencentes aos pedidos
    # existentes nas coleções selecionadas.
    result = result.loc[
        result["codpedido"].isin(order_ids)
    ].copy()

    # --------------------------------------------------------
    # Textos
    # --------------------------------------------------------

    result["codproduto"] = clean_text(
        result["codproduto"],
        upper=True,
    )

    result["nomeproduto"] = clean_text(
        result["nomeproduto"]
    )

    result["seqtamanho"] = clean_text(
        result["seqtamanho"],
        upper=True,
    )

    result["seqsortimento"] = clean_text(
        result["seqsortimento"],
        upper=True,
    )

    # --------------------------------------------------------
    # Valores numéricos
    # --------------------------------------------------------

    numeric_columns = [
        "coditem",
        "qtdepedida",
        "qtdesaldo",
        "qtdefaturado",
        "qtdecancelada",
        "valorunitariobruto",
    ]

    for column in numeric_columns:
        result[column] = (
            pd.to_numeric(
                result[column],
                errors="coerce",
            )
            .fillna(0)
        )

    # --------------------------------------------------------
    # Padronização dos nomes
    # --------------------------------------------------------

    result = result.rename(
        columns={
            "codproduto": "referencia",
            "seqtamanho": "grade",
            "seqsortimento": "cor",
        }
    )

    # --------------------------------------------------------
    # Criação do SKU
    # --------------------------------------------------------

    result["sku"] = (
        result["referencia"].fillna("")
        + "|"
        + result["grade"].fillna("")
        + "|"
        + result["cor"].fillna("")
    )

    # --------------------------------------------------------
    # Valor total
    # --------------------------------------------------------

    result["valor_total_pedido"] = (
        result["qtdepedida"]
        * result["valorunitariobruto"]
    )

    return (
        result
        .sort_values(
            [
                "codpedido",
                "referencia",
                "cor",
                "grade",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# SALVAMENTO EXCEL
# ============================================================

def save_excel(
    df: pd.DataFrame,
    path: Path,
) -> None:
    """Salva DataFrame tratado em Excel."""

    with pd.ExcelWriter(
        path,
        engine="openpyxl",
        datetime_format="dd/mm/yyyy",
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Pedidos",
        )

        worksheet = writer.sheets["Pedidos"]

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = (
            worksheet.dimensions
        )


# ============================================================
# RESUMO POR COLEÇÃO
# ============================================================

def print_collection_summary(
    sales: pd.DataFrame,
    items: pd.DataFrame,
) -> None:
    """Exibe resumo de processamento por coleção."""

    collections = (
        sales["codcolecao"]
        .dropna()
        .unique()
        .tolist()
    )

    collections = sorted(collections)

    print()
    print("=" * 70)
    print("RESUMO POR COLEÇÃO")
    print("=" * 70)

    for collection in collections:

        collection_sales = sales.loc[
            sales["codcolecao"].eq(collection)
        ]

        order_ids = (
            collection_sales["codpedido"]
            .dropna()
            .unique()
        )

        collection_items = items.loc[
            items["codpedido"].isin(order_ids)
        ]

        print()
        print(f"Coleção: {collection}")

        print(
            "Pedidos: "
            f"{collection_sales['codpedido'].nunique():,}"
        )

        print(
            "Linhas de pedidos: "
            f"{len(collection_sales):,}"
        )

        print(
            "SKUs: "
            f"{collection_items['sku'].nunique():,}"
        )

        print(
            "Linhas de itens: "
            f"{len(collection_items):,}"
        )


# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================

def main() -> None:

    # --------------------------------------------------------
    # Diretórios
    # --------------------------------------------------------

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    PARQUET_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Leitura
    # --------------------------------------------------------

    raw_sales = read_source(
        RAW_SALES
    )

    raw_items = read_source(
        RAW_ITEMS
    )

    # --------------------------------------------------------
    # ETL pedidos
    # --------------------------------------------------------

    sales = prepare_sales(
        raw_sales,
        collections=COLLECTIONS,
    )

    if sales.empty:
        raise ValueError(
            "Nenhum pedido encontrado para as "
            "coleções configuradas."
        )

    # --------------------------------------------------------
    # ETL itens
    # --------------------------------------------------------

    order_ids = (
        sales["codpedido"]
        .dropna()
        .unique()
    )

    items = prepare_items(
        raw_items,
        order_ids,
    )

    # --------------------------------------------------------
    # Arquivos de saída
    # --------------------------------------------------------

    sales_excel = (
        PROCESSED_DIR
        / "venda-colecao-pedidos_processed.xlsx"
    )

    items_excel = (
        PROCESSED_DIR
        / "venda-colecao-pedidos-detalhado_processed.xlsx"
    )

    sales_parquet = (
        PARQUET_DIR
        / "venda-colecao-pedidos.parquet"
    )

    items_parquet = (
        PARQUET_DIR
        / "venda-colecao-pedidos-detalhado.parquet"
    )

    # --------------------------------------------------------
    # Excel
    # --------------------------------------------------------

    save_excel(
        sales,
        sales_excel,
    )

    save_excel(
        items,
        items_excel,
    )

    # --------------------------------------------------------
    # Parquet
    # --------------------------------------------------------

    sales.to_parquet(
        sales_parquet,
        index=False,
    )

    items.to_parquet(
        items_parquet,
        index=False,
    )

    # --------------------------------------------------------
    # Resultado
    # --------------------------------------------------------

    processed_collections = sorted(
        sales["codcolecao"]
        .dropna()
        .unique()
        .tolist()
    )

    print()
    print("=" * 70)
    print("ETL FINALIZADO")
    print("=" * 70)

    print(
        "Coleções processadas: "
        + ", ".join(processed_collections)
    )

    print(
        f"Total de coleções: "
        f"{len(processed_collections):,}"
    )

    print(
        f"Pedidos: "
        f"{sales['codpedido'].nunique():,} "
        f"| linhas: {len(sales):,}"
    )

    print(
        f"SKUs: "
        f"{items['sku'].nunique():,} "
        f"| linhas: {len(items):,}"
    )

    print()
    print(
        f"Excel pedidos: {sales_excel}"
    )

    print(
        f"Excel itens: {items_excel}"
    )

    print(
        f"Parquet pedidos: {sales_parquet}"
    )

    print(
        f"Parquet itens: {items_parquet}"
    )

    print_collection_summary(
        sales,
        items,
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()
