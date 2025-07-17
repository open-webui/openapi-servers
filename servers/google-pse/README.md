# 🔍 Google PSE Tool Server

A sleek and simple FastAPI-based server to provide web search functionality using Google's Programmable Search Engine (PSE) via the Custom Search JSON API.

📦 Built with:  
⚡️ FastAPI • 📜 OpenAPI • 🧰 Python • 🔍 Google Custom Search API

---

## 🚀 Quickstart

Clone the repo and get started in seconds:

```bash
git clone https://github.com/open-webui/openapi-servers
cd openapi-servers/servers/google-pse

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
export GOOGLE_API_KEY="your_google_api_key_here"
export GOOGLE_PSE_CX="your_search_engine_id_here"

# Run the server
uvicorn main:app --host 0.0.0.0 --reload
```

---

## 🔧 Configuration

### Required Environment Variables

- `GOOGLE_API_KEY`: Your Google API key with Custom Search API enabled
- `GOOGLE_PSE_CX`: Your Programmable Search Engine ID

### Getting Your Credentials

1. **Google API Key**:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Custom Search JSON API
   - Create credentials (API Key)

2. **Programmable Search Engine ID**:
   - Visit [Google Programmable Search Engine](https://programmablesearchengine.google.com/)
   - Create a new search engine
   - Copy the Search Engine ID (cx parameter)

---

## 🔍 About

This server is part of the OpenAPI Tools Collection. Use it to perform web searches programmatically, retrieve search results with metadata, and integrate search functionality into your applications — all wrapped in a developer-friendly OpenAPI interface.

### Features

- 🌐 Web search using Google's Custom Search JSON API
- 🎯 Advanced search parameters (language, country, date restrictions, etc.)
- 📊 Rich metadata including search timing and result counts
- 🔒 Configurable safe search filtering
- 📄 Support for file type and site-specific searches
- 🚀 Fast and reliable RESTful API

Compatible with any OpenAPI-supported ecosystem, including:

- 🌀 FastAPI
- 📘 Swagger UI
- 🧪 API testing tools
- 🤖 AI agents and LLMs

---

## 📡 API Endpoints

### `GET /search`

Perform a web search with comprehensive parameters:

**Required Parameters:**
- `q`: Search query string

**Optional Parameters:**
- `num`: Number of results (1-10, default: 10)
- `start`: Starting index for results (default: 1)
- `safe`: Safe search level ('active' or 'off')
- `lr`: Language restriction (e.g., 'lang_en')
- `cr`: Country restriction (e.g., 'countryUS')
- `dateRestrict`: Date restriction ('d1', 'w1', 'm1', 'y1')
- `exactTerms`: Phrase that must appear in all results
- `excludeTerms`: Terms to exclude from results
- `fileType`: File type filter ('pdf', 'doc', etc.)
- `siteSearch`: Specific site to search
- `siteSearchFilter`: Include ('i') or exclude ('e') site

### `GET /health`

Health check endpoint to verify service status.

---

## 🚧 Customization

Extend the search functionality, add custom filters, or integrate with other APIs. Perfect for:

- 🤖 AI agent web research capabilities
- 📊 Automated content discovery
- 🔍 Custom search applications
- 📈 SEO and market research tools

---

## 🌐 API Documentation

Once running, explore auto-generated interactive docs:

🖥️ Swagger UI: http://localhost:8000/docs  
📄 OpenAPI JSON: http://localhost:8000/openapi.json

---

## 🐳 Docker Support

Run with Docker Compose:

```bash
# Set environment variables in your shell or .env file
export GOOGLE_API_KEY="your_api_key"
export GOOGLE_PSE_CX="your_search_engine_id"

# Start the service
docker-compose up --build
```

---

## 📝 Example Usage

```bash
# Basic search
curl "http://localhost:8000/search?q=OpenAI+GPT"

# Advanced search with filters
curl "http://localhost:8000/search?q=machine+learning&num=5&lr=lang_en&dateRestrict=m1"

# Site-specific search
curl "http://localhost:8000/search?q=python+tutorial&siteSearch=github.com&siteSearchFilter=i"
```

---

Made with ❤️ by the Open WebUI community 🌍  
Explore more tools ➡️ https://github.com/open-webui/openapi-servers