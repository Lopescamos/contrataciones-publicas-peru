"""Cliente HTTP genérico para consumir APIs REST.

Características:
    * Reintentos automáticos con espera exponencial (urllib3 ``Retry``) ante
      errores de red y códigos 429/5xx, respetando la cabecera ``Retry-After``.
    * Pausa mínima entre solicitudes (``min_interval``) para no saturar al servidor.
    * Paginación por enlace ``links.next`` (patrón usado por las APIs OCDS).
    * Descarga de archivos grandes por bloques, con archivo temporal ``.part``.

Ejemplo:
    >>> with APIClient("https://api.ejemplo.pe/v1", min_interval=0.5) as client:
    ...     for page_number, payload in client.iter_pages("items", max_pages=3):
    ...         print(page_number, len(payload["items"]))
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from contrataciones.utils.logger import get_logger

logger = get_logger(__name__)

NextLinkFn = Callable[[Any], str | None]


class APIError(RuntimeError):
    """Error al consumir una API (red, código HTTP o JSON inválido)."""

    def __init__(self, message: str, status_code: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


def default_next_link(payload: Any) -> str | None:
    """Devuelve el enlace a la siguiente página (``links.next`` o ``next``)."""
    if not isinstance(payload, dict):
        return None
    links = payload.get("links")
    if isinstance(links, dict) and links.get("next"):
        return str(links["next"])
    if isinstance(payload.get("next"), str) and payload["next"]:
        return payload["next"]
    return None


class APIClient:
    """Cliente HTTP con reintentos, pausas y paginación."""

    def __init__(
        self,
        base_url: str = "",
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        status_forcelist: tuple[int, ...] | list[int] = (429, 500, 502, 503, 504),
        min_interval: float = 0.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.min_interval = max(0.0, float(min_interval or 0.0))
        self._last_request_at = 0.0
        self.session = session or requests.Session()
        if headers:
            self.session.headers.update({k: str(v) for k, v in headers.items() if v})
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=tuple(status_forcelist),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    # -- utilidades ---------------------------------------------------------------
    def build_url(self, endpoint: str = "") -> str:
        """Une ``base_url`` con el endpoint (o devuelve la URL si ya es absoluta)."""
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        if not endpoint:
            return self.base_url
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    # -- solicitudes -----------------------------------------------------------------
    def request(self, method: str, endpoint: str = "", **kwargs: Any) -> requests.Response:
        """Ejecuta una solicitud y lanza :class:`APIError` si la respuesta es >= 400."""
        url = self.build_url(endpoint)
        self._throttle()
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise APIError(f"Error de red al llamar {url}: {exc}", url=url) from exc
        finally:
            self._last_request_at = time.monotonic()
        if response.status_code >= 400:
            snippet = " ".join(response.text[:300].split())
            raise APIError(
                f"HTTP {response.status_code} en {response.url}: {snippet}",
                status_code=response.status_code,
                url=response.url,
            )
        return response

    def get_json(self, endpoint: str = "", params: dict[str, Any] | None = None) -> Any:
        """GET que devuelve el cuerpo decodificado como JSON."""
        response = self.request("GET", endpoint, params=params)
        try:
            return response.json()
        except ValueError as exc:
            content_type = response.headers.get("content-type", "desconocido")
            raise APIError(
                f"La respuesta de {response.url} no es JSON válido (content-type={content_type})",
                status_code=response.status_code,
                url=response.url,
            ) from exc

    def iter_pages(
        self,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        *,
        next_link: NextLinkFn = default_next_link,
        max_pages: int | None = None,
    ) -> Iterator[tuple[int, Any]]:
        """Recorre una API paginada por enlaces y entrega ``(n_pagina, payload)``."""
        url: str | None = self.build_url(endpoint)
        current_params = params
        page = 0
        visited: set[str] = set()
        while url and (max_pages is None or page < max_pages):
            payload = self.get_json(url, params=current_params)
            page += 1
            visited.add(url)
            yield page, payload
            following = next_link(payload)
            if not following or following in visited:
                break
            # El enlace "next" ya incluye los parámetros de consulta.
            url, current_params = following, None

    def download(
        self,
        url: str,
        destination: str | Path,
        *,
        chunk_size: int = 1 << 20,
        overwrite: bool = False,
        timeout: float | None = None,
    ) -> Path:
        """Descarga un archivo por bloques. Devuelve la ruta final."""
        destination = Path(destination)
        if destination.exists() and not overwrite:
            logger.info("El archivo ya existe, se omite la descarga: %s", destination)
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".part")
        response = self.request("GET", url, stream=True, timeout=timeout or self.timeout)
        total = int(response.headers.get("content-length") or 0)
        written, next_report = 0, 50 << 20
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if written >= next_report:
                    pct = f" ({written / total:.0%})" if total else ""
                    logger.info("Descargados %.0f MB%s", written / (1 << 20), pct)
                    next_report += 50 << 20
        temporary.replace(destination)
        logger.info("Descarga completa: %s (%.1f MB)", destination, written / (1 << 20))
        return destination

    # -- ciclo de vida ------------------------------------------------------------
    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> APIClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
