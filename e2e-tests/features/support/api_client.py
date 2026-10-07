"""Cliente HTTP del proyecto E2E, basado en ``requests.Session``.

Una instancia por escenario (creada en ``before_scenario``): mantiene las
cabeceras (incluido el Bearer del token vigente) sin filtrar estado entre
escenarios.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

import requests

from support import config


class ApiClient:
    """Cliente HTTP contra el gateway con token opcional."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = (base_url or config.base_url()).rstrip("/")
        self.timeout = timeout if timeout is not None else config.http_timeout()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.last_request: Optional[Tuple[str, str]] = None

    # -- Token ---------------------------------------------------------
    def set_token(self, token: Optional[str]) -> None:
        """Activa/desactiva el Bearer del token vigente."""
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.headers.pop("Authorization", None)

    # -- Peticiones ----------------------------------------------------
    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Ejecuta una petición y recuerda método/URL para los mensajes de error."""
        if path.startswith(("http://", "https://")):
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)
        self.last_request = (method.upper(), url)
        return self.session.request(method.upper(), url, **kwargs)

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, json: Optional[dict] = None, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, json=json, **kwargs)

    def put(self, path: str, json: Optional[dict] = None, **kwargs: Any) -> requests.Response:
        return self.request("PUT", path, json=json, **kwargs)

    # -- Ciclo de vida -------------------------------------------------
    def close(self) -> None:
        """Cierra la sesión HTTP del escenario."""
        self.session.close()
