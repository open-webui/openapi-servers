import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# --- Nano Empire Monetization Patch ---
try:
    from nano_empire_guardrails import monetize
    original_add_api_route = FastAPI.add_api_route
    def monetized_add_api_route(self, path: str, endpoint, *args, **kwargs):
        if not any(path.startswith(prefix) for prefix in ["/docs", "/redoc", "/openapi"]):
            endpoint = monetize(credits_per_call=1)(endpoint)
        return original_add_api_route(self, path, endpoint, *args, **kwargs)
    FastAPI.add_api_route = monetized_add_api_route
except ImportError:
    pass
# --------------------------------------

from pydantic import BaseModel, Field
from typing import Optional

# --- LLM/SQL libraries ---
from langchain_experimental.sql import SQLDatabaseChain
from langchain_community.llms.openai import OpenAI
from langchain_community.utilities import SQLDatabase

from sqlalchemy.exc import SQLAlchemyError

# -- Load DB URL from environment variable --
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Set this in your environment


# -------------------------------
# Pydantic models
# -------------------------------
class SQLChatInput(BaseModel):
    query: str = Field(
        ...,
        description="Your question or task in natural language (e.g. 'Show me the top 10 customers by sales.')",
    )


class SQLChatOutput(BaseModel):
    sql: str = Field(..., description="SQL that was executed")
    answer: str = Field(..., description="Answer to your query, from the database")
    raw_result: Optional[list] = Field(
        None, description="Raw result rows (list of dict/tuples)"
    )


# -------------------------------
# API Setup
# -------------------------------
app = FastAPI(
    title="Chat with SQL API",
    version="1.0.0",
    description=(
        "Chat in natural language with any SQL database using LLMs. "
        "Query and analyze your data conversationally!"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------
# LLM + SQL Chain Setup (singleton)
# -------------------------------
def get_chain():
    # Initiate reflected SQLAlchemy DB
    db = SQLDatabase.from_uri(DATABASE_URL)
    # LLM instance: using OpenAI GPT (or swap for your preferred)
    llm = OpenAI(
        temperature=0, openai_api_key=OPENAI_API_KEY, model_name="gpt-3.5-turbo"
    )
    return SQLDatabaseChain.from_llm(
        llm, db, verbose=True, return_sql=True, return_intermediate_steps=True
    )


sql_chain = get_chain()


# -------------------------------
# Schema endpoint
# -------------------------------
@app.get("/schema", summary="Get database schema overview")
def get_db_schema():
    """
    Returns the tables and columns for the currently connected database.
    """
    try:
        db = sql_chain.database
        return db.get_table_info()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve schema info: {e}"
        )


# -------------------------------
# Chatting endpoint
# -------------------------------
@app.post(
    "/chat_sql", response_model=SQLChatOutput, summary="Chat with your SQL database"
)
def chat_sql(data: SQLChatInput):
    """
    Enter a natural language instruction/question, get answer from your database.
    """
    try:
        # Run chain
        result = sql_chain({"query": data.query})
        # result example: {'result': 'Answer in plain text', 'intermediate_steps': {'sql_cmd': sql, ...}}
        answer = result["result"]
        sql = None
        raw_result = None
        if "intermediate_steps" in result and "sql_cmd" in result["intermediate_steps"]:
            sql = result["intermediate_steps"]["sql_cmd"]
        if "intermediate_steps" in result and "result" in result["intermediate_steps"]:
            raw_result = result["intermediate_steps"]["result"]
        return SQLChatOutput(sql=sql or "", answer=answer, raw_result=raw_result)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")
