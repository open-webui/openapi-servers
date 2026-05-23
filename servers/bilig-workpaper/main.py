import os
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DEFAULT_BILIG_BASE_URL = "https://bilig.proompteng.ai"

app = FastAPI(
    title="Bilig WorkPaper Formula Readback API",
    version="0.1.0",
    description=(
        "OpenAPI tool server for writing one Bilig WorkPaper input cell, "
        "recalculating formulas, and returning verified computed readback."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FormulaReadbackRequest(BaseModel):
    sheetName: str = Field(
        "Inputs",
        description="Worksheet containing the editable forecast input.",
        examples=["Inputs"],
    )
    address: str = Field(
        "B3",
        description="A1-style input cell address to edit before recalculation.",
        examples=["B3"],
    )
    value: float = Field(
        0.4,
        description="Numeric value to write before formula readback.",
        examples=[0.4],
    )


class FormulaSnapshot(BaseModel):
    expectedArr: float | None = Field(None, description="Computed expected ARR value.")
    targetGap: float | None = Field(None, description="Computed gap to target value.")


class FormulaChecks(BaseModel):
    formulasPersisted: bool = Field(
        ..., description="Formula definitions persisted after serialization."
    )
    restoredMatchesAfter: bool = Field(
        ..., description="Restored workbook readback matched post-edit values."
    )
    computedOutputChanged: bool = Field(
        ..., description="Dependent formula output changed after the input edit."
    )


class FormulaReadbackResponse(BaseModel):
    verified: bool = Field(
        ..., description="True only when Bilig verified the formula readback proof."
    )
    editedCell: str | None = Field(
        None, description="Edited worksheet cell, for example Inputs!B3."
    )
    before: FormulaSnapshot
    after: FormulaSnapshot
    checks: FormulaChecks
    source: str = Field("Bilig WorkPaper", description="Readback source.")
    github: str = Field(
        "https://github.com/proompteng/bilig", description="Bilig project URL."
    )


def bilig_base_url() -> str:
    base_url = os.getenv("BILIG_BASE_URL", DEFAULT_BILIG_BASE_URL).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=500, detail="BILIG_BASE_URL must start with http:// or https://"
        )
    return base_url


def compact_proof(proof: dict[str, Any]) -> FormulaReadbackResponse:
    if proof.get("verified") is not True:
        raise HTTPException(
            status_code=502,
            detail={"message": "Bilig returned an unverified response", "proof": proof},
        )

    before = proof.get("before") if isinstance(proof.get("before"), dict) else {}
    after = proof.get("after") if isinstance(proof.get("after"), dict) else {}
    checks = proof.get("checks") if isinstance(proof.get("checks"), dict) else {}

    return FormulaReadbackResponse(
        verified=True,
        editedCell=proof.get("editedCell"),
        before=FormulaSnapshot(
            expectedArr=before.get("expectedArr"),
            targetGap=before.get("targetGap"),
        ),
        after=FormulaSnapshot(
            expectedArr=after.get("expectedArr"),
            targetGap=after.get("targetGap"),
        ),
        checks=FormulaChecks(
            formulasPersisted=checks.get("formulasPersisted") is True,
            restoredMatchesAfter=checks.get("restoredMatchesAfter") is True,
            computedOutputChanged=checks.get("computedOutputChanged") is True,
        ),
    )


@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/forecast/readback",
    response_model=FormulaReadbackResponse,
    summary="Write one forecast input and return verified formula readback",
)
def forecast_readback(request: FormulaReadbackRequest) -> FormulaReadbackResponse:
    try:
        response = requests.post(
            f"{bilig_base_url()}/api/workpaper/n8n/forecast",
            json={
                "sheetName": request.sheetName,
                "address": request.address.upper(),
                "value": request.value,
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "OpenWebUI-Bilig-WorkPaper-Server/0.1",
            },
            timeout=30,
        )
        response.raise_for_status()
        proof = response.json()
    except requests.exceptions.RequestException as error:
        raise HTTPException(
            status_code=503, detail=f"Error connecting to Bilig: {error}"
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=502, detail=f"Bilig returned invalid JSON: {error}"
        ) from error

    if not isinstance(proof, dict):
        raise HTTPException(
            status_code=502,
            detail=f"Expected JSON object from Bilig, received {type(proof).__name__}",
        )

    return compact_proof(proof)
