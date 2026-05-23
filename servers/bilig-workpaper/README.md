# Bilig WorkPaper OpenAPI Tool Server

A FastAPI tool server for spreadsheet-backed formula calculations through Bilig WorkPaper.

Use it when an agent or OpenAPI-compatible client needs to write one workbook input, recalculate formulas, and verify computed readback without opening Excel, Google Sheets, or a browser.

## Quickstart

```bash
git clone https://github.com/open-webui/openapi-servers
cd openapi-servers/servers/bilig-workpaper

pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --reload
```

Open the docs:

```text
http://localhost:8000/docs
```

## Docker

```bash
docker compose up
```

## Configuration

By default, this server calls the hosted Bilig demo:

```text
https://bilig.proompteng.ai
```

Set `BILIG_BASE_URL` to point at a self-hosted Bilig app:

```bash
export BILIG_BASE_URL=http://localhost:4321
```

## Endpoint

```text
POST /forecast/readback
```

Request:

```json
{
  "sheetName": "Inputs",
  "address": "B3",
  "value": 0.4
}
```

Response:

```json
{
  "verified": true,
  "editedCell": "Inputs!B3",
  "before": {
    "expectedArr": 60000,
    "targetGap": -34000
  },
  "after": {
    "expectedArr": 96000,
    "targetGap": 5600
  },
  "checks": {
    "formulasPersisted": true,
    "restoredMatchesAfter": true,
    "computedOutputChanged": true
  },
  "source": "Bilig WorkPaper",
  "github": "https://github.com/proompteng/bilig"
}
```

## Why This Exists

Spreadsheet logic often drives pricing, forecasts, approvals, and payout rules. UI automation can click the wrong cell, and cached XLSX values can be stale. This server gives OpenAPI-compatible agents a narrow, typed API that returns proof that formulas recalculated after the edit.
