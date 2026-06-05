import requests
import reverse_geocoder as rg # Added reverse_geocoder
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
from typing import Optional, List # Removed Literal, no longer needed for query param

app = FastAPI(
    title="Weather API",
    version="1.0.0",
    description="Provides weather retrieval by latitude and longitude using Open-Meteo.", # Updated description
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

class CurrentWeather(BaseModel):
    time: str = Field(..., description="ISO 8601 format timestamp")
    temperature_2m: float = Field(..., alias="temperature_2m", description="Air temperature at 2 meters above ground")
    wind_speed_10m: float = Field(..., alias="wind_speed_10m", description="Wind speed at 10 meters above ground")

class HourlyUnits(BaseModel):
    time: str
    temperature_2m: str
    relative_humidity_2m: str
    wind_speed_10m: str

class HourlyData(BaseModel):
    time: List[str]
    temperature_2m: List[float]
    relative_humidity_2m: List[int] # Assuming humidity is integer percentage
    wind_speed_10m: List[float]

class WeatherForecastOutput(BaseModel):
    latitude: float
    longitude: float
    generationtime_ms: float
    utc_offset_seconds: int
    timezone: str
    timezone_abbreviation: str
    elevation: float
    current: CurrentWeather = Field(..., description="Current weather conditions")
    hourly_units: HourlyUnits
    hourly: HourlyData

# -------------------------------
# Routes
# -------------------------------

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
# Countries officially using Fahrenheit
FAHRENHEIT_COUNTRIES = {"US", "LR", "MM"} # USA, Liberia, Myanmar

@app.get("/forecast", response_model=WeatherForecastOutput, summary="Get current weather and forecast")
def get_weather_forecast(
    latitude: float = Query(..., description="Latitude for the location (e.g., 52.52)"),
    longitude: float = Query(..., description="Longitude for the location (e.g., 13.41)")
):
    """
    Retrieves current weather conditions and hourly forecast data
    for the specified latitude and longitude using the Open-Meteo API.
    Temperature unit (Celsius/Fahrenheit) is determined automatically based on location.
    """
    # Determine temperature unit based on location
    try:
        geo_results = rg.search((latitude, longitude), mode=1) # mode=1 for single result
        if geo_results:
            country_code = geo_results[0]['cc']
            temperature_unit = "fahrenheit" if country_code in FAHRENHEIT_COUNTRIES else "celsius"
        else:
            # Default to Celsius if country cannot be determined
            temperature_unit = "celsius"
    except Exception:
        # Handle potential errors during geocoding, default to Celsius
        temperature_unit = "celsius"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,wind_speed_10m",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": "auto",
        "temperature_unit": temperature_unit # Use determined unit
    }
    try:
        response = requests.get(OPEN_METEO_URL, params=params)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()

        # Basic validation to ensure expected keys are present
        if "current" not in data or "hourly" not in data:
             raise HTTPException(status_code=500, detail="Unexpected response format from Open-Meteo API")

        # Pydantic will automatically validate the structure based on WeatherForecastOutput
        return data

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Error connecting to Open-Meteo API: {e}")
    except Exception as e:
        # Catch other potential errors during processing
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
