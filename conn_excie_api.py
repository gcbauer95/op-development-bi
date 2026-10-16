from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Final, Mapping
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

# Carrega .env apenas quando existente.
# Em Docker/produção, as mesmas variáveis podem ser injetadas diretamente
# no ambiente do processo/container.
load_dotenv()


DEFAULT_TIMEOUT: Final[float] = 30.0
DEFAULT_REQUESTS_PER_SECOND: Final[float] = 5.0
DEFAULT_MAX_CONCURRENCY: Final[int] = 5
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_BACKOFF_BASE: Final[float] = 1.0


logger = logging.getLogger(__name__)


# =============================================================================
# EXCEÇÕES
# =============================================================================


class ExciaError(Exception):
    """Erro base da integração com a API Excia."""


class ExciaConfigurationError(ExciaError):
    """Configuração inválida ou ausente."""


class ExciaAuthenticationError(ExciaError):
    """Falha de autenticação junto à API Excia."""


class ExciaAuthorizationError(ExciaError):
    """Acesso não autorizado a determinado recurso."""


class ExciaRateLimitError(ExciaError):
    """Limite de requisições excedido."""


class ExciaTimeoutError(ExciaError):
    """Timeout de comunicação com a API Excia."""


class ExciaUnavailableError(ExciaError):
    """API Excia temporariamente indisponível."""


class ExciaHTTPError(ExciaError):
    """Erro HTTP não categorizado."""


# =============================================================================
# CONFIGURAÇÃO EXTERNA
# =============================================================================


@dataclass(frozen=True, slots=True)
class ExciaConfig:
    base_url: str
    token: str
    empresa: str

    timeout: float = DEFAULT_TIMEOUT
    requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base: float = DEFAULT_BACKOFF_BASE

    @classmethod
    def from_env(cls) -> "ExciaConfig":
        """
        Cria a configuração da integração a partir das variáveis de ambiente.

        Variáveis obrigatórias:
            EXCIA_BASE_URL
            EXCIA_TOKEN
            EXCIA_EMPRESA

        Variáveis opcionais:
            EXCIA_TIMEOUT
            EXCIA_REQUESTS_PER_SECOND
            EXCIA_MAX_CONCURRENCY
            EXCIA_MAX_RETRIES
            EXCIA_BACKOFF_BASE
        """

        base_url = _required_env("EXCIA_BASE_URL")
        token = _required_env("EXCIA_TOKEN")
        empresa = _required_env("EXCIA_EMPRESA")

        base_url = _normalize_base_url(base_url)

        timeout = _env_float(
            "EXCIA_TIMEOUT",
            DEFAULT_TIMEOUT,
            minimum=0.1,
        )

        requests_per_second = _env_float(
            "EXCIA_REQUESTS_PER_SECOND",
            DEFAULT_REQUESTS_PER_SECOND,
            minimum=0.1,
        )

        max_concurrency = _env_int(
            "EXCIA_MAX_CONCURRENCY",
            DEFAULT_MAX_CONCURRENCY,
            minimum=1,
        )

        max_retries = _env_int(
            "EXCIA_MAX_RETRIES",
            DEFAULT_MAX_RETRIES,
            minimum=0,
        )

        backoff_base = _env_float(
            "EXCIA_BACKOFF_BASE",
            DEFAULT_BACKOFF_BASE,
            minimum=0.1,
        )

        return cls(
            base_url=base_url,
            token=token,
            empresa=empresa,
            timeout=timeout,
            requests_per_second=requests_per_second,
            max_concurrency=max_concurrency,
            max_retries=max_retries,
            backoff_base=backoff_base,
        )

    def __repr__(self) -> str:
        """
        Impede exposição acidental do Token ao imprimir o objeto.
        """
        return (
            "ExciaConfig("
            f"base_url={self.base_url!r}, "
            "token=<redacted>, "
            f"empresa={self.empresa!r}, "
            f"timeout={self.timeout!r}, "
            f"requests_per_second={self.requests_per_second!r}, "
            f"max_concurrency={self.max_concurrency!r}, "
            f"max_retries={self.max_retries!r}"
            ")"
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise ExciaConfigurationError(
            f"{name} não configurado"
        )

    return value.strip()


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
) -> float:
    raw_value = os.getenv(name)

    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ExciaConfigurationError(
            f"{name} possui valor inválido"
        ) from exc

    if minimum is not None and value < minimum:
        raise ExciaConfigurationError(
            f"{name} deve ser maior ou igual a {minimum}"
        )

    return value


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ExciaConfigurationError(
            f"{name} possui valor inválido"
        ) from exc

    if minimum is not None and value < minimum:
        raise ExciaConfigurationError(
            f"{name} deve ser maior ou igual a {minimum}"
        )

    return value


def _normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")

    parsed = urlparse(normalized)

    if parsed.scheme not in {"http", "https"}:
        raise ExciaConfigurationError(
            "EXCIA_BASE_URL deve utilizar http ou https"
        )

    if not parsed.netloc:
        raise ExciaConfigurationError(
            "EXCIA_BASE_URL possui URL inválida"
        )

    return normalized


# =============================================================================
# CLIENT HTTP
# =============================================================================


class ExciaClient:
    """
    Client assíncrono responsável pela comunicação com a API Excia.

    O restante da aplicação não precisa conhecer:
        - Token;
        - headers;
        - empresa;
        - política de retry;
        - throttle;
        - timeout;
        - controle de concorrência.
    """

    def __init__(
        self,
        config: ExciaConfig | None = None,
    ) -> None:
        self._config = config or ExciaConfig.from_env()

        self._headers = {
            "Token": self._config.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            headers=self._headers,
            timeout=httpx.Timeout(self._config.timeout),
            follow_redirects=True,
        )

        self._semaphore = asyncio.Semaphore(
            self._config.max_concurrency
        )

        self._throttle_lock = asyncio.Lock()

        self._minimum_interval = (
            1.0 / self._config.requests_per_second
        )

        self._last_request_started = 0.0
        self._request_urls: list[str] = []

        self._closed = False

    # =========================================================================
    # CONTEXT MANAGER
    # =========================================================================

    async def __aenter__(self) -> "ExciaClient":
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return

        await self._client.aclose()
        self._closed = True

    @property
    def request_urls(self) -> tuple[str, ...]:
        """URLs GET efetivamente montadas nesta instância do client."""

        return tuple(self._request_urls)

    def clear_request_urls(self) -> None:
        """Limpa o histórico local de URLs antes de uma nova consulta."""

        self._request_urls.clear()

    # =========================================================================
    # INFRAESTRUTURA INTERNA
    # =========================================================================

    async def _throttle(self) -> None:
        """
        Garante intervalo mínimo global entre o início das requisições.
        """

        async with self._throttle_lock:
            now = time.monotonic()

            elapsed = now - self._last_request_started
            remaining = self._minimum_interval - elapsed

            if remaining > 0:
                await asyncio.sleep(remaining)

            self._last_request_started = time.monotonic()

    @staticmethod
    def _endpoint(endpoint: str) -> str:
        """
        Normaliza endpoint sem permitir URL externa arbitrária.
        """

        endpoint = endpoint.strip()

        if not endpoint:
            raise ValueError("Endpoint não pode ser vazio")

        if endpoint.startswith(("http://", "https://")):
            raise ValueError(
                "O endpoint deve ser relativo à EXCIA_BASE_URL"
            )

        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        return endpoint

    def _params_with_empresa(
        self,
        params: Mapping[str, Any] | None,
        *,
        include_empresa: bool = True,
    ) -> dict[str, Any]:
        """
        Inclui empresa configurada por padrão, com possibilidade de desativar
        a inclusão automática e preservar um valor explícito nos parâmetros.

        Quando a inclusão automática está ativa, a empresa configurada prevalece.
        """

        result = dict(params or {})
        if include_empresa:
            result["empresa"] = self._config.empresa

        return result

    def _should_retry(
        self,
        *,
        method: str,
        status_code: int | None = None,
        transport_error: bool = False,
    ) -> bool:
        """
        Política conservadora de retry.

        GET:
            retry em falhas transitórias.

        POST:
            não faz retry automático para evitar duplicação
            de operações com efeito colateral.
        """

        method = method.upper()

        if method != "GET":
            return False

        if transport_error:
            return True

        if status_code == 429:
            return True

        if status_code is not None and 500 <= status_code <= 599:
            return True

        return False

    async def _sleep_before_retry(
        self,
        attempt: int,
        *,
        retry_after: str | None = None,
    ) -> None:
        """
        Backoff exponencial controlado.

        Se Retry-After possuir um valor numérico válido, ele é respeitado
        dentro de um limite defensivo.
        """

        if retry_after:
            try:
                wait = float(retry_after)

                if 0 < wait <= 60:
                    await asyncio.sleep(wait)
                    return

            except ValueError:
                pass

        wait = self._config.backoff_base * (2 ** attempt)

        # Proteção para impedir espera exagerada.
        wait = min(wait, 30.0)

        await asyncio.sleep(wait)

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        allow_not_found: bool = True,
        include_empresa: bool = True,
    ) -> Any:
        if self._closed:
            raise ExciaError(
                "ExciaClient já foi encerrado"
            )

        method = method.upper()
        endpoint = self._endpoint(endpoint)

        request_params = self._params_with_empresa(
            params,
            include_empresa=include_empresa,
        )

        max_attempts = self._config.max_retries + 1

        for attempt in range(max_attempts):
            await self._throttle()

            started_at = time.monotonic()

            try:
                async with self._semaphore:
                    request = self._client.build_request(
                        method=method,
                        url=endpoint,
                        params=request_params,
                        json=json,
                    )
                    self._request_urls.append(str(request.url))
                    response = await self._client.send(request)

            except httpx.TimeoutException as exc:
                duration = time.monotonic() - started_at

                logger.warning(
                    "Excia timeout method=%s endpoint=%s "
                    "duration=%.3fs attempt=%d",
                    method,
                    endpoint,
                    duration,
                    attempt + 1,
                )

                if (
                    attempt < self._config.max_retries
                    and self._should_retry(
                        method=method,
                        transport_error=True,
                    )
                ):
                    await self._sleep_before_retry(attempt)
                    continue

                raise ExciaTimeoutError(
                    f"Timeout ao acessar endpoint {endpoint}"
                ) from exc

            except httpx.TransportError as exc:
                duration = time.monotonic() - started_at

                logger.warning(
                    "Excia transport_error method=%s endpoint=%s "
                    "duration=%.3fs attempt=%d",
                    method,
                    endpoint,
                    duration,
                    attempt + 1,
                )

                if (
                    attempt < self._config.max_retries
                    and self._should_retry(
                        method=method,
                        transport_error=True,
                    )
                ):
                    await self._sleep_before_retry(attempt)
                    continue

                raise ExciaUnavailableError(
                    f"Falha de comunicação com endpoint {endpoint}"
                ) from exc

            duration = time.monotonic() - started_at

            logger.info(
                "Excia request method=%s endpoint=%s "
                "status=%d duration=%.3fs attempt=%d",
                method,
                endpoint,
                response.status_code,
                duration,
                attempt + 1,
            )

            # -----------------------------------------------------------------
            # Sucesso
            # -----------------------------------------------------------------

            if 200 <= response.status_code < 300:
                return self._decode_response(response)

            # -----------------------------------------------------------------
            # 404
            # -----------------------------------------------------------------

            if response.status_code == 404:
                if allow_not_found:
                    return None

                raise ExciaHTTPError(
                    f"Recurso não encontrado em {endpoint}"
                )

            # -----------------------------------------------------------------
            # Autenticação
            # -----------------------------------------------------------------

            if response.status_code == 401:
                raise ExciaAuthenticationError(
                    "Falha de autenticação na API Excia"
                )

            # -----------------------------------------------------------------
            # Autorização
            # -----------------------------------------------------------------

            if response.status_code == 403:
                raise ExciaAuthorizationError(
                    f"Acesso não autorizado ao endpoint {endpoint}"
                )

            # -----------------------------------------------------------------
            # Rate Limit
            # -----------------------------------------------------------------

            if response.status_code == 429:
                logger.warning(
                    "Excia rate_limit endpoint=%s attempt=%d",
                    endpoint,
                    attempt + 1,
                )

                if (
                    attempt < self._config.max_retries
                    and self._should_retry(
                        method=method,
                        status_code=429,
                    )
                ):
                    await self._sleep_before_retry(
                        attempt,
                        retry_after=response.headers.get(
                            "Retry-After"
                        ),
                    )
                    continue

                raise ExciaRateLimitError(
                    "Limite de requisições da API Excia atingido"
                )

            # -----------------------------------------------------------------
            # 5xx
            # -----------------------------------------------------------------

            if 500 <= response.status_code <= 599:
                if (
                    attempt < self._config.max_retries
                    and self._should_retry(
                        method=method,
                        status_code=response.status_code,
                    )
                ):
                    await self._sleep_before_retry(attempt)
                    continue

                raise ExciaUnavailableError(
                    "API Excia temporariamente indisponível "
                    f"(HTTP {response.status_code})"
                )

            # -----------------------------------------------------------------
            # Outros 4xx / erros
            # -----------------------------------------------------------------

            detail = self._error_detail(response)
            suffix = f": {detail}" if detail else ""
            raise ExciaHTTPError(
                f"Erro na API Excia: HTTP {response.status_code} "
                f"em {endpoint}{suffix}"
            )

        raise ExciaUnavailableError(
            f"Não foi possível concluir a chamada ao endpoint {endpoint}"
        )

    @staticmethod
    def _decode_response(
        response: httpx.Response,
    ) -> Any:
        """
        Retorna JSON quando possível.

        Não registra body da resposta para reduzir risco de vazamento
        de informações sensíveis.
        """

        if not response.content:
            return None

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

        if (
            content_type.startswith("image/")
            or "application/pdf" in content_type
            or "application/octet-stream" in content_type
        ):
            return response.content

        if "application/json" in content_type:
            return response.json()

        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        """Extrai a mensagem de erro sem incluir respostas extensas na UI."""
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip()[:500]

        messages: list[str] = []

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if "error" in str(key).casefold() or "erro" in str(key).casefold():
                        if isinstance(item, (str, int, float)):
                            messages.append(str(item))
                        else:
                            collect(item)
                    else:
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(payload)
        if messages:
            return "; ".join(messages)[:500]
        return str(payload).strip()[:500]

    # =========================================================================
    # MÉTODOS INTERNOS DE TRANSPORTE
    # =========================================================================

    async def _get(
        self,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        allow_not_found: bool = True,
        include_empresa: bool = True,
    ) -> Any:
        return await self._request(
            "GET",
            endpoint,
            params=params,
            allow_not_found=allow_not_found,
            include_empresa=include_empresa,
        )

    async def _post_write(
        self,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Any,
    ) -> Any:
        """
        Transporte reservado exclusivamente para operações explícitas
        de escrita.

        Importante:
        POST não recebe retry automático para evitar duplicações.
        """

        return await self._request(
            "POST",
            endpoint,
            params=params,
            json=payload,
            allow_not_found=False,
        )

    # =========================================================================
    # INTERFACE PÚBLICA — CONSULTAS
    # =========================================================================

    async def buscar_pedido(
        self,
        numero: str | int,
    ) -> Any:
        """
        Consulta /BuscarPedido.

        A API Excia documenta o parâmetro `numero` para localizar um
        pedido pelo número do ERP.
        """

        if numero is None or str(numero).strip() == "":
            raise ValueError(
                "Número do pedido é obrigatório"
            )

        return await self._get(
            "/BuscarPedido",
            params={"numero": str(numero).strip()},
            allow_not_found=False,
        )

    async def produto_estoque(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/ProdutoEstoque",
            params=params,
        )

    async def listar_pedidos(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/PedidoLista",
            params=params,
        )

    async def listar_entidades(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/EntidadeLista",
            params=params,
        )

    async def listar_transportadoras(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/TransportadoraLista",
            params=params,
        )

    async def listar_ops(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/OPLista",
            params=params,
        )

    async def listar_representantes(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/RepresentanteLista",
            params=params,
        )

    async def listar_familias(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/FamiliaLista",
            params=params,
        )

    async def listar_colecoes(
        self,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._get(
            "/ColecaoLista",
            params=params,
        )

    async def get(
        self,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        allow_not_found: bool = True,
        include_empresa: bool = True,
    ) -> Any:
        """
        Interface genérica SOMENTE para consultas GET.

        Útil para adicionar gradualmente os endpoints da Excia sem
        expor Token, headers ou empresa para a aplicação.

        Não existe equivalente público genérico para POST de escrita.
        """

        return await self._get(
            endpoint,
            params=params,
            allow_not_found=allow_not_found,
            include_empresa=include_empresa,
        )

    # =========================================================================
    # PAGINAÇÃO
    # =========================================================================

    async def paginate(
        self,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        page_param: str = "pagina",
        page_size: int = 300,
        start_page: int = 1,
        max_pages: int = 10_000,
        include_empresa: bool = True,
    ) -> list[Any]:
        """
        Executa paginação defensiva.

        OBSERVAÇÃO:
        O nome default `pagina` precisa corresponder ao endpoint utilizado.
        Caso a API utilize outro nome, informe explicitamente page_param.

        A função detecta:
            - página menor que page_size;
            - página vazia;
            - repetição da página anterior;
            - excesso de páginas.

        Não pressupõe estrutura de resposta além de uma lista.
        """

        if page_size <= 0:
            raise ValueError(
                "page_size deve ser maior que zero"
            )

        if start_page <= 0:
            raise ValueError(
                "start_page deve ser maior que zero"
            )

        if max_pages <= 0:
            raise ValueError(
                "max_pages deve ser maior que zero"
            )

        base_params = dict(params or {})

        records: list[Any] = []
        previous_page: list[Any] | None = None

        current_page = start_page

        for _ in range(max_pages):
            current_params = dict(base_params)
            current_params[page_param] = current_page

            result = await self._get(
                endpoint,
                params=current_params,
                include_empresa=include_empresa,
            )

            if result is None:
                break

            if not isinstance(result, list):
                raise ExciaError(
                    "Paginação esperava resposta em formato de lista"
                )

            if not result:
                break

            # Algumas APIs repetem a última página indefinidamente.
            if previous_page is not None and result == previous_page:
                logger.warning(
                    "Excia pagination repeated_page "
                    "endpoint=%s page=%d",
                    endpoint,
                    current_page,
                )
                break

            records.extend(result)

            if len(result) < page_size:
                break

            previous_page = result
            current_page += 1

        else:
            raise ExciaError(
                f"Paginação interrompida ao atingir max_pages={max_pages}"
            )

        return records

    # =========================================================================
    # HEALTHCHECK
    # =========================================================================

    async def healthcheck(
        self,
        endpoint: str,
    ) -> bool:
        """
        Executa uma consulta GET segura para verificar comunicação.

        O endpoint deve ser explicitamente informado porque o documento
        fornecido não define qual endpoint deve ser considerado o
        healthcheck oficial da integração.
        """

        try:
            await self._get(
                endpoint,
                allow_not_found=False,
            )

            return True

        except ExciaError:
            return False


# =============================================================================
# FACTORY
# =============================================================================


def create_excia_client() -> ExciaClient:
    """
    Factory para criação do client usando configuração externa.
    """

    return ExciaClient(
        config=ExciaConfig.from_env()
    )
