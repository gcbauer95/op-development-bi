"""ETL da posição de estoque pronta-entrega da coleção AV27."""

from pathlib import Path

import pandas as pd


COLLECTION = "AV27"
RAW_FILE = Path("raw/posicao-estoque-av27.xlsx")
PROCESSED_FILE = Path("processed/posicao-estoque-av27_processed.xlsx")
PARQUET_FILE = Path("parquet/posicao-estoque-av27.parquet")


def clean_text(series: pd.Series, *, upper: bool = False) -> pd.Series:
    result = series.astype("string").str.strip()
    return result.str.upper() if upper else result


def prepare_stock(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "codcolecao",
        "codreferencia",
        "seqtamanho",
        "seqsortimento",
        "qtdprontaentrega",
        "seqordenacaotamanho",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Colunas ausentes na posição de estoque: {sorted(missing)}")

    result = df.copy()
    result["codcolecao"] = clean_text(result["codcolecao"], upper=True)
    result = result.loc[result["codcolecao"].eq(COLLECTION)].copy()
    result["codreferencia"] = clean_text(result["codreferencia"], upper=True)
    result["seqtamanho"] = clean_text(result["seqtamanho"], upper=True)
    result["seqsortimento"] = clean_text(result["seqsortimento"], upper=True)
    result["qtdprontaentrega"] = pd.to_numeric(result["qtdprontaentrega"], errors="coerce").fillna(0)
    result["seqordenacaotamanho"] = pd.to_numeric(result["seqordenacaotamanho"], errors="coerce")
    result["sku"] = (
        result["codreferencia"].fillna("") + "|"
        + result["seqtamanho"].fillna("") + "|"
        + result["seqsortimento"].fillna("")
    )
    result = result.rename(columns={
        "codcolecao": "colecao",
        "codreferencia": "referencia",
        "seqtamanho": "grade",
        "seqsortimento": "cor",
        "qtdprontaentrega": "estoque_pronta_entrega",
        "seqordenacaotamanho": "ordem_grade",
    })
    return result[
        ["colecao", "referencia", "grade", "cor", "estoque_pronta_entrega", "ordem_grade", "sku"]
    ].sort_values(["referencia", "cor", "ordem_grade", "grade"]).reset_index(drop=True)


def main() -> None:
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {RAW_FILE}")
    PROCESSED_FILE.parent.mkdir(exist_ok=True)
    PARQUET_FILE.parent.mkdir(exist_ok=True)

    source = pd.read_excel(RAW_FILE, sheet_name=0)
    stock = prepare_stock(source)
    stock.to_parquet(PARQUET_FILE, index=False)
    with pd.ExcelWriter(PROCESSED_FILE, engine="openpyxl") as writer:
        stock.to_excel(writer, index=False, sheet_name="Estoque AV27")
        worksheet = writer.sheets["Estoque AV27"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

    print(f"Coleção processada: {COLLECTION}")
    print(f"Linhas: {len(stock):,} | SKUs: {stock['sku'].nunique():,}")
    print(f"Estoque pronta-entrega: {stock['estoque_pronta_entrega'].sum():,.0f}")
    print(f"Parquet: {PARQUET_FILE}")
    print(f"Excel: {PROCESSED_FILE}")


if __name__ == "__main__":
    main()
