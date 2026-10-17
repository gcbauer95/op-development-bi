"""Explorador interativo das consultas GET documentadas pela API Excia."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import quote

import pandas as pd
import streamlit as st

PAGES_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PAGES_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from conn_excie_api import ExciaError, ExciaHTTPError, create_excia_client  # noqa: E402
from utils.display import display_dataframe  # noqa: E402
from utils.shared import apply_theme  # noqa: E402


CATALOG_PATH = PROJECT_DIR / "excia_api_catalog.json"
API_CATALOG: list[dict[str, Any]] = json.loads(
    CATALOG_PATH.read_text(encoding="utf-8")
)


def to_dataframe(payload: Any) -> pd.DataFrame:
    """Converte estruturas JSON comuns em linhas e colunas navegáveis."""
    if isinstance(payload, list):
        if not payload:
            return pd.DataFrame()
        if all(isinstance(row, dict) for row in payload):
            return pd.json_normalize(payload, sep=".")
        if all(not isinstance(row, (dict, list)) for row in payload):
            return pd.DataFrame({"valor": payload})
        return pd.DataFrame(
            {"json": [json.dumps(row, ensure_ascii=False) for row in payload]}
        )
    if isinstance(payload, dict):
        return pd.json_normalize([payload], sep=".")
    return pd.DataFrame({"valor": [payload]})


def selected_record(label: str) -> dict[str, Any]:
    return next(item for item in API_CATALOG if item["nome_completo"] == label)


def required_groups(parameters: list[dict[str, Any]]) -> list[set[str]]:
    """Agrupa parâmetros obrigatórios alternativos descritos na documentação."""
    names = {parameter["nome"] for parameter in parameters}
    alternatives: list[set[str]] = []
    for parameter in parameters:
        if not parameter["obrigatorio"]:
            continue
        condition = parameter["condicao"]
        if "caso não informado" not in condition.casefold():
            continue
        mentioned = {
            name for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", condition)
            if name in names
        }
        group = mentioned | {parameter["nome"]}
        if len(group) > 1:
            alternatives.append(group)

    merged: list[set[str]] = []
    for group in alternatives:
        overlapping = [existing for existing in merged if existing & group]
        if overlapping:
            for existing in overlapping:
                group.update(existing)
                merged.remove(existing)
        merged.append(group)
    return merged


def is_conditional_required(parameter: dict[str, Any]) -> bool:
    condition = parameter["condicao"].casefold()
    return "caso não informado" in condition or "caso informado parâmetro" in condition


st.set_page_config(
    page_title="Explorador API Excia | PPCP",
    page_icon="🔎",
    layout="wide",
)
apply_theme()

st.title("Explorador da API Excia")
st.caption(
    "Selecione uma consulta GET, preencha os parâmetros de entrada e veja a resposta em tabela. "
    "O catálogo foi transcrito da documentação oficial da EXCIA."
)
st.info(
    "A rota e os nomes dos parâmetros são fixos. O token é enviado pelo cliente de integração; "
    "empresa só é enviada quando estiver documentada para a consulta e for preenchida."
)

for api in API_CATALOG:
    api["nome_completo"] = f"{api['grupo']} · {api['nome']} · {api['rota']}"

groups = ["Todas"] + sorted({item["grupo"] for item in API_CATALOG})
col_filter, col_api = st.columns([1, 2])
with col_filter:
    group_filter = st.selectbox("Área da API", groups)
available_apis = [
    item for item in API_CATALOG
    if group_filter == "Todas" or item["grupo"] == group_filter
]
with col_api:
    selected_label = st.selectbox(
        "Consulta GET",
        [item["nome_completo"] for item in available_apis],
    )
record = selected_record(selected_label)

with st.expander("Catálogo de consultas incluídas", expanded=False):
    catalog_frame = pd.DataFrame(
        [{
            "Área": item["grupo"],
            "Consulta": item["nome"],
            "Rota": item["rota"],
            "Origem": "Documentação oficial da EXCIA",
        }
         for item in API_CATALOG]
    )
    st.dataframe(catalog_frame, use_container_width=True, hide_index=True)
    st.markdown(
        "Consulte os detalhes e os parâmetros de cada operação na "
        "[documentação oficial da EXCIA](http://api.excia.com.br:3000/api/#consideracoes-iniciais)."
    )

endpoint = record["rota"]
parameters = record["parametros"]
st.markdown(f"### {record['nome']}")
st.caption(record["descricao"])
st.caption(f"Rota GET: `{endpoint}`")

if parameters:
    parameter_frame = pd.DataFrame(
        [{
            "Parâmetro": parameter["nome"],
            "Local": "Caminho" if parameter["local"] == "caminho" else "Consulta",
            "Tipo / tamanho": parameter["tipo"],
            "Obrigatoriedade": parameter["condicao"],
            "Descrição": parameter["descricao"],
        } for parameter in parameters]
    )
    st.dataframe(parameter_frame, use_container_width=True, hide_index=True)
else:
    st.info("A documentação desta consulta não lista parâmetros de entrada.")

with st.form("excia_api_explorer_form"):
    query_parameters = [parameter for parameter in parameters if parameter["local"] == "consulta"]
    path_parameters = [parameter for parameter in parameters if parameter["local"] == "caminho"]
    route_path_keys = list(dict.fromkeys(re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", endpoint)))
    path_values: dict[str, str] = {}
    path_by_name = {parameter["nome"]: parameter for parameter in path_parameters}
    if route_path_keys or path_parameters:
        st.markdown("**Parâmetros de caminho**")
        path_field_names = list(dict.fromkeys(route_path_keys + [
            name for name in record.get("sufixos_caminho_opcionais", [])
            if name not in route_path_keys
        ]))
        path_columns = st.columns(min(3, len(path_field_names)))
        for index, key in enumerate(path_field_names):
            parameter = path_by_name.get(key, {})
            required = bool(parameter.get("obrigatorio", key in route_path_keys))
            type_label = parameter.get("tipo", "string / path param")
            help_text = parameter.get("descricao", "Parâmetro enviado no caminho da URL.")
            label = f"{key} · {'obrigatório' if required else 'opcional'} · {type_label}"
            with path_columns[index % len(path_columns)]:
                path_values[key] = st.text_input(
                    label,
                    help=help_text,
                    key=f"path_{record['nome_completo']}_{key}",
                )

    if query_parameters:
        st.markdown("**Parâmetros de consulta**")
    query_params: dict[str, str] = {}
    editable_query_parameters = []
    for parameter in query_parameters:
        if parameter["valor_fixo"] is not None:
            query_params[parameter["nome"]] = parameter["valor_fixo"]
        else:
            editable_query_parameters.append(parameter)
    for parameter in parameters:
        if parameter["local"] == "consulta" and parameter["valor_fixo"] is not None:
            st.caption(
                f"{parameter['nome']}: valor fixo enviado automaticamente "
                f"({parameter['valor_fixo']})."
            )
    query_columns = st.columns(min(3, len(editable_query_parameters))) if editable_query_parameters else []
    for index, parameter in enumerate(editable_query_parameters):
        name = parameter["nome"]
        condition = parameter["condicao"]
        label = f"{name} · {condition} · {parameter['tipo']}"
        help_text = parameter["descricao"]
        if name == "pagina":
            help_text = f"{help_text} Tipo esperado: number inteiro positivo."
        with query_columns[index % len(query_columns)]:
            query_params[name] = st.text_input(
                label,
                key=f"query_{record['nome_completo']}_{name}",
                help=help_text,
            )
    paginate_all = False
    if any(parameter["nome"] == "pagina" for parameter in query_parameters):
        paginate_all = st.checkbox(
            "Buscar todas as páginas (até 100 páginas)",
            value=False,
            help="A documentação informa até 300 registros por página.",
        )
    search = st.form_submit_button("Buscar dados", type="primary")

if search:
    st.session_state.pop("excia_explorer_payload", None)
    st.session_state.pop("excia_explorer_request_urls", None)
    try:
        missing = [
            key for key in route_path_keys
            if not path_values.get(key, "").strip()
        ]
        if missing:
            raise ValueError("Preencha os parâmetros de caminho: " + ", ".join(missing))

        suffixes = record.get("sufixos_caminho_opcionais", [])
        suffix_values = [path_values.get(name, "").strip() for name in suffixes]
        filled_suffix_count = sum(bool(value) for value in suffix_values)
        if any(not value for value in suffix_values[:filled_suffix_count]):
            raise ValueError(
                "Informe os parâmetros de caminho opcionais na ordem: "
                + ", ".join(suffixes)
                + "."
            )

        params = {
            name: value.strip()
            for name, value in query_params.items()
            if value.strip()
        }
        for parameter in editable_query_parameters:
            name = parameter["nome"]
            if name in params and parameter["tipo"].casefold().startswith("number"):
                try:
                    params[name] = str(int(params[name]))
                except ValueError as exc:
                    raise ValueError(f"O parâmetro {name} deve ser um número inteiro.") from exc

        alternatives = required_groups(parameters)
        grouped_names = set().union(*alternatives) if alternatives else set()
        required_missing = [
            parameter["nome"]
            for parameter in parameters
            if parameter["local"] == "consulta"
            and parameter["obrigatorio"]
            and not is_conditional_required(parameter)
            and parameter["nome"] not in grouped_names
            and not params.get(parameter["nome"], "").strip()
        ]
        required_missing.extend(
            name for group in alternatives
            if not any(params.get(name, "").strip() for name in group)
            for name in [" / ".join(sorted(group))]
        )
        for parameter in parameters:
            condition = parameter["condicao"].casefold()
            if not parameter["obrigatorio"] or "caso informado parâmetro" not in condition:
                continue
            dependency = re.search(
                r"caso informado parâmetro\s+([a-z_][a-z0-9_]*)\s*=\s*['\"]?([^)'\"]+)",
                condition,
            )
            if dependency and params.get(dependency.group(1), "").casefold() == dependency.group(2).strip().casefold():
                if not params.get(parameter["nome"], "").strip():
                    required_missing.append(parameter["nome"])
        if required_missing:
            raise ValueError(
                "Preencha os parâmetros obrigatórios: "
                + ", ".join(required_missing)
                + "."
            )

        resolved_endpoint = endpoint.strip()
        for key, value in path_values.items():
            if value.strip():
                resolved_endpoint = resolved_endpoint.replace(f":{key}", quote(value.strip(), safe=""))
        if filled_suffix_count:
            resolved_endpoint += "/" + "/".join(
                quote(value, safe="") for value in suffix_values[:filled_suffix_count]
            )

        with st.spinner("Consultando a API Excia..."):
            async def fetch() -> Any:
                async with create_excia_client() as client:
                    client.clear_request_urls()
                    try:
                        if paginate_all:
                            params.pop("pagina", None)
                            return await client.paginate(
                                resolved_endpoint,
                                params=params,
                                page_param="pagina",
                                page_size=300,
                                max_pages=100,
                                include_empresa=False,
                            )
                        return await client.get(
                            resolved_endpoint,
                            params=params,
                            allow_not_found=False,
                            include_empresa=False,
                        )
                    finally:
                        st.session_state["excia_explorer_request_urls"] = list(
                            client.request_urls
                        )

            payload = asyncio.run(fetch())
        st.session_state["excia_explorer_payload"] = {
            "endpoint": resolved_endpoint,
            "payload": payload,
        }
    except ExciaHTTPError as exc:
        if "nenhum registro encontrado" in str(exc).casefold():
            st.session_state["excia_explorer_payload"] = {
                "endpoint": resolved_endpoint,
                "payload": [],
            }
        else:
            st.error(f"Não foi possível consultar a API: {exc}")
    except (ExciaError, ValueError, TypeError) as exc:
        st.error(f"Não foi possível consultar a API: {exc}")
    except Exception as exc:  # Erros de decodificação/transporte da resposta.
        st.error(f"A consulta falhou ao processar a resposta: {exc}")

request_urls = st.session_state.get("excia_explorer_request_urls", [])
if request_urls:
    if len(request_urls) == 1:
        st.markdown("**URL GET enviada**")
        st.code(request_urls[0], language=None)
    else:
        with st.expander(f"URLs GET enviadas ({len(request_urls)})", expanded=False):
            for index, url in enumerate(request_urls, start=1):
                st.caption(f"Requisição {index}")
                st.code(url, language=None)

result = st.session_state.get("excia_explorer_payload")
if result is not None:
    payload = result["payload"]
    st.subheader("Resultado")
    st.caption(f"GET {result['endpoint']}")
    if isinstance(payload, bytes):
        mime = "application/octet-stream"
        filename = "resposta-api-excia.bin"
        if payload.startswith(b"%PDF"):
            mime, filename = "application/pdf", "resposta-api-excia.pdf"
        elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
            mime, filename = "image/png", "resposta-api-excia.png"
            st.image(payload)
        elif payload.startswith(b"\xff\xd8\xff"):
            mime, filename = "image/jpeg", "resposta-api-excia.jpg"
            st.image(payload)
        display_dataframe(
            pd.DataFrame([{"Tipo": mime, "Tamanho (bytes)": len(payload)}]),
            hide_index=True,
        )
        st.download_button(
            "Baixar arquivo retornado",
            data=payload,
            file_name=filename,
            mime=mime,
        )
    elif payload is None:
        st.info("A API retornou `null` para esta consulta.")
        st.download_button(
            "Baixar resposta JSON",
            data="null",
            file_name="resposta-api-excia.json",
            mime="application/json",
        )
    else:
        result_df = to_dataframe(payload)
        if result_df.empty:
            st.info("A consulta retornou uma lista vazia.")
        else:
            display_dataframe(result_df, hide_index=True)
            st.caption(f"Registros: {len(result_df):,}".replace(",", "."))
        st.download_button(
            "Baixar resposta JSON",
            data=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            file_name="resposta-api-excia.json",
            mime="application/json",
        )
        with st.expander("Resposta JSON original"):
            st.json(payload)
