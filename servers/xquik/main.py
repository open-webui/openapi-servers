from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx
from config import (
    API_CONTRACT,
    UPSTREAM_API_ROOT,
    UPSTREAM_SCHEMA_URL,
    Settings,
    load_settings,
)
from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, Response
from schema import prepare_openapi_schema

MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 16_777_216
MAX_SCHEMA_BYTES = 4_194_304
PROXY_METHODS = ["DELETE", "GET", "PATCH", "POST", "PUT"]
SAFE_RESPONSE_HEADERS = ("content-disposition", "content-type", "retry-after")

RequestUpstream = Callable[
    [str, str, Sequence[tuple[str, str]], bytes, Mapping[str, str]],
    Awaitable[httpx.Response],
]
LoadSchema = Callable[[], Awaitable[Mapping[str, Any]]]


async def request_upstream(
    method: str,
    url: str,
    query: Sequence[tuple[str, str]],
    body: bytes,
    headers: Mapping[str, str],
) -> httpx.Response:
    async with (
        httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
        ) as client,
        client.stream(
            method,
            url,
            params=list(query),
            content=body or None,
            headers=headers,
        ) as response,
    ):
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise UpstreamResponseTooLarge
        return httpx.Response(
            response.status_code,
            content=bytes(content),
            headers=response.headers,
            request=response.request,
        )


class UpstreamResponseTooLarge(RuntimeError):
    pass


async def load_upstream_schema() -> Mapping[str, Any]:
    async with (
        httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(15.0),
        ) as client,
        client.stream(
            "GET",
            UPSTREAM_SCHEMA_URL,
            headers={"accept": "application/json"},
        ) as response,
    ):
        if response.status_code != 200:
            raise RuntimeError("Xquik OpenAPI discovery failed.")
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_SCHEMA_BYTES:
                raise RuntimeError("Xquik OpenAPI document is too large.")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise TypeError("Xquik returned an invalid OpenAPI document.")
    return parsed


class ProxyRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        upstream_request: RequestUpstream,
        schema_loader: LoadSchema,
    ) -> None:
        self.settings = settings
        self.upstream_request = upstream_request
        self.schema_loader = schema_loader
        self.schema_lock: asyncio.Lock | None = None
        self.schema_cache: dict[str, Any] | None = None

    async def health(self) -> dict[str, bool]:
        return {
            "actions_enabled": self.settings.actions_enabled,
            "configured": bool(self.settings.api_key),
            "ok": True,
        }

    async def openapi_document(self) -> JSONResponse:
        return JSONResponse(await self._openapi_schema())

    async def _openapi_schema(self) -> dict[str, Any]:
        if self.schema_lock is None:
            self.schema_lock = asyncio.Lock()
        async with self.schema_lock:
            if self.schema_cache is None:
                self.schema_cache = await self._load_prepared_schema()
        return self.schema_cache

    async def _load_prepared_schema(self) -> dict[str, Any]:
        try:
            source = await self.schema_loader()
            return prepare_openapi_schema(
                source,
                actions_enabled=self.settings.actions_enabled,
            )
        except (
            httpx.RequestError,
            json.JSONDecodeError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise HTTPException(
                status_code=502,
                detail="Xquik OpenAPI discovery failed. Try again.",
            ) from exc

    async def docs(self) -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Xquik OpenAPI Tool Server",
        )

    async def proxy(self, request: Request, path: str) -> Response:
        if not self.settings.api_key:
            raise HTTPException(
                status_code=503,
                detail="Xquik is not configured. Set XQUIK_API_KEY.",
            )
        method = request.method.upper()
        if method != "GET":
            _require_action_approval(request, self.settings)
        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Request body exceeds 1 MiB.",
            )
        headers = _upstream_headers(request, self.settings.api_key)
        url = _upstream_url(path)
        try:
            upstream_response = await self.upstream_request(
                method,
                url,
                list(request.query_params.multi_items()),
                body,
                headers,
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="Xquik request failed. Try again.",
            ) from exc
        except UpstreamResponseTooLarge as exc:
            raise HTTPException(
                status_code=502,
                detail="Xquik response exceeds 16 MiB.",
            ) from exc
        if len(upstream_response.content) > MAX_RESPONSE_BYTES:
            raise HTTPException(
                status_code=502,
                detail="Xquik response exceeds 16 MiB.",
            )
        if 300 <= upstream_response.status_code < 400:
            raise HTTPException(
                status_code=502,
                detail="Xquik returned an unexpected redirect.",
            )
        response_headers = {
            name: value
            for name in SAFE_RESPONSE_HEADERS
            if (value := upstream_response.headers.get(name)) is not None
        }
        response_headers["x-xquik-untrusted-content"] = "true"
        return Response(
            content=upstream_response.content,
            headers=response_headers,
            status_code=upstream_response.status_code,
        )


def create_app(
    *,
    settings: Settings | None = None,
    upstream_request: RequestUpstream = request_upstream,
    schema_loader: LoadSchema = load_upstream_schema,
) -> FastAPI:
    runtime = ProxyRuntime(
        settings=load_settings() if settings is None else settings,
        upstream_request=upstream_request,
        schema_loader=schema_loader,
    )
    app = FastAPI(
        docs_url=None,
        openapi_url=None,
        redoc_url=None,
        title="Xquik OpenAPI Tool Server",
    )
    app.add_api_route(
        "/health",
        runtime.health,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/openapi.json",
        runtime.openapi_document,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/docs",
        runtime.docs,
        methods=["GET"],
        include_in_schema=False,
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/api/v1/{path:path}",
        runtime.proxy,
        methods=PROXY_METHODS,
        include_in_schema=False,
    )
    return app


def _require_action_approval(request: Request, settings: Settings) -> None:
    if not settings.actions_enabled:
        raise HTTPException(
            status_code=403,
            detail="Xquik actions are disabled. Set XQUIK_ENABLE_ACTIONS=true.",
        )
    if request.headers.get("x-xquik-confirmation", "").lower() != "approved":
        raise HTTPException(
            status_code=428,
            detail=(
                "Explicit approval required. Send "
                "x-xquik-confirmation: approved for this call."
            ),
        )


def _upstream_headers(request: Request, api_key: str) -> dict[str, str]:
    headers = {
        "accept": request.headers.get("accept", "application/json"),
        "x-api-key": api_key,
        "xquik-api-contract": API_CONTRACT,
    }
    for name in ("content-type", "idempotency-key"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _upstream_url(path: str) -> str:
    segments = path.split("/")
    if not segments or any(
        not segment or segment in {".", ".."} or "\\" in segment for segment in segments
    ):
        raise HTTPException(status_code=400, detail="Invalid Xquik API path.")
    encoded_path = "/".join(quote(segment, safe="") for segment in segments)
    return f"{UPSTREAM_API_ROOT}/{encoded_path}"


app = create_app()
