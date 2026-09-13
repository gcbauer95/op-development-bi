from io import BytesIO

import pandas as pd
import streamlit as st


DATASETS = {
    "movimentacao": {
        "description": "Movimentação por setor",
        "columns": [
            "OF",
            "Referência",
            "Descrição",
            "Tamanho",
            "Data Entrada",
            "Data Saída",
            "Prev Saída",
            "Qt OF",
            "Qt Aprovada",
            "CodSetor",
            "Setor",
            "Colecao",
            "Desc_Colecao",
            "CodFacção",
            "Facção",
            "CodGrupo",
            "Grupo",
        ],
    },
}


@st.cache_data
def read_parquet(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_parquet(
        BytesIO(file_bytes)
    )


def validate_dataframe(
    df: pd.DataFrame,
    expected_columns: list[str],
) -> list[str]:

    return [
        column
        for column in expected_columns
        if column not in df.columns
    ]


def load_data(dataset_name: str) -> pd.DataFrame | None:

    dataset = DATASETS.get(dataset_name)

    if dataset is None:
        raise ValueError(
            f"Dataset '{dataset_name}' não está configurado."
        )

    # ========================================================
    # 1. VERIFICAR SE JÁ EXISTE NO SESSION_STATE
    # ========================================================

    state_key = f"data_{dataset_name}"

    if state_key in st.session_state:

        return st.session_state[state_key]

    # ========================================================
    # 2. SOLICITAR UPLOAD
    # ========================================================

    uploaded_file = st.file_uploader(
        f"Envie o arquivo — {dataset['description']}",
        type=["parquet"],
        key=f"upload_{dataset_name}",
    )

    if uploaded_file is None:
        return None

    # ========================================================
    # 3. LER PARQUET
    # ========================================================

    try:

        df = read_parquet(
            uploaded_file.getvalue()
        )

    except Exception as error:

        st.error(
            f"Não foi possível ler o arquivo Parquet: {error}"
        )

        return None

    # ========================================================
    # 4. VALIDAR
    # ========================================================

    missing_columns = validate_dataframe(
        df,
        dataset["columns"],
    )

    if missing_columns:

        st.error(
            "O arquivo não possui a estrutura esperada."
        )

        st.write(
            "Colunas ausentes:",
            missing_columns,
        )

        return None

    # ========================================================
    # 5. SALVAR NA SESSÃO
    # ========================================================

    st.session_state[state_key] = df

    return df
