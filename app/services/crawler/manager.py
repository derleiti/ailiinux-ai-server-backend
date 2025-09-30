from __future__ import annotations

import asyncio
import json
import random
import re
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

import hashlib
import gzip
import jsonlines
from rank_bm25 import BM25Okapi
from ...config import get_settings

logger = __import__("logging").getLogger("ailinux.crawler")

# Optional imports from existing services; imported lazily to avoid heavy dependencies
try:  # pragma: no cover - registry import is optional during unit tests
    from ..model_registry import registry
    from .. import chat as chat_service
except Exception:  # pragma: no cover
    registry = None
    chat_service = None


USER_AGENT = "AILinuxCrawler/1.0"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

SUMMARY_SYSTEM_PROMPT = (
    "You are Nova AI. Summarise the crawled article for publication on the AILinux network. "
    "Return three bullet points highlighting key takeaways and one short headline (<=120 chars)."
)

RELEVANT_META_KEYS = {
    "description",
    "og:description",
    "twitter:description",
}

ARTICLE_SELECTORS = [
    "article",
    "main article",
    "div[itemtype='http://schema.org/Article']",
    "div[itemtype='https://schema.org/Article']",
    "div.post-content",
    "div.entry-content",
]

PUBLISH_META_KEYS = [
    "article:published_time",
    "article:modified_time",
    "og:updated_time",
    "date",
    "dc.date",
    "dc.date.issued",
    "dc.date.created",
    "pubdate",
]


@dataclass
class CrawlFeedback:
    score: float
    comment: Optional[str]
    source: str
    confirmed: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "comment": self.comment,
            "source": self.source,
            "confirmed": self.confirmed,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CrawlResult:
    id: str
    job_id: str
    url: str
    depth: int
    parent_url: Optional[str]
    status: str
    title: str
    summary: Optional[str]
    headline: Optional[str]
    content: str
    excerpt: str
    meta_description: Optional[str]
    keywords_matched: List[str]
    score: float
    publish_date: Optional[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ratings: List[CrawlFeedback] = field(default_factory=list)
    rating_average: float = 0.0
    rating_count: int = 0
    confirmations: int = 0
    tags: List[str] = field(default_factory=list)
    spool_path: Optional[Path] = None
    size_bytes: int = 0
    posted_at: Optional[datetime] = None
    post_id: Optional[int] = None
    topic_id: Optional[int] = None
    normalized_text: Optional[str] = None
    content_hash: Optional[str] = None
    source_domain: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    tokens_est: Optional[int] = None

    def to_dict(self, include_content: bool = True) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "job_id": self.job_id,
            "url": self.url,
            "depth": self.depth,
            "parent_url": self.parent_url,
            "status": self.status,
            "title": self.title,
            "summary": self.summary,
            "headline": self.headline,
            "excerpt": self.excerpt,
            "meta_description": self.meta_description,
            "keywords_matched": self.keywords_matched,
            "score": self.score,
            "publish_date": self.publish_date,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "rating_average": self.rating_average,
            "rating_count": self.rating_count,
            "confirmations": self.confirmations,
            "tags": self.tags,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "post_id": self.post_id,
            "topic_id": self.topic_id,
            "normalized_text": self.normalized_text,
            "content_hash": self.content_hash,
            "source_domain": self.source_domain,
            "labels": self.labels,
            "tokens_est": self.tokens_est,
            "size_bytes": self.size_bytes,
            "ratings": [feedback.to_dict() for feedback in self.ratings],
        }
        if include_content:
            payload["content"] = self.content
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrawlResult":
        result = cls(
            id=data["id"],
            job_id=data["job_id"],
            url=data["url"],
            depth=data.get("depth", 0),
            parent_url=data.get("parent_url"),
            status=data.get("status", "pending"),
            title=data.get("title", ""),
            summary=data.get("summary"),
            headline=data.get("headline"),
            content=data.get("content", ""),
            excerpt=data.get("excerpt", ""),
            meta_description=data.get("meta_description"),
            keywords_matched=data.get("keywords_matched", []),
            score=data.get("score", 0.0),
            publish_date=data.get("publish_date"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc),
            tags=data.get("tags", []),
            normalized_text=data.get("normalized_text"),
            content_hash=data.get("content_hash"),
            source_domain=data.get("source_domain"),
            labels=data.get("labels", []),
            tokens_est=data.get("tokens_est"),
        )
        for rating in data.get("ratings", []):
            result.ratings.append(
                CrawlFeedback(
                    score=rating.get("score", 0.0),
                    comment=rating.get("comment"),
                    source=rating.get("source", "unknown"),
                    confirmed=rating.get("confirmed", False),
                    created_at=datetime.fromisoformat(rating["created_at"]) if rating.get("created_at") else datetime.now(timezone.utc),
                )
            )
        result.rating_count = data.get("rating_count", len(result.ratings))
        result.rating_average = data.get("rating_average", 0.0)
        result.confirmations = data.get("confirmations", 0)
        if data.get("posted_at"):
            result.posted_at = datetime.fromisoformat(data["posted_at"])
        result.post_id = data.get("post_id")
        result.topic_id = data.get("topic_id")
        result.size_bytes = data.get("size_bytes", 0)
        return result


@dataclass
class CrawlJob:
    id: str
    keywords: List[str]
    seeds: List[str]
    max_depth: int
    max_pages: int
    allowed_domains: Set[str]
    allow_external: bool
    relevance_threshold: float
    rate_limit: float
    user_context: Optional[str]
    requested_by: Optional[str]
    metadata: dict[str, Any]
    status: str = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    pages_crawled: int = 0
    results: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "keywords": self.keywords,
            "seeds": self.seeds,
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "allowed_domains": list(self.allowed_domains),
            "allow_external": self.allow_external,
            "relevance_threshold": self.relevance_threshold,
            "rate_limit": self.rate_limit,
            "user_context": self.user_context,
            "requested_by": self.requested_by,
            "metadata": self.metadata,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "pages_crawled": self.pages_crawled,
            "results": self.results,
            "error": self.error,
        }


class CrawlerStore:
    """In-memory cache with disk spill-over for crawl results."""

    def __init__(self, max_memory_bytes: int, spool_dir: Path):
        self.max_memory_bytes = max_memory_bytes
        self.spool_dir = spool_dir
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self._records: OrderedDict[str, CrawlResult] = OrderedDict()
        self._sizes: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._memory_usage = 0

    async def add(self, result: CrawlResult) -> None:
        data = json.dumps(result.to_dict(include_content=True), ensure_ascii=False)
        size = len(data.encode("utf-8"))
        result.size_bytes = size
        async with self._lock:
            # Deduplicate by content_hash
            if result.content_hash:
                for existing_result in self._records.values():
                    if existing_result.content_hash == result.content_hash:
                        # Update existing result if new one is better (e.g., higher score, more recent)
                        if result.score > existing_result.score or result.updated_at > existing_result.updated_at:
                            self._records[existing_result.id] = result
                            self._sizes[result.id] = size
                            self._memory_usage += (size - self._sizes.get(existing_result.id, 0))
                            logger.debug("Updated duplicate crawl result %s with new data", result.id)
                        return

            await self._ensure_capacity(size)
            self._records[result.id] = result
            self._sizes[result.id] = size
            self._memory_usage += size

    async def _ensure_capacity(self, required: int) -> None:
        if self.max_memory_bytes <= 0:
            return
        while self._memory_usage + required > self.max_memory_bytes and self._records:
            record_id, record = self._records.popitem(last=False)
            size = self._sizes.pop(record_id, 0)
            self._memory_usage -= size
            # Removed _spill_to_disk call, now handled by CrawlerManager's flush methods

    async def get(self, result_id: str) -> Optional[CrawlResult]:
        async with self._lock:
            record = self._records.get(result_id)
            if record:
                return record
        # Disk lookup for individual files is removed, now handled by search across shards
        return None

    async def list(self, predicate) -> List[CrawlResult]:
        async with self._lock:
            records = list(self._records.values())
        matched = [record for record in records if predicate(record)]
        # Disk lookup for individual files is removed, now handled by search across shards
        return matched

    async def update(self, result: CrawlResult) -> None:
        async with self._lock:
            if result.id in self._records:
                self._records[result.id] = result
                data = json.dumps(result.to_dict(include_content=True), ensure_ascii=False)
                size = len(data.encode("utf-8"))
                delta = size - self._sizes.get(result.id, 0)
                self._memory_usage += delta
                self._sizes[result.id] = size
            else:
                # If not in RAM, it must be on disk, but we don't update individual files anymore
                pass


class CrawlerManager:
    def __init__(self) -> None:
        settings = get_settings()
        spool_dir = Path(getattr(settings, "crawler_spool_dir", "data/crawler_spool"))
        self._store = CrawlerStore(
            max_memory_bytes=int(getattr(settings, "crawler_max_memory_bytes", 48 * 1024**3)),
            spool_dir=spool_dir,
        )
        self._jobs: Dict[str, CrawlJob] = {}
        self._job_queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._robots_cache: Dict[str, Optional[RobotFileParser]] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._random = random.Random()

        # Training data management
        self._train_dir = Path(getattr(settings, "crawler_train_dir", "data/crawler_spool/train"))
        self._train_dir.mkdir(parents=True, exist_ok=True)
        self._train_index_path = self._train_dir / "index.json"
        self._current_shard_path: Optional[Path] = None
        self._last_flush_time: datetime = datetime.now(timezone.utc)
        self._train_buffer: List[CrawlResult] = []
        self._flush_interval = int(getattr(settings, "crawler_flush_interval", 3600))
        self._retention_days = int(getattr(settings, "crawler_retention_days", 30))
        self._load_train_index()

    def _load_train_index(self) -> None:
        if self._train_index_path.exists():
            try:
                with open(self._train_index_path, "r", encoding="utf-8") as f:
                    self._train_index = json.load(f)
            except json.JSONDecodeError:
                logger.warning("Could not decode train index file, starting fresh.")
                self._train_index = {"shards": []}
        else:
            self._train_index = {"shards": []}

    def _save_train_index(self) -> None:
        with open(self._train_index_path, "w", encoding="utf-8") as f:
            json.dump(self._train_index, f, indent=2)

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._client = httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0)
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._run_worker(), name="crawler-worker")
        logger.info("Crawler manager started")

    async def flush_hourly(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(self._flush_interval)
            await self.flush_to_jsonl()

    async def flush_to_jsonl(self) -> None:
        if not self._train_buffer:
            return

        current_hour = datetime.now(timezone.utc).strftime("%Y%m%d-%H")
        shard_name = f"crawl-train-{current_hour}.jsonl"
        shard_path = self._train_dir / shard_name

        records_flushed = 0
        size_flushed = 0

        async with self._lock:
            with jsonlines.open(shard_path, mode="a") as writer:
                for result in self._train_buffer:
                    data = result.to_dict(include_content=False) # Don't include full content in JSONL
                    writer.write(data)
                    records_flushed += 1
                    size_flushed += len(json.dumps(data).encode("utf-8"))
            self._train_buffer.clear()

            # Update train index
            found = False
            for shard_entry in self._train_index["shards"]:
                if shard_entry["name"] == shard_name:
                    shard_entry["records"] += records_flushed
                    shard_entry["size_bytes"] += size_flushed
                    found = True
                    break
            if not found:
                self._train_index["shards"].append({
                    "name": shard_name,
                    "records": records_flushed,
                    "size_bytes": size_flushed,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            self._save_train_index()

        logger.info("Flushed %d records (%.2f KB) to %s", records_flushed, size_flushed / 1024, shard_name)

    async def shutdown_flush(self) -> None:
        logger.info("Performing final flush of RAM buffer to JSONL shards.")
        await self.flush_to_jsonl()

    async def compact_spool(self) -> None:
        while not self._stop_event.is_set():
            # Run daily
            await asyncio.sleep(86400)
            logger.info("Starting spool compaction and archiving.")
            archive_dir = self._train_dir / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self._retention_days)

            async with self._lock:
                shards_to_update = []
                for shard_info in self._train_index["shards"]:
                    shard_path = self._train_dir / shard_info["name"]
                    if not shard_path.exists():
                        continue

                    # Parse date from shard name (e.g., crawl-train-YYYYMMDD-HH.jsonl)
                    try:
                        date_str = shard_info["name"].replace("crawl-train-", "").replace(".jsonl", "")
                        shard_date = datetime.strptime(date_str, "%Y%m%d-%H").replace(tzinfo=timezone.utc)
                    except ValueError:
                        logger.warning("Could not parse date from shard name: %s", shard_info["name"])
                        shards_to_update.append(shard_info)
                        continue

                    if shard_date < cutoff_date:
                        gzipped_shard_name = shard_path.name + ".gz"
                        gzipped_shard_path = archive_dir / gzipped_shard_name
                        try:
                            with open(shard_path, "rb") as f_in:
                                with gzip.open(gzipped_shard_path, "wb") as f_out:
                                    f_out.writelines(f_in)
                            shard_path.unlink() # Delete original
                            logger.info("Gzipped and archived shard: %s", shard_path.name)
                        except Exception as exc:
                            logger.error("Error gzipping shard %s: %s", shard_path.name, exc)
                            shards_to_update.append(shard_info) # Keep in index if error
                    else:
                        shards_to_update.append(shard_info)
                self._train_index["shards"] = shards_to_update
                self._save_train_index()
            logger.info("Spool compaction and archiving completed.")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._worker_task:
            await self._worker_task
            self._worker_task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("Crawler manager stopped")

    async def create_job(
        self,
        *,
        keywords: List[str],
        seeds: List[str],
        max_depth: int = 2,
        max_pages: int = 60,
        rate_limit: float = 1.0,
        relevance_threshold: float = 0.35,
        allow_external: bool = False,
        user_context: Optional[str] = None,
        requested_by: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CrawlJob:
        if not seeds:
            raise ValueError("At least one seed URL is required")
        normalized_keywords = [kw.strip() for kw in keywords if kw.strip()]
        normalized_seeds = [seed.strip() for seed in seeds if seed.strip()]
        allowed_domains = {urlparse(seed).netloc for seed in normalized_seeds}
        job = CrawlJob(
            id=str(uuid.uuid4()),
            keywords=normalized_keywords,
            seeds=normalized_seeds,
            max_depth=max(0, min(max_depth, 5)),
            max_pages=max(1, min(max_pages, 500)),
            allowed_domains=allowed_domains,
            allow_external=allow_external,
            relevance_threshold=max(0.1, min(relevance_threshold, 0.95)),
            rate_limit=max(0.1, min(rate_limit, 10.0)),
            user_context=user_context,
            requested_by=requested_by,
            metadata=metadata or {},
        )
        async with self._lock:
            self._jobs[job.id] = job
        await self._job_queue.put(job.id)
        logger.info("Crawler job %s queued with %d seeds", job.id, len(job.seeds))
        return job

    async def list_jobs(self) -> List[CrawlJob]:
        async with self._lock:
            return list(self._jobs.values())

    async def get_job(self, job_id: str) -> Optional[CrawlJob]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def get_result(self, result_id: str) -> Optional[CrawlResult]:
        return await self._store.get(result_id)

    async def add_feedback(
        self,
        result_id: str,
        *,
        score: float,
        comment: Optional[str],
        confirmed: bool,
        source: str,
    ) -> Optional[CrawlResult]:
        result = await self._store.get(result_id)
        if not result:
            return None
        feedback = CrawlFeedback(score=max(0.0, min(score, 5.0)), comment=comment, source=source, confirmed=confirmed)
        result.ratings.append(feedback)
        result.rating_count = len(result.ratings)
        result.rating_average = sum(item.score for item in result.ratings) / max(1, result.rating_count)
        if confirmed:
            result.confirmations += 1
        result.updated_at = datetime.now(timezone.utc)
        await self._store.update(result)
        return result

    async def mark_posted(
        self,
        result_id: str,
        *,
        post_id: Optional[int],
        topic_id: Optional[int],
    ) -> Optional[CrawlResult]:
        result = await self._store.get(result_id)
        if not result:
            return None
        result.status = "published"
        result.posted_at = datetime.now(timezone.utc)
        result.post_id = post_id
        result.topic_id = topic_id
        result.updated_at = datetime.now(timezone.utc)
        await self._store.update(result)
        return result

    async def ready_for_publication(self, *, limit: int = 10, min_age_minutes: int = 60) -> List[CrawlResult]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=min_age_minutes)

        def predicate(result: CrawlResult) -> bool:
            if result.status == "published":
                return False
            if result.rating_count < 2:
                return False
            if result.rating_average < 4.0:
                return False
            if result.confirmations < 1:
                return False
            if result.created_at > cutoff:
                return False
            return True

        results = await self._store.list(predicate)
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def search(
        self,
        query: str,
        limit: int = 20,
        min_score: float = 0.35,
        freshness_days: int = 7,
    ) -> List[Dict[str, Any]]:
        all_results: List[Dict[str, Any]] = []
        query_tokens = query.lower().split()

        # 1. Search RAM first
        async with self._store._lock:
            for result in self._store._records.values():
                if result.normalized_text:
                    all_results.append(asdict(result))

        # 2. Search disk shards
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=freshness_days)
        async with self._lock:
            for shard_info in self._train_index["shards"]:
                shard_path = self._train_dir / shard_info["name"]
                if not shard_path.exists():
                    continue

                try:
                    date_str = shard_info["name"].replace("crawl-train-", "").replace(".jsonl", "")
                    shard_date = datetime.strptime(date_str, "%Y%m%d-%H").replace(tzinfo=timezone.utc)
                    if shard_date < cutoff_date:
                        continue
                except ValueError:
                    continue

                with jsonlines.open(shard_path, mode="r") as reader:
                    for obj in reader:
                        # Reconstruct CrawlResult from dict for consistent processing
                        result = CrawlResult.from_dict(obj)
                        if result.normalized_text:
                            all_results.append(obj)

        # 3. Rerank results (BM25)
        if not all_results:
            return []

        corpus = [res["normalized_text"] for res in all_results if res.get("normalized_text")]
        if not corpus:
            return []

        tokenized_corpus = [doc.lower().split() for doc in corpus]
        bm25 = BM25Okapi(tokenized_corpus)
        doc_scores = bm25.get_scores(query_tokens)

        scored_results = []
        for i, res in enumerate(all_results):
            res_score = doc_scores[i] # BM25 score
            # Combine with original score, if any, or just use BM25
            final_score = (res.get("score", 0.0) + res_score) / 2.0 if res.get("score") else res_score
            if final_score >= min_score:
                scored_results.append({
                    "url": res["url"],
                    "title": res["title"],
                    "excerpt": res["excerpt"],
                    "score": final_score,
                    "ts": res["created_at"],
                    "source_domain": res["source_domain"],
                })

        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:limit]

    async def _run_worker(self) -> None:
        assert self._client is not None
        while not self._stop_event.is_set():
            try:
                job_id = await asyncio.wait_for(self._job_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            job = await self.get_job(job_id)
            if not job:
                continue
            await self._process_job(job)
            self._job_queue.task_done()

    async def _process_job(self, job: CrawlJob) -> None:
        assert self._client is not None
        job.status = "running"
        job.updated_at = datetime.now(timezone.utc)
        await self._persist_job(job)
        queue: deque[Tuple[str, int, Optional[str]]] = deque()
        for seed in job.seeds:
            queue.append((seed, 0, None))
        visited: Set[str] = set()

        while queue and job.pages_crawled < job.max_pages:
            url, depth, parent = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            if depth > job.max_depth:
                continue
            if not await self._can_fetch(url):
                continue
            await asyncio.sleep(job.rate_limit + self._random.uniform(0.0, job.rate_limit))
            try:
                response = await self._client.get(url)
            except Exception as exc:  # pragma: no cover - network issues
                logger.warning("Crawler fetch failed for %s: %s", url, exc)
                continue
            if response.status_code >= 400:
                continue
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            text_content = self._extract_text(soup)
            score, matched_keywords = self._score_content(text_content, job.keywords)
            if score >= job.relevance_threshold:
                result = await self._build_result(
                    job,
                    url=url,
                    parent_url=parent,
                    depth=depth,
                    soup=soup,
                    text_content=text_content,
                    score=score,
                    matched_keywords=matched_keywords,
                )
                await self._store.add(result)
                job.results.append(result.id)
                self._train_buffer.append(result) # Add to training buffer
            job.pages_crawled += 1
            job.updated_at = datetime.now(timezone.utc)
            await self._persist_job(job)

            if depth < job.max_depth:
                links = self._extract_links(url, soup, job)
                for link in links:
                    if link not in visited:
                        queue.append((link, depth + 1, url))

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        await self._persist_job(job)
        logger.info("Crawler job %s completed with %d pages crawled", job.id, len(job.results))

    async def _build_result(
        self,
        job: CrawlJob,
        *,
        url: str,
        parent_url: Optional[str],
        depth: int,
        soup: BeautifulSoup,
        text_content: str,
        score: float,
        matched_keywords: List[str],
    ) -> CrawlResult:
        title = self._extract_title(soup)
        meta_description = self._extract_meta_description(soup)
        publish_date = self._extract_publish_date(soup)
        excerpt = self._build_excerpt(text_content)
        headline, summary = await self._generate_summary(text_content, meta_description)
        normalized_text = self._normalize_text(soup)
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        source_domain = urlparse(url).netloc
        tokens_est = len(normalized_text.split())

        result = CrawlResult(
            id=str(uuid.uuid4()),
            job_id=job.id,
            url=url,
            depth=depth,
            parent_url=parent_url,
            status="pending",
            title=title,
            summary=summary,
            headline=headline,
            content=text_content,
            excerpt=excerpt,
            meta_description=meta_description,
            keywords_matched=matched_keywords,
            score=score,
            publish_date=publish_date,
            tags=self._guess_tags(matched_keywords, job.metadata.get("tags")),
            normalized_text=normalized_text,
            content_hash=content_hash,
            source_domain=source_domain,
            tokens_est=tokens_est,
        )
        return result

    async def _persist_job(self, job: CrawlJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots_cache.get(base)
        if parser is None and self._client:
            robots_url = urljoin(base, "/robots.txt")
            parser = RobotFileParser()
            try:
                response = await self._client.get(robots_url, timeout=10.0)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    parser = None
            except Exception:  # pragma: no cover
                parser = None
            self._robots_cache[base] = parser
        if parser:
            return parser.can_fetch(USER_AGENT, url)
        return True

    @staticmethod
    def _extract_text(soup: BeautifulSoup) -> str:
        for selector in ARTICLE_SELECTORS:
            node = soup.select_one(selector)
            if node:
                return node.get_text(separator=" ", strip=True)
        paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
        return " ".join(paragraphs)

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.get_text(strip=True)
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return "Untitled Document"

    @staticmethod
    def _extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
        for key in RELEVANT_META_KEYS:
            node = soup.find("meta", attrs={"name": key}) or soup.find("meta", property=key)
            if node and node.get("content"):
                return node["content"].strip()
        return None

    @staticmethod
    def _extract_publish_date(soup: BeautifulSoup) -> Optional[str]:
        for key in PUBLISH_META_KEYS:
            node = soup.find("meta", attrs={"name": key}) or soup.find("meta", property=key)
            if node and node.get("content"):
                try:
                    dt = dateparser.parse(node["content"])
                    if dt:
                        return dt.astimezone(timezone.utc).isoformat()
                except (ValueError, TypeError):
                    continue
        time_node = soup.find("time")
        if time_node and time_node.get("datetime"):
            try:
                dt = dateparser.parse(time_node["datetime"])
                if dt:
                    return dt.astimezone(timezone.utc).isoformat()
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def _build_excerpt(text_content: str, *, max_length: int = 420) -> str:
        clean = re.sub(r"\s+", " ", text_content).strip()
        if len(clean) <= max_length:
            return clean
        return clean[: max_length - 3].rstrip() + "..."

    def _guess_tags(self, matched_keywords: Iterable[str], additional: Optional[Iterable[str]]) -> List[str]:
        tags = set(keyword.lower() for keyword in matched_keywords)
        if additional:
            tags.update(str(tag).lower() for tag in additional)
        return sorted(tags)

    def _extract_links(self, base_url: str, soup: BeautifulSoup, job: CrawlJob) -> List[str]:
        links: List[str] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href:
                continue
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if not job.allow_external and parsed.netloc not in job.allowed_domains:
                continue
            links.append(absolute)
        return links

    def _score_content(self, text: str, keywords: List[str]) -> Tuple[float, List[str]]:
        if not keywords:
            return 0.0, []
        text_lower = text.lower()
        matched = [keyword for keyword in keywords if keyword.lower() in text_lower]
        score = len(matched) / len(keywords)
        return score, matched

    async def _generate_summary(self, text: str, meta_description: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        settings = get_settings()
        model_name = getattr(settings, "crawler_summary_model", None)
        if not text:
            return None, meta_description
        if model_name and registry and chat_service:
            try:
                model = await registry.get_model(model_name)
            except Exception as exc:  # pragma: no cover
                logger.warning("Crawler summary model lookup failed: %s", exc)
                model = None
            if model and "chat" in model.capabilities:
                try:
                    messages = [
                        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": text[:6000]},
                    ]
                    chunks: List[str] = []
                    async for chunk in chat_service.stream_chat(
                        model,
                        model_name,
                        messages,
                        stream=True,
                        temperature=0.2,
                    ):
                        chunks.append(chunk)
                    summary_text = "".join(chunks).strip()
                    if summary_text:
                        headline, bullet_summary = self._split_summary(summary_text)
                        return headline, bullet_summary
                except Exception as exc:  # pragma: no cover
                    logger.warning("Crawler summary generation failed: %s", exc)
        # Fallback summary
        fallback = meta_description or self._build_excerpt(text, max_length=360)
        headline = None
        return headline, fallback

    @staticmethod
    def _split_summary(summary_text: str) -> Tuple[Optional[str], Optional[str]]:
        lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
        if not lines:
            return None, None
        headline = lines[0][:120]
        body = "\n".join(lines[1:]) if len(lines) > 1 else None
        return headline, body

    @staticmethod
    def _normalize_text(soup: BeautifulSoup) -> str:
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()

        # Remove navigation and footer elements (common patterns)
        for unwanted_tag in soup.find_all(["nav", "footer", "aside"]):
            unwanted_tag.extract()

        # Get text, preserving paragraph breaks and headings
        text_parts = []
        for element in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]):
            text_parts.append(element.get_text(separator=" ", strip=True))

        # Join parts and collapse multiple whitespaces
        full_text = "\n".join(text_parts)
        return re.sub(r"\s+", " ", full_text).strip()


crawler_manager = CrawlerManager()