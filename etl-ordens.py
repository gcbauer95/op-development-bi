import pandas as pd
from pathlib import Path


# ============================================================
# 1. CONFIGURAÇÕES
# ============================================================

full_path = Path("raw/ops-geradas.xlsx")

processed_dir = Path("processed")
parquet_dir = Path("parquet")

processed_dir.mkdir(exist_ok=True)
parquet_dir.mkdir(exist_ok=True)


# ============================================================
# 2. LEITURA DO EXCEL ORIGINAL
# ============================================================

df = pd.read_excel(full_path, dtype={'Número': "string"})


# ============================================================
# 3. REMOVER COLUNAS DESNECESSÁRIAS
# ============================================================

columns_delete = [
	'Período',
	'Parte',
	'Cliente',
	'Nome Cliente',
	'Facção',
	'Nome Faccao',
	'Planejado',
	'Quant.OF',
	'Prox. Facção',
	'Prox. Descrição Facção',
	'Descrição Período',
	'Desc. Parte',
	'Obs. Facção',
	'Obs. OF',
	'Família',
	'Desc. Família',
	'Material',
	'Descrição Material',
	'Modelista',
	'Estilista',
	'Complemento 2',
	'Programação',
	'Identificador Prazo',
	'Reprocesso',
	'Entrega',
	'Cor Prod. Acabado',
	'Sequência',
	'Quant. 2',
	'Quant. I',
	'Quant. F',
	'Quant. B',
	'Quant. C'

]

df = df.drop(
    columns=columns_delete,
    errors="ignore"
)


# ============================================================
# 4. RENOMEAR COLUNAS
# ============================================================

columns_rename = {
    'Número': 'OF',
    'Ult. Retorno': 'Ult. Movimentação',
    'Código': 'Referência',
    'Descrição Produto': 'Descrição',
    'Setor': 'Setor Atual',
    'Desc. Setor': 'Desc. Setor Atual',
    'Quant.': 'Qt Aprovada',
    'Envio': 'Data Setor',
    'Prev. Retorno': 'Prev. Término',
    'Quant. Pend.': 'Qt Pend.',
    'Quant. Orig.': 'Qt Orig.'
}

df = df.rename(columns=columns_rename)


# ============================================================
# 5. DEFINIR COLUNAS PRINCIPAIS
# ============================================================

first_columns = [
	'OF',
	'Emissão',
	'Referência',
	'Descrição',
	'Setor Atual',
	'Desc. Setor Atual',
	'Prox. Setor',
	'Desc. Prox. Setor',
	'Data Setor',
	'Prev. Término',
	'Qt Orig.',
	'Qt Aprovada',
	'Qt Pend.',
	'Fluxo',
	'Desc. Fluxo',
	'Coleção',
	'Desc. Coleção',
	'Tipo OP',
	'Desc. Tipo OP'
]


# ============================================================
# 6. ORGANIZAR COLUNAS DO DATAFRAME
# ============================================================

df = df[
    first_columns +
    [
        col
        for col in df.columns
        if col not in first_columns
    ]
]


# ============================================================
# 6. TROCAR NOME DO GRUPO PARA MELHOR ENTENDIMENTO
# ============================================================

# df['Grupo'] = df['Grupo'].replace('JEANS INTERNO', 'JEANS INFERIOR')
# df['Grupo'] = df['Grupo'].replace('JEANS EXTERNO', 'JEANS PARTE DE CIMA')


# ============================================================
# 7. TRATAMENTO DAS DATAS
# ============================================================

columns_date = [
    'Emissão',
    'Data Setor',
    'Ult. Movimentação',
    'Prev. Término'
]



for column in columns_date:

    if column in df.columns:

        df[column] = pd.to_datetime(
            df[column],
            errors="coerce"
        )


# ============================================================
# 8. GERAR PARQUET
# ============================================================

df_parquet = df[first_columns].copy()

parquet_file = (
    parquet_dir /
    f"{full_path.stem}.parquet"
)

df_parquet.to_parquet(
    parquet_file,
    index=False
)


# ============================================================
# 9. GERAR EXCEL PROCESSADO
# ============================================================

excel_file = (
    processed_dir /
    f"{full_path.stem}_processed.xlsx"
)

with pd.ExcelWriter(
    excel_file,
    engine="openpyxl"
) as writer:

    df.to_excel(
        writer,
        index=False,
        sheet_name="Plan1"
    )

    worksheet = writer.sheets["Plan1"]

    for column_name in columns_date:

        if column_name not in df.columns:
            continue

        column_index = (
            df.columns.get_loc(column_name) + 1
        )

        for cell in worksheet.iter_cols(
            min_col=column_index,
            max_col=column_index,
            min_row=2
        ):
            for item in cell:
                item.number_format = "dd/mm/yyyy"


# ============================================================
# 10. INFORMAÇÕES DO PROCESSAMENTO
# ============================================================

print(f"Processado: {len(df):,} linhas")
print(f"Colunas originais após tratamento: {len(df.columns)}")
print(f"Colunas no Parquet: {len(df_parquet.columns)}")
print(f"Parquet: {parquet_file}")
print(f"Excel: {excel_file}")
