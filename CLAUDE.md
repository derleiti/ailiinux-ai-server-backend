# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AILinux AI Server Backend is a FastAPI-based Python service providing AI-powered capabilities including chat completions, vision analysis, image generation, and web crawling with intelligent content discovery. The backend aggregates multiple AI providers (Ollama, Gemini, Mistral, GPT-OSS, Stable Diffusion) into a unified API with intelligent routing, rate limiting, and content publishing workflows.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Server
```bash
# Development mode with auto-reload
uvicorn app.main:app --reload

# Production-like mode
uvicorn app.main:app --host 0.0.0.0 --port 9100

# Debug mode with verbose logging
uvicorn app.main:app --reload --log-level debug
```

### Testing
```bash
# Run all tests (requires pytest installation)
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_chat.py -v

# Run with verbose output and detailed tracebacks
python -m pytest tests/ -v --tb=short

# List all tests without running them
python -m pytest tests/ --collect-only -q
```

## Architecture Overview

### Core Application Structure

**Entry Point**: `app/main.py:create_app()` initializes the FastAPI application with:
- CORS middleware for cross-origin requests (configurable via `CORS_ALLOWED_ORIGINS`)
- Custom logging middleware for request/response tracking
- Redis-based rate limiting via `fastapi-limiter`
- Centralized exception handlers for consistent error responses
- Router composition with `/v1` prefixed routes for versioned API endpoints

**Configuration**: `app/config.py` uses Pydantic settings with environment variable validation:
- All settings have defaults and can be overridden via `.env` file
- Provider configurations (Ollama, Gemini, Mistral, etc.) with optional API keys
- Crawler settings for memory limits, flush intervals, and retention policies
- Timeout configurations for request handling and backend services

### Service Layer Architecture

The service layer (`app/services/`) implements core business logic with clear separation of concerns:

**Model Registry** (`model_registry.py`):
- Discovers available models from Ollama backend
- Caches model lists with TTL-based invalidation
- Auto-detects capabilities (vision, image generation) via pattern matching
- Provides unified model metadata across providers

**LLM Router** (`llm_router.py`):
- Routes requests to appropriate LLM backends based on task complexity
- Policy-based routing for different workloads (architecture, security reviews, long-form content)
- Configurable per-provider timeouts and token limits
- Fallback mechanisms for provider unavailability

**Chat Service** (`chat.py`):
- Streaming and non-streaming completions with provider abstraction
- Automatic uncertainty detection with web search fallback
- Crawler integration for website analysis workflows
- Message formatting and role conversion for different providers (Ollama, Gemini, Mistral)
- Special handling for Mistral model aliases

**Vision Service** (`vision.py`):
- Multi-modal chat with base64 image support
- Automatic vision model detection and routing
- Gemini and Ollama vision model integration
- Error handling with graceful fallbacks

**Crawler System** (`services/crawler/manager.py`):
- Asynchronous web crawling with depth control and page limits
- In-memory result buffering with configurable memory limits
- JSONL shard rotation for training data accumulation
- TF-IDF based relevance scoring and ranking
- Hourly flush to disk with retention policy (default 30 days)
- Automatic archival and compression of old shards
- Integration with chat models via `crawler.search` tool

**Auto Publisher** (`auto_publisher.py`):
- Automated content publishing to WordPress and bbPress
- Post scheduling and duplicate detection
- Integration with crawler results for content generation
- Configurable publish intervals and target categories/forums

**Orchestrator** (`orchestrator.py`):
- Coordinates crawler → summarization → publishing workflows
- Background job scheduling and queue management
- Error recovery and retry logic

### API Routes Structure

Routes are organized by feature domain in `app/routes/`:

- **Health**: `/health` - System health checks and status
- **Admin**: `/admin/*` - Administrative operations
- **MCP**: `/mcp/*` - Model Context Protocol integration
- **Orchestration**: `/orchestration/*` - Workflow coordination
- **Models**: `/v1/models` - List available AI models
- **Agents**: `/v1/agents/*` - Agent-based interactions
- **Chat**: `/v1/chat/completions` - Chat completion endpoints
- **Vision**: `/v1/vision/chat/completions` - Vision-enabled chat
- **SD**: `/v1/images/generations` - Stable Diffusion image generation
- **Crawler**: `/v1/crawler/*` - Web crawling and search endpoints
- **Posts**: `/v1/posts/*` - Content publishing endpoints

### Key Design Patterns

**HTTP Client Abstraction** (`utils/http_client.py`):
- Centralized HTTP client with retry logic and timeout handling
- Exponential backoff for transient failures
- Connection pooling and error normalization
- Used by crawler, publisher, and external API integrations

**Error Handling** (`utils/errors.py`):
- Standardized error responses: `{"error": {"message": str, "code": str}}`
- HTTP exception handlers in `main.py` ensure consistent error format
- Validation errors include detailed field-level error information

**Throttling** (`utils/throttle.py`):
- Request queue with concurrency limits (`MAX_CONCURRENT_REQUESTS`)
- Timeout-based queue management (`REQUEST_QUEUE_TIMEOUT`)
- Prevents backend overload during high traffic

### Crawler Training Data Workflow

The crawler implements a sophisticated data collection pipeline:

1. **Crawl Execution**: Jobs created via `/v1/crawler/jobs` or `/crawl` slash command
2. **RAM Buffer**: Recent results stored in memory (up to `CRAWLER_MAX_MEMORY_BYTES`)
3. **Hourly Rotation**: Background task flushes RAM deltas to JSONL shards every hour
4. **Shard Format**: `data/crawler_spool/train/crawl-train-YYYYMMDD-HH.jsonl`
5. **Search Integration**: Chat models query via `crawler.search` tool
6. **Retention**: Shards older than 30 days are gzipped and archived

**Training Data Fields**:
- `job_id`, `url`, `title`, `excerpt/summary`, `normalized_text`
- `matched_keywords`, `score`, `publish_date`, `created_at`
- `source_domain`, `labels`, `content_hash`, `tokens_est`

## Testing Strategy

Tests are organized by component in `tests/` directory:

- **Unit Tests**: Individual service and utility testing with mocking
- **Integration Tests**: End-to-end workflows (HTTP client → crawler → publisher)
- **Route Tests**: FastAPI endpoint testing with `httpx.AsyncClient`

**Key Test Files**:
- `test_chat.py`: Chat service functionality
- `test_crawler.py`: Crawler manager and job lifecycle
- `test_http_client.py`: HTTP client retry and error handling
- `test_auto_publisher.py`: Publishing workflows
- `test_integration.py`: Complete end-to-end scenarios

**Testing Conventions**:
- Use `@pytest.mark.asyncio` for async tests
- Mock external dependencies (HTTP requests, model APIs)
- Shared fixtures in `conftest.py` (when present)
- Test naming: `test_<component>_<behavior>`

## Environment Configuration

Key environment variables (see `.env.example` for complete list):

**Core Settings**:
- `REQUEST_TIMEOUT=30` - Default request timeout in seconds
- `OLLAMA_TIMEOUT_MS=15000` - Ollama backend timeout
- `MAX_CONCURRENT_REQUESTS=8` - Concurrency limit for request queue
- `CORS_ALLOWED_ORIGINS` - Comma-separated list of allowed origins

**Provider Backends**:
- `OLLAMA_BASE=http://localhost:11434` - Ollama API endpoint
- `STABLE_DIFFUSION_URL=http://localhost:7860` - SD WebUI endpoint
- `GEMINI_API_KEY` - Google Gemini API key (optional)
- `MIXTRAL_API_KEY` - Mistral/Mixtral API key (optional)
- `GPT_OSS_API_KEY`, `GPT_OSS_BASE_URL` - GPT-OSS configuration (optional)

**Crawler Configuration**:
- `CRAWLER_ENABLED=true` - Enable crawler functionality
- `CRAWLER_MAX_MEMORY_BYTES=268435456` - RAM buffer size (256MB default)
- `CRAWLER_FLUSH_INTERVAL=3600` - Flush interval in seconds (hourly)
- `CRAWLER_RETENTION_DAYS=30` - JSONL shard retention period

**WordPress Integration** (optional):
- `WORDPRESS_URL` - WordPress site URL
- `WORDPRESS_USER`, `WORDPRESS_PASSWORD` - WordPress credentials

**Redis** (required for rate limiting):
- `REDIS_URL=redis://localhost:6379/0` - Redis connection string

## Code Style and Conventions

- **PEP 8 Compliance**: 4-space indentation, snake_case for variables/functions/modules
- **Type Hints**: All route handlers and service methods use explicit type annotations
- **Async/Await**: All I/O operations are async for non-blocking execution
- **Pydantic Models**: Request/response validation via Pydantic schemas in `app/schemas/`
- **Logging**: Use module-level loggers: `logger = logging.getLogger("ailinux.<module>")`
- **Error Handling**: Raise `HTTPException` with standardized error dictionaries
- **Documentation**: Docstrings for complex logic; inline comments for non-obvious decisions

## Common Development Patterns

### Adding a New Route
1. Create route handler in `app/routes/<feature>.py`
2. Define request/response schemas in `app/schemas/<feature>.py`
3. Implement business logic in `app/services/<feature>.py`
4. Register router in `app/main.py:create_app()`
5. Add tests in `tests/test_<feature>.py`

### Adding a New AI Provider
1. Update `app/config.py` with provider settings
2. Extend `app/services/llm_router.py` with routing rules
3. Add provider-specific handling in `app/services/chat.py`
4. Update `.env.example` with new environment variables

### Crawler Integration
- Use `crawler_manager.create_job()` to start crawls
- Query results via `crawler_manager.search_results()` for in-memory search
- Access training shards in `data/crawler_spool/train/` for historical data
- Jobs are pruned after 24 hours; results persist in training shards

## Important File Locations

- **Application Entry**: `app/main.py`
- **Configuration**: `app/config.py`, `.env`
- **Core Services**: `app/services/chat.py`, `app/services/crawler/manager.py`
- **HTTP Client**: `app/utils/http_client.py`
- **Routes**: `app/routes/`
- **Tests**: `tests/`
- **Training Data**: `data/crawler_spool/train/`
- **Logs**: `logs/`

## Debugging Tips

- Use `--log-level debug` with uvicorn to see detailed request/response logs
- Check Redis connection if rate limiting fails: `redis-cli ping`
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Monitor crawler jobs via `/v1/crawler/jobs/<job_id>/status`
- Inspect training shards: `cat data/crawler_spool/train/crawl-train-*.jsonl | jq`
