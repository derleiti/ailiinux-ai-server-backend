# Gemini Workspace Analysis

This document provides a comprehensive overview of the projects and development conventions within this workspace. It is intended to be used as a guide for developers and AI agents to understand the codebase and contribute effectively.

## Project Overview

This workspace contains the `ailinux-ai-server-backend` project, a machine learning server built with FastAPI (Python). It provides AI-powered services and leverages libraries like `torch`, `transformers`, and `pillow`. The application is structured in a modular way, with different routers for services like agents, chat, crawler, models, stable diffusion, and vision.

The key features of the project are:
- **Multi-provider LLM chat interface**: Supports Ollama, Mistral, Gemini, and any GPT-OSS compatible API.
- **Intelligent web crawler**: A sophisticated web crawler built with `crawlee` and `Playwright`, featuring a job-based architecture, content scoring, AI-powered summarization, and BM25 search.
- **WordPress integration**: An auto-publishing system that generates articles from crawled data and posts them to WordPress and bbPress.
- **Stable Diffusion image generation integration**: Provides an API for generating images using Stable Diffusion.
- **Vision AI capabilities**: Supports vision models for image analysis.

## Building and Running

The following commands are used to build, run, and test the project.

*   **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
*   **Run Development Server:**
    ```bash
    uvicorn app.main:app --reload
    ```
*   **Run in a production-like environment:**
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 9100
    ```
*   **Run Tests:**
    ```bash
    pytest
    ```

## Architecture Overview

### Layer Structure
```
app/
├── main.py              # FastAPI app creation, CORS, router registration, startup/shutdown
├── config.py            # Pydantic settings with .env loading
├── routes/              # API endpoints (thin controllers)
│   ├── chat.py          # POST /v1/chat/completions (streaming)
│   ├── vision.py        # POST /v1/vision (image analysis)
│   ├── crawler.py       # Crawler job management + BM25 search
│   ├── posts.py         # WordPress post creation
│   ├── agents.py        # Agent tool definitions (crawler, WordPress)
│   ├── models.py        # GET /v1/models (registry listing)
│   └── sd.py            # Stable Diffusion generation
├── services/            # Business logic
│   ├── chat.py          # Multi-provider chat orchestration with auto web search
│   ├── model_registry.py # Dynamic model discovery (Ollama, cloud APIs)
│   ├── vision.py        # Vision model routing (Gemini/Ollama)
│   ├── agents.py        # Tool specs for AI agents
│   ├── wordpress.py     # WordPress REST API client
│   ├── web_search.py    # DuckDuckGo web search
│   ├── crawler/
│   │   └── manager.py   # Crawlee-based crawler with BM25 indexing
│   └── sd.py            # Stable Diffusion client
├── schemas/             # Pydantic request/response models
└── utils/               # HTTP helpers, error formatting, throttling
```

### Key Architectural Patterns

**Multi-Provider Model Routing (`services/model_registry.py`)**
- Models prefixed with `mistral/`, `gemini/`, `gpt-oss:`, or Ollama local models
- Dynamic discovery from Ollama + static cloud providers
- 30-second caching with async lock for concurrent requests
- Vision capability detection via regex on model names

**Chat Service Intelligence (`services/chat.py`)**
- Auto-triggers web search when detecting uncertainty phrases ("I don't know", etc.)
- Auto-triggers crawler for website-related queries ("crawl", "website", etc.)
- Routes to appropriate provider (Ollama, Mistral, Gemini, GPT-OSS)
- Streaming SSE responses for all providers

**Web Crawler (`services/crawler/manager.py`)**
- Crawlee-based async crawler with Playwright
- BM25 (rank-bm25) search index with tokenization
- AI-powered summarization of crawled content
- Hourly JSONL shard flushing for training data
- Automatic memory management and retention policy
- Periodic compaction of old shards

**WordPress Integration**
- REST API client with Basic Auth
- Media upload, post creation, category management
- Integrated with crawler results for automated publishing

## WordPress Plugin Context

`nova-ai-frontend/` contains a WordPress plugin that:
- Renders chat UI via shortcode
- FAB (floating action button) for chat
- Scheduled crawler integration
- Post discussion features
- Configured via WordPress admin settings page

## Important Implementation Details

### Virtual Environment Path Workaround
`app/main.py` lines 6-11: Manually adds `.venv/lib/python3.12/site-packages` to `sys.path`. This is a workaround for an environment issue where uvicorn doesn't correctly use the virtual environment. **Do not remove this without fixing the underlying issue.**

### Model ID Conventions
- `mistral/mixtral-8x7b` → routed to Mistral API
- `gemini/gemini-2.0-flash-exp` → routed to Gemini API
- `gpt-oss:cloud`, `gpt-oss:120b-cloud` → generic OpenAI-compatible API
- `llama3.2-vision`, `llava` → routed to vision endpoints
- All other IDs → routed to Ollama

## Development Conventions

The following development conventions are used in this project.

*   **Source Code:** Source code is located in the `app/` directory, organized by domain. Core logic is delegated to `app/services/` and shared helpers to `app.utils/`.
*   **Tests:** The project documentation mentions that tests are located in the `tests/` directory and mirror the source code structure, with shared fixtures in `tests/conftest.py`. However, these files were not found during the investigation.
*   **Commits:** Commits should follow the Conventional Commits specification.
*   **Pull Requests:** Pull requests should have a concise description and be linked to an issue.
*   **Security:** Never commit secrets. Use a local `.env` file.
*   **Formatting:** Use PEP 8, with four-space indentation and snake_case for variables, functions, and modules. `CamelCase` is used for Pydantic models or classes.