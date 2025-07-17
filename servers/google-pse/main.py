import os
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List

app = FastAPI(
    title="Google Programmable Search Engine API",
    version="1.0.0",
    description="Provides web search functionality using Google's Custom Search JSON API.",
)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Pydantic models
# -------------------------------

class SearchItem(BaseModel):
    title: str = Field(..., description="The title of the search result")
    link: str = Field(..., description="The URL of the search result")
    snippet: str = Field(..., description="A snippet of text from the search result")
    displayLink: Optional[str] = Field(None, description="The display URL")
    formattedUrl: Optional[str] = Field(None, description="The formatted URL")

class SearchInformation(BaseModel):
    searchTime: float = Field(..., description="The time taken to perform the search")
    formattedSearchTime: str = Field(..., description="The formatted search time")
    totalResults: str = Field(..., description="The total number of search results")
    formattedTotalResults: str = Field(..., description="The formatted total results")

class Queries(BaseModel):
    request: Optional[List[dict]] = Field(None, description="The request query parameters")
    nextPage: Optional[List[dict]] = Field(None, description="Parameters for the next page")
    previousPage: Optional[List[dict]] = Field(None, description="Parameters for the previous page")

class Context(BaseModel):
    title: str = Field(..., description="The title of the custom search engine")

class SearchResponse(BaseModel):
    kind: str = Field(..., description="The kind of search response")
    url: dict = Field(..., description="URL information")
    queries: Queries = Field(..., description="Query information")
    context: Context = Field(..., description="Search engine context")
    searchInformation: SearchInformation = Field(..., description="Information about the search")
    items: Optional[List[SearchItem]] = Field(None, description="The search results")

# -------------------------------
# Routes
# -------------------------------

GOOGLE_SEARCH_URL = "https://customsearch.googleapis.com/customsearch/v1"

@app.get("/search", response_model=SearchResponse, summary="Perform a web search")
def search_web(
    q: str = Query(..., description="The search query"),
    cx: Optional[str] = Query(None, description="The Programmable Search Engine ID (can be set via GOOGLE_PSE_CX env var)"),
    api_key: Optional[str] = Query(None, description="Google API key (can be set via GOOGLE_API_KEY env var)"),
    num: Optional[int] = Query(10, ge=1, le=10, description="Number of search results to return (1-10)"),
    start: Optional[int] = Query(1, ge=1, le=91, description="The index of the first result to return"),
    safe: Optional[str] = Query("off", description="Search safety level: 'active' or 'off'"),
    lr: Optional[str] = Query(None, description="Language restriction (e.g., 'lang_en')"),
    cr: Optional[str] = Query(None, description="Country restriction (e.g., 'countryUS')"),
    dateRestrict: Optional[str] = Query(None, description="Date restriction (e.g., 'd1', 'w1', 'm1', 'y1')"),
    exactTerms: Optional[str] = Query(None, description="Phrase that all results must contain"),
    excludeTerms: Optional[str] = Query(None, description="Terms to exclude from results"),
    fileType: Optional[str] = Query(None, description="File type restriction (e.g., 'pdf', 'doc')"),
    siteSearch: Optional[str] = Query(None, description="Site to search within or exclude"),
    siteSearchFilter: Optional[str] = Query(None, description="Include ('i') or exclude ('e') siteSearch")
):
    """
    Performs a web search using Google's Custom Search JSON API.
    
    The API key and search engine ID can be provided as query parameters or set as environment variables:
    - GOOGLE_API_KEY: Your Google API key
    - GOOGLE_PSE_CX: Your Programmable Search Engine ID
    
    Returns search results in JSON format with metadata about the search.
    """
    
    # Get API key and search engine ID from parameters or environment variables
    google_api_key = api_key or os.getenv("GOOGLE_API_KEY")
    search_engine_id = cx or os.getenv("GOOGLE_PSE_CX")
    
    if not google_api_key:
        raise HTTPException(
            status_code=400, 
            detail="Google API key is required. Provide it as 'api_key' parameter or set GOOGLE_API_KEY environment variable."
        )
    
    if not search_engine_id:
        raise HTTPException(
            status_code=400, 
            detail="Programmable Search Engine ID is required. Provide it as 'cx' parameter or set GOOGLE_PSE_CX environment variable."
        )
    
    # Build request parameters
    params = {
        "key": google_api_key,
        "cx": search_engine_id,
        "q": q,
        "num": num,
        "start": start,
        "safe": safe
    }
    
    # Add optional parameters if provided
    optional_params = {
        "lr": lr,
        "cr": cr,
        "dateRestrict": dateRestrict,
        "exactTerms": exactTerms,
        "excludeTerms": excludeTerms,
        "fileType": fileType,
        "siteSearch": siteSearch,
        "siteSearchFilter": siteSearchFilter
    }
    
    for key, value in optional_params.items():
        if value is not None:
            params[key] = value
    
    try:
        response = requests.get(GOOGLE_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Check if the response contains an error
        if "error" in data:
            error_info = data["error"]
            raise HTTPException(
                status_code=error_info.get("code", 400),
                detail=f"Google API Error: {error_info.get('message', 'Unknown error')}"
            )
        
        # Validate required fields are present
        required_fields = ["kind", "url", "queries", "context", "searchInformation"]
        for field in required_fields:
            if field not in data:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Unexpected response format from Google API: missing '{field}'"
                )
        
        return data
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=503, 
            detail=f"Error connecting to Google Custom Search API: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"An internal error occurred: {e}"
        )

@app.get("/health", summary="Health check endpoint")
def health_check():
    """
    Simple health check endpoint to verify the service is running.
    """
    return {"status": "healthy", "service": "google-pse"}