# 🔎 iFlow Search Tool Server

A Node-native OpenAPI 3.1 tool server that exposes the [iFlow Search](https://platform.iflow.cn) API — web search, image search, and URL fetch — to any OpenAPI-compatible client (Open WebUI, Coze, custom agents).

> ⚠️ **Convention note.** Unlike the other servers in this repo (Python / FastAPI / uvicorn), iFlow Search is published on **npm** and runs via **`npx`**. There is no `main.py` or `requirements.txt` here — the server *is* the published [`@iflow-ai/search-openapi`](https://www.npmjs.com/package/@iflow-ai/search-openapi) package. Everything below is invocation, configuration, and registration; no local source needs to be edited.

📦 Built with:
⚡️ Node.js (≥ 18) • 📦 npm / npx • 📜 OpenAPI 3.1 • 🔍 iFlow Search API

---

## 🚀 Quickstart

No clone required. The server is a single `npx` invocation:

```bash
# Required: your iFlow API key, exported in the parent shell
export IFLOW_API_KEY="YOUR_IFLOW_API_KEY"

# Run the server (binds to 0.0.0.0:8787 by default)
npx -y @iflow-ai/search-openapi
```

Now visit:

- 🖥️ Swagger UI / interactive docs: `http://localhost:8787/openapi.json` (raw spec)
- ❤️ Health check: `http://localhost:8787/health`

> The current stable release on npm is `@iflow-ai/search-openapi@0.1.0` (the `latest` dist-tag). For reproducible installs, pin the version explicitly — e.g. `npx -y @iflow-ai/search-openapi@0.1.0`.

---

## 🔧 Configuration

All configuration is read from environment variables. The server reads `process.env` only — it does **not** load `.env` files or any on-disk configuration.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `IFLOW_API_KEY` | yes | — | Bearer token the server sends to iFlow as `Authorization: Bearer …`. **Never put this in a tracked file.** |
| `PORT` | no | `8787` | Listen port. |
| `IFLOW_OPENAPI_AUTH_TOKEN` | no | — | If set, every route except `GET /health` requires `Authorization: Bearer <token>` from the **caller**. This is an operator-defined gate token in front of the OpenAPI server — it is **not** an iFlow key. Absent ⇒ open mode (no auth on the server's HTTP surface). |
| `IFLOW_OPENAPI_CORS_ORIGIN` | no | — | When set (e.g. `*` or `https://your-openwebui.example.com`), the server emits the appropriate `Access-Control-Allow-*` headers. Required if a browser-side Open WebUI deployment talks to this server cross-origin. |
| `IFLOW_OPENAPI_CLIENT` | no | — | Declared host slug (e.g. `open-webui`) used in the startup banner and in upstream attribution. Allowed pattern: `[a-z0-9._-]{1,64}`. |

### Example: open mode behind a local Open WebUI (browser-side)

```bash
export IFLOW_API_KEY="YOUR_IFLOW_API_KEY"

IFLOW_OPENAPI_CLIENT=open-webui \
  IFLOW_OPENAPI_CORS_ORIGIN='*' \
  PORT=8787 \
  npx -y @iflow-ai/search-openapi
```

### Example: gated mode (server requires its own bearer)

```bash
export IFLOW_API_KEY="YOUR_IFLOW_API_KEY"
export IFLOW_OPENAPI_AUTH_TOKEN="YOUR_OPENAPI_AUTH_TOKEN"

IFLOW_OPENAPI_CLIENT=open-webui \
  PORT=8787 \
  npx -y @iflow-ai/search-openapi
```

In gated mode, every Open WebUI request must include
`Authorization: Bearer YOUR_OPENAPI_AUTH_TOKEN`. The token is compared with
`timingSafeEqual` server-side. `GET /health` is always reachable so platform
health probes still work.

---

## 🔌 Register in Open WebUI

1. In Open WebUI, open **Workspace → Tools → Add Tool Server** (or the equivalent OpenAPI tool registration screen for your release).
2. Fill in:
   - **URL**: `http://localhost:8787`
   - **OpenAPI spec path**: `/openapi.json`
   - **Auth**: *None* if the server is in open mode. If you set `IFLOW_OPENAPI_AUTH_TOKEN`, choose **Bearer** and paste `YOUR_OPENAPI_AUTH_TOKEN`.
3. Save. Open WebUI fetches `/openapi.json` and registers the three tools automatically.

The three iFlow tools become callable from any model that supports tool use.

---

## 📡 API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness probe. Never gated by `IFLOW_OPENAPI_AUTH_TOKEN`. |
| `GET` | `/openapi.json` | OpenAPI 3.1 document describing the three tool routes. |
| `POST` | `/tools/iflow_web_search` | Web search. Body: `{ "query": "…", "count": 1-10 }`. Returns titles, URLs, snippets. |
| `POST` | `/tools/iflow_image_search` | Image search. Body: `{ "query": "…", "count": 1-10 }`. Returns image URLs, titles, source pages. |
| `POST` | `/tools/iflow_web_fetch` | Fetch the readable contents of a single URL. Body: `{ "url": "https://…" }`. |

Each tool route is a thin pass-through to the iFlow Search API; request validation, error mapping, and response normalization happen inside the server before any payload is sent over the network.

### Example call (open mode)

```bash
curl -sS -X POST http://localhost:8787/tools/iflow_web_search \
  -H 'Content-Type: application/json' \
  -d '{"query":"iflow search","count":3}'
```

### Example call (gated mode)

```bash
curl -sS -X POST http://localhost:8787/tools/iflow_web_search \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_OPENAPI_AUTH_TOKEN' \
  -d '{"query":"iflow search","count":3}'
```

---

## 🔒 Security boundary

This is the most important section. Read it once.

- **`IFLOW_API_KEY` stays inside the local `@iflow-ai/search-openapi` server process.** It is read from `process.env`, attached as `Authorization: Bearer …` on outbound requests to `https://platform.iflow.cn`, and never written to disk, never logged, never echoed.
- **Open WebUI never receives `IFLOW_API_KEY`.** The browser / Open WebUI backend only ever sees (a) the URL of this OpenAPI server and (b), if you set one, the operator-defined `IFLOW_OPENAPI_AUTH_TOKEN` bearer.
- **`IFLOW_OPENAPI_AUTH_TOKEN` is NOT an iFlow key.** It is an operator-defined gate token in front of the local OpenAPI server, used only by callers of *this* server (Open WebUI, curl, your own agent). Choose any opaque value you like; it is unrelated to your iFlow account.
- **Do not commit a real `IFLOW_API_KEY`.** Inject it via `export` in the shell that launches `npx`, via your secret store, or via a `direnv` block — never into a tracked file.
- For deployments where Open WebUI must reach the server over the public Internet, terminate TLS at a reverse proxy and either (a) set `IFLOW_OPENAPI_AUTH_TOKEN` so the server enforces a bearer, or (b) enforce auth at the proxy/tunnel layer (Cloudflare Access policy on a named tunnel, an nginx layer that checks a fixed header, a managed API gateway). Do not expose the open mode to the public Internet.

---

## 🧰 Source, issues, contributions

- 📦 npm: <https://www.npmjs.com/package/@iflow-ai/search-openapi>
- 🛠️ Source repo (monorepo containing the server, the core SDK, and the LangChain / MCP adapters): <https://github.com/zhengyanglsun/iflow-search-js>
- ❓ iFlow platform docs: <https://platform.iflow.cn/docs>

Issues and PRs against the server itself live in the source repo above. This folder is the Open WebUI registration recipe.

---

## 📝 License

MIT — same as the rest of this repository, and same as the published [`@iflow-ai/search-openapi`](https://www.npmjs.com/package/@iflow-ai/search-openapi) package.
