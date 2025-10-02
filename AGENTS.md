# Repository Guidelines

## Project Structure & Module Organization
The FastAPI backend lives in `app/`, with `app/main.py` wiring routers, middleware, and mounts. Keep route handlers under `app/routes/` lean—push business logic into `app/services/` and shared utilities into `app/utils/`. Defaults surface in `app/config.py`. Tests mirror this layout in `tests/`, sharing fixtures through `tests/conftest.py`. WordPress UI assets stay under `/root/wordpress/html/wp-content/plugins/nova-ai-frontend` and remain English-only.

## Build, Test, and Development Commands
Create a virtualenv with `python -m venv .venv && source .venv/bin/activate`, then install deps via `pip install -r requirements.txt`. Run the API locally using `uvicorn app.main:app --reload`. For production-like checks, prefer `uvicorn app.main:app --host 0.0.0.0 --port 9100`. Execute the suite with `pytest`; rerun after meaningful backend or plugin changes.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation, snake_case for modules, functions, and variables, and reserve `CamelCase` for Pydantic models or classes. Route functions stay async with explicit return types. Keep comments minimal and focused on non-obvious decisions. Business logic belongs in services, not routers.

## Testing Guidelines
Use `pytest` with the async fixtures already defined in `tests/conftest.py`. Name tests for the behavior they cover (e.g., `test_chat_streams_tokens`). Cover success, failure, and throttling paths. When adding fixtures or mocks, centralize them in `tests/conftest.py` to avoid duplication.

## Commit & Pull Request Guidelines
Follow Conventional Commits, such as `feat: add streaming vision endpoint`, and keep each commit scoped to one change. Pull requests should note behavioral impact, list validation commands (e.g., `pytest`, `uvicorn app.main:app --reload`), and link tickets or docs. Call out new environment variables, config toggles, migrations, or external service integrations.

## Security & Configuration Tips
Never commit `.env` contents. Respect the defaults in `app/config.py` for timeouts, concurrency, and SSL. Validate integrations with local `uvicorn` runs before enabling them elsewhere. For crawler training data, honor `CRAWLER_MAX_MEMORY_BYTES`, `CRAWLER_FLUSH_INTERVAL`, `CRAWLER_RETENTION_DAYS`, and `CRAWLER_TRAIN_DIR`, keeping only the last 30 days of JSONL shards and archiving older data.
