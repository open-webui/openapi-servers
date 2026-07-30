from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from config import API_CONTRACT, UPSTREAM_API_ROOT, Settings
from fastapi import HTTPException
from main import MAX_RESPONSE_BYTES, _upstream_url, create_app
from schema import prepare_openapi_schema


def source_schema() -> dict[str, Any]:
    return {
        "components": {"securitySchemes": {"apiKey": {"type": "apiKey"}}},
        "info": {"description": "Upstream description.", "title": "Xquik API"},
        "openapi": "3.1.0",
        "paths": {
            "/account": {
                "get": {
                    "operationId": "getAccount",
                    "responses": {"200": {"description": "OK"}},
                    "security": [{"apiKey": []}],
                },
                "patch": {
                    "operationId": "updateAccount",
                    "responses": {"200": {"description": "OK"}},
                    "security": [{"apiKey": []}],
                },
            },
            "/x/tweets/search": {
                "get": {
                    "operationId": "searchTweets",
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
        "security": [{"apiKey": []}],
        "servers": [{"url": "https://xquik.com/api/v1"}],
    }


class RecordingRequester:
    def __init__(self, response: httpx.Response | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = (
            response
            if response is not None
            else httpx.Response(
                200,
                content=b'{"ok":true}',
                headers={"content-type": "application/json", "server": "private"},
            )
        )

    async def __call__(
        self,
        method: str,
        url: str,
        query: Sequence[tuple[str, str]],
        body: bytes,
        headers: Mapping[str, str],
    ) -> httpx.Response:
        self.calls.append(
            {
                "body": body,
                "headers": dict(headers),
                "method": method,
                "query": list(query),
                "url": url,
            }
        )
        return self.response


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requester = RecordingRequester()

    async def _client(
        self,
        *,
        actions_enabled: bool = False,
        api_key: str = "secret-key",
        schema_loader=None,
        upstream_request=None,
    ) -> httpx.AsyncClient:
        async def default_schema_loader() -> Mapping[str, Any]:
            return source_schema()

        app = create_app(
            settings=Settings(
                api_key=api_key,
                actions_enabled=actions_enabled,
            ),
            upstream_request=upstream_request or self.requester,
            schema_loader=schema_loader or default_schema_loader,
        )
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def test_health_reports_configuration_without_secret(self) -> None:
        async with await self._client(actions_enabled=True) as client:
            response = await client.get("/health")

        self.assertEqual(
            response.json(),
            {"actions_enabled": True, "configured": True, "ok": True},
        )
        self.assertNotIn("secret-key", response.text)

    async def test_get_uses_fixed_origin_and_safe_headers(self) -> None:
        async with await self._client() as client:
            response = await client.get(
                "/api/v1/x/tweets/search",
                params=[("q", "open webui"), ("tag", "one"), ("tag", "two")],
                headers={
                    "authorization": "Bearer attacker",
                    "cookie": "session=attacker",
                    "x-api-key": "attacker-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-xquik-untrusted-content"], "true")
        self.assertEqual(
            self.requester.calls,
            [
                {
                    "body": b"",
                    "headers": {
                        "accept": "*/*",
                        "x-api-key": "secret-key",
                        "xquik-api-contract": API_CONTRACT,
                    },
                    "method": "GET",
                    "query": [
                        ("q", "open webui"),
                        ("tag", "one"),
                        ("tag", "two"),
                    ],
                    "url": f"{UPSTREAM_API_ROOT}/x/tweets/search",
                }
            ],
        )

    async def test_missing_key_blocks_proxy(self) -> None:
        async with await self._client(api_key="") as client:
            response = await client.get("/api/v1/x/tweets/search")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.requester.calls, [])

    async def test_actions_are_disabled_by_default(self) -> None:
        async with await self._client() as client:
            response = await client.post("/api/v1/x/tweets", json={"text": "x"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.requester.calls, [])

    async def test_action_requires_per_call_confirmation(self) -> None:
        async with await self._client(actions_enabled=True) as client:
            response = await client.post("/api/v1/x/tweets", json={"text": "x"})

        self.assertEqual(response.status_code, 428)
        self.assertEqual(self.requester.calls, [])

    async def test_approved_action_forwards_body_and_idempotency(self) -> None:
        async with await self._client(actions_enabled=True) as client:
            response = await client.post(
                "/api/v1/x/tweets",
                content=b'{"text":"approved"}',
                headers={
                    "content-type": "application/json",
                    "idempotency-key": "request-1",
                    "x-xquik-confirmation": "approved",
                },
            )

        self.assertEqual(response.status_code, 200)
        call = self.requester.calls[0]
        self.assertEqual(call["body"], b'{"text":"approved"}')
        self.assertEqual(call["headers"]["idempotency-key"], "request-1")
        self.assertEqual(call["headers"]["content-type"], "application/json")
        self.assertNotIn("x-xquik-confirmation", call["headers"])

    async def test_redirect_is_rejected_without_forwarding_location(self) -> None:
        self.requester.response = httpx.Response(
            302,
            headers={"location": "https://example.com/credential-capture"},
        )
        async with await self._client() as client:
            response = await client.get("/api/v1/account")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("location", response.headers)

    async def test_network_failure_returns_generic_error(self) -> None:
        async def fail_request(*_args, **_kwargs) -> httpx.Response:
            raise httpx.ConnectError(
                "private failure",
                request=httpx.Request("GET", "https://xquik.com"),
            )

        async with await self._client(upstream_request=fail_request) as client:
            response = await client.get("/api/v1/account")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private failure", response.text)

    async def test_large_response_is_rejected(self) -> None:
        self.requester.response = httpx.Response(
            200,
            content=b"x" * (MAX_RESPONSE_BYTES + 1),
        )
        async with await self._client() as client:
            response = await client.get("/api/v1/account")

        self.assertEqual(response.status_code, 502)
        self.assertIn("16 MiB", response.text)

    async def test_large_body_is_rejected(self) -> None:
        async with await self._client(actions_enabled=True) as client:
            response = await client.post(
                "/api/v1/x/tweets",
                content=b"x" * 1_048_577,
                headers={"x-xquik-confirmation": "approved"},
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.requester.calls, [])

    async def test_openapi_is_cached_and_read_only_by_default(self) -> None:
        calls = 0

        async def schema_loader() -> Mapping[str, Any]:
            nonlocal calls
            calls += 1
            return source_schema()

        async with await self._client(schema_loader=schema_loader) as client:
            first = await client.get("/openapi.json")
            second = await client.get("/openapi.json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(calls, 1)
        schema = first.json()
        self.assertEqual(schema["servers"], [{"url": "/api/v1"}])
        self.assertEqual(schema["security"], [])
        self.assertNotIn("securitySchemes", schema["components"])
        self.assertNotIn("patch", schema["paths"]["/account"])
        self.assertIn("/health", schema["paths"])
        self.assertEqual(
            schema["paths"]["/health"]["get"]["servers"],
            [{"url": "/"}],
        )

    async def test_openapi_exposes_approved_actions_when_enabled(self) -> None:
        async with await self._client(actions_enabled=True) as client:
            response = await client.get("/openapi.json")

        operation = response.json()["paths"]["/account"]["patch"]
        confirmation = operation["parameters"][-1]
        self.assertEqual(confirmation["name"], "x-xquik-confirmation")
        self.assertEqual(confirmation["schema"]["const"], "approved")
        self.assertNotIn("security", operation)

    async def test_invalid_openapi_document_fails_closed(self) -> None:
        async def invalid_schema() -> Mapping[str, Any]:
            return {"openapi": "2.0", "paths": {}}

        async with await self._client(schema_loader=invalid_schema) as client:
            response = await client.get("/openapi.json")

        self.assertEqual(response.status_code, 502)


class SchemaTests(unittest.TestCase):
    def test_prepare_schema_does_not_mutate_source(self) -> None:
        source = source_schema()
        prepared = prepare_openapi_schema(source, actions_enabled=False)

        self.assertIn("patch", source["paths"]["/account"])
        self.assertNotIn("patch", prepared["paths"]["/account"])

    def test_prepare_schema_rejects_invalid_path_items(self) -> None:
        source = source_schema()
        source["paths"]["/bad"] = "not-an-object"

        with self.assertRaisesRegex(TypeError, "Invalid OpenAPI path item"):
            prepare_openapi_schema(source, actions_enabled=False)

    def test_prepare_schema_normalizes_live_prefixed_paths(self) -> None:
        source = source_schema()
        source["paths"]["/api/v1/x/users/{id}"] = source["paths"].pop(
            "/x/tweets/search"
        )

        prepared = prepare_openapi_schema(source, actions_enabled=False)

        self.assertIn("/x/users/{id}", prepared["paths"])
        self.assertNotIn("/api/v1/x/users/{id}", prepared["paths"])

    def test_upstream_url_encodes_segments_and_rejects_traversal(self) -> None:
        self.assertEqual(
            _upstream_url("x/users/user name"),
            f"{UPSTREAM_API_ROOT}/x/users/user%20name",
        )
        with self.assertRaises(HTTPException):
            _upstream_url("x/../account")


if __name__ == "__main__":
    unittest.main()
