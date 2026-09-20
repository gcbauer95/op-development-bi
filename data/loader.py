from io import BytesIO
import hashlib

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
    "ops_geradas": {
        "description": "Ordens geradas",
        "columns": [
            "OF",
            "Tipo OP",
            "Desc. Tipo OP",
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


def load_data(dataset_name: str, *, refresh: bool = False) -> pd.DataFrame | None:

    dataset = DATASETS.get(dataset_name)

    if dataset is None:
        raise ValueError(
            f"Dataset '{dataset_name}' não está configurado."
        )

    # ========================================================
    # 1. VERIFICAR SE JÁ EXISTE NO SESSION_STATE
    # ========================================================

    state_key = f"data_{dataset_name}"

    if state_key in st.session_state and not refresh:

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
        return st.session_state.get(state_key)

    # ========================================================
    # 3. LER PARQUET
    # ========================================================

    try:

        file_bytes = uploaded_file.getvalue()
        file_signature = hashlib.sha256(file_bytes).hexdigest()

        if (
            state_key in st.session_state
            and st.session_state.get(f"{state_key}_signature") == file_signature
        ):
            return st.session_state[state_key]

        df = read_parquet(file_bytes)

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
    st.session_state[f"{state_key}_signature"] = file_signature
    st.session_state.pop("data_movimentacao_enriched", None)

    return df
