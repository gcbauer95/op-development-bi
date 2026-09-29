"""ETL das vendas e itens de pedidos da coleção AV27.

Lê os dois Excel exportados do ERP, normaliza os tipos, cria a chave de SKU
(referência + grade + cor), grava cópias tratadas em ``processed`` e Parquet
para carga posterior no Streamlit.
"""

from pathlib import Path

import pandas as pd


COLLECTION = "AV27"
RAW_SALES = Path("raw/venda-colecao-pedidos.xlsx")
RAW_ITEMS = Path("raw/venda-colecao-pedidos-detalhado.xlsx")
PROCESSED_DIR = Path("processed")
PARQUET_DIR = Path("parquet")


def clean_text(series: pd.Series, *, upper: bool = False) -> pd.Series:
    result = series.astype("string").str.strip()
    return result.str.upper() if upper else result


def read_source(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    # As exportações têm abas vazias auxiliares; a primeira aba contém os dados.
    return pd.read_excel(path, sheet_name=0)


def prepare_sales(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "codcolecao", "dataemissao", "codcliente", "nomecliente", "codproduto",
        "quantidade", "codpedido", "dataprevfaturamento", "situacaopedido",
        "dataultimanf", "numeroultimanf", "bloq_fin", "bloq_com", "pagto",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes na base de pedidos: {sorted(missing)}")

    result = df.copy()
    result["codcolecao"] = clean_text(result["codcolecao"], upper=True)
    result = result.loc[result["codcolecao"].eq(COLLECTION)].copy()
    result["codproduto"] = clean_text(result["codproduto"], upper=True)
    result["nomecliente"] = clean_text(result["nomecliente"])
    result["situacaopedido"] = clean_text(result["situacaopedido"], upper=True)
    result["bloq_fin"] = clean_text(result["bloq_fin"], upper=True)
    result["bloq_com"] = clean_text(result["bloq_com"], upper=True)
    result["pagto"] = clean_text(result["pagto"])

    for column in ["dataemissao", "dataprevfaturamento", "dataultimanf"]:
        result[column] = pd.to_datetime(result[column], errors="coerce")
    for column in ["codcliente", "quantidade", "codpedido", "numeroultimanf"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result["quantidade"] = result["quantidade"].fillna(0)
    result["codpedido"] = result["codpedido"].astype("Int64")
    return result.sort_values(["dataemissao", "codpedido", "codproduto"]).reset_index(drop=True)


def prepare_items(df: pd.DataFrame, order_ids: pd.Series) -> pd.DataFrame:
    required = {
        "coditem", "codproduto", "nomeproduto", "qtdepedida", "qtdesaldo",
        "qtdefaturado", "qtdecancelada", "valorunitariobruto", "seqtamanho",
        "seqsortimento", "codpedido",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes na base detalhada: {sorted(missing)}")

    result = df.copy()
    result["codpedido"] = pd.to_numeric(result["codpedido"], errors="coerce").astype("Int64")
    result = result.loc[result["codpedido"].isin(order_ids)].copy()
    result["codproduto"] = clean_text(result["codproduto"], upper=True)
    result["nomeproduto"] = clean_text(result["nomeproduto"])
    result["seqtamanho"] = clean_text(result["seqtamanho"], upper=True)
    result["seqsortimento"] = clean_text(result["seqsortimento"], upper=True)
    for column in ["coditem", "qtdepedida", "qtdesaldo", "qtdefaturado", "qtdecancelada", "valorunitariobruto"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)

    result = result.rename(columns={
        "codproduto": "referencia",
        "seqtamanho": "grade",
        "seqsortimento": "cor",
    })
    result["sku"] = (
        result["referencia"].fillna("") + "|"
        + result["grade"].fillna("") + "|"
        + result["cor"].fillna("")
    )
    result["valor_total_pedido"] = result["qtdepedida"] * result["valorunitariobruto"]
    return result.sort_values(["codpedido", "referencia", "cor", "grade"]).reset_index(drop=True)


def save_excel(df: pd.DataFrame, path: Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl", datetime_format="dd/mm/yyyy") as writer:
        df.to_excel(writer, index=False, sheet_name="Pedidos")
        worksheet = writer.sheets["Pedidos"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions


def main() -> None:
    PROCESSED_DIR.mkdir(exist_ok=True)
    PARQUET_DIR.mkdir(exist_ok=True)

    sales = prepare_sales(read_source(RAW_SALES))
    items = prepare_items(read_source(RAW_ITEMS), sales["codpedido"].dropna().unique())

    sales_excel = PROCESSED_DIR / "venda-colecao-pedidos_processed.xlsx"
    items_excel = PROCESSED_DIR / "venda-colecao-pedidos-detalhado_processed.xlsx"
    sales_parquet = PARQUET_DIR / "venda-colecao-pedidos.parquet"
    items_parquet = PARQUET_DIR / "venda-colecao-pedidos-detalhado.parquet"

    save_excel(sales, sales_excel)
    save_excel(items, items_excel)
    sales.to_parquet(sales_parquet, index=False)
    items.to_parquet(items_parquet, index=False)

    print(f"Coleção processada: {COLLECTION}")
    print(f"Pedidos: {sales['codpedido'].nunique():,} | linhas: {len(sales):,}")
    print(f"SKUs: {items['sku'].nunique():,} | linhas: {len(items):,}")
    print(f"Excel: {sales_excel} | {items_excel}")
    print(f"Parquet: {sales_parquet} | {items_parquet}")


if __name__ == "__main__":
    main()
