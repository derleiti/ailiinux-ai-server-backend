## Crawler Integration Update

This update integrates the web crawler with the chat models, enabling new functionalities for data collection, search, and training.

### Chat Model Integration

Chat models can now leverage crawler results through a new tool and slash command:

*   **`crawler.search` Tool**: An internal API (`POST /v1/crawler/search`) is available for chat models to search crawled content. It accepts a `query`, `limit`, `min_score`, and `freshness_days`.
    *   **Input**: `{ query: string, limit?: number=20, min_score?: number=0.35, freshness_days?: number=7 }`
    *   **Output**: Top-K results with `{url, title, excerpt, score, ts}`.

*   **`/crawl` Slash Command**: Users can initiate crawl jobs directly from the chat interface.
    *   **Syntax**: `/crawl kw:<comma keywords> seeds:<space URLs> depth:<0-5> pages:<1-200> ext:<true|false>`
    *   **Example**: `/crawl kw:ai,linux seeds:https://www.example.com depth:1 pages:50 ext:false`
    *   Job status updates are streamed, and results are linked upon completion.

### Training Data Accumulation

Crawler results are now stored in a RAM-first buffer and persisted as JSONL shards for training data:

*   **RAM-first Buffer**: Recent crawl results are kept in memory for fast retrieval.
*   **Hourly Rotation**: A background job flushes RAM deltas to disk hourly into new JSONL shards.
    *   **File Naming**: `data/crawler_spool/train/crawl-train-${YYYYMMDD-HH}.jsonl`
    *   **Record Fields**: `job_id`, `url`, `title`, `excerpt/summary`, `normalized_text`, `matched_keywords`, `score`, `publish_date` (ISO8601), `created_at`, `source_domain`, `labels` (from feedback), `content_hash` (sha256), `tokens_est`.
*   **Shutdown Flush**: Any pending RAM entries are flushed to disk upon application shutdown.
*   **Index Maintenance**: A `train/index.json` file tracks all shards, their sizes, and record counts.

### Data Retention Policy

To manage disk space and data freshness:

*   **30-Day Retention**: JSONL shards older than 30 days are automatically gzipped and moved to `data/crawler_spool/archive/`.
*   **Daily Compaction**: A daily background task handles the gzipping and archiving process.

### Environment Variables (`.env`)

The following environment variables can be configured:

*   `CRAWLER_MAX_MEMORY_BYTES`: Maximum memory (in bytes) for the RAM buffer (e.g., `536870912` for 512MB).
*   `CRAWLER_FLUSH_INTERVAL`: Interval (in seconds) for hourly flushing of RAM deltas to JSONL shards (default: `3600`).
*   `CRAWLER_RETENTION_DAYS`: Number of days to retain uncompressed JSONL shards (default: `30`).
*   `CRAWLER_TRAIN_DIR`: Directory for storing training data shards (default: `data/crawler_spool/train`).

### Testing Checklist

To verify the new functionalities:

1.  **Start Backend**: Confirm hourly timer logs and on-demand flush via an internal trigger.
2.  **Run `/crawl`**: Execute `/crawl` from chat; verify job lifecycle, visible results, and the creation/update of JSONL shards and the index.
3.  **Call `/crawler/search`**: Use the frontend "Sources" button to call `/crawler/search`; verify RAM-first, then disk shard search, and reranking.
4.  **Restart Service**: Verify that pending RAM entries are flushed to disk upon service shutdown.