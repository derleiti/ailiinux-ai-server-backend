# Repository Guidelines

## Project Structure & Module Organization
The FastAPI backend lives in `app/`, with `main.py` composing routers, middleware, and mounts. Keep route handlers in `app/routes/` thin—delegate core logic to `app/services/` and shared helpers to `app/utils/`. WordPress UI code rests in `/root/wordpress/html/wp-content/plugins/nova-ai-frontend` and should remain English-only. Defaults come from `app/config.py`; adjust via environment variables only when necessary. Tests under `tests/` mirror the route layout and share fixtures through `tests/conftest.py`.

## Build, Test, and Development Commands
Create a virtualenv with `python -m venv .venv && source .venv/bin/activate`. Install dependencies using `pip install -r requirements.txt`. Run the API locally with `uvicorn app.main:app --reload`; for production-like checks, prefer `uvicorn app.main:app --host 0.0.0.0 --port 9100`. Execute the async suite via `pytest`; ensure it passes before pushing. When debugging, tail server logs with `uvicorn ... --reload --log-level debug` only as needed.

## Coding Style & Naming Conventions
Follow PEP 8, using four-space indentation and snake_case for variables, functions, and modules. Reserve `CamelCase` for Pydantic models or classes. Route functions stay async with explicit return types and minimal comments. Keep business logic in services, not routers. Favor reusable helpers in `app/utils/` and document non-obvious decisions inline.

## Testing Guidelines
Write tests with `pytest` and `httpx.AsyncClient` fixtures, targeting FastAPI routes end-to-end. Name tests after behaviors (e.g., `test_chat_streams_tokens`) and cover success, failure, and throttling paths. Add shared fixtures or mocks to `tests/conftest.py` rather than duplicating setup. Run `pytest` locally after meaningful changes to ensure parity with CI expectations.

## Commit & Pull Request Guidelines
Use Conventional Commits such as `feat: add streaming vision endpoint`, keeping each commit scoped to one logical change. Pull requests should summarize behavioral impact, list validation commands (e.g., `pytest`, `uvicorn`), and link relevant tickets or documentation. Call out new environment variables, config toggles, migrations, or external service changes, and request review from the appropriate service owner.

## Security & Configuration Tips
Never commit `.env` contents; document required keys alongside feature docs. Respect defaults in `app/config.py` for timeouts, concurrency, and SSL. Validate integrations locally with `uvicorn` before enabling them in shared environments, and escalate any credential handling changes for review.

## Crawler Training Data Management

Chat models can utilize the `crawler.search` tool to retrieve relevant information. This tool searches both in-memory crawl results and historical JSONL shards.

Crawl results are rotated hourly into JSONL shards under `data/crawler_spool/train/` with a naming convention of `crawl-train-${YYYYMMDD-HH}.jsonl`. These shards accumulate training data for models.

Data retention policy dictates keeping the last 30 days of shards. Older shards are gzipped and moved to `data/crawler_spool/archive/`.

**Environment Variables:**

*   `CRAWLER_MAX_MEMORY_BYTES`: Maximum memory (in bytes) for in-RAM crawl results before spilling to disk.
*   `CRAWLER_FLUSH_INTERVAL`: Interval (in seconds) for hourly flushing of RAM deltas to JSONL shards.
*   `CRAWLER_RETENTION_DAYS`: Number of days to retain JSONL shards before gzipping and archiving.
*   `CRAWLER_TRAIN_DIR`: Directory for storing JSONL training data shards.

