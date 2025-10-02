from __future__ import annotations

import asyncio
import logging
from typing import Optional, List
from .manager import CrawlerManager, CrawlJob
from ...config import get_settings

logger = logging.getLogger("ailinux.user_crawler")


class UserCrawler:
    """
    Dedicated fast crawler instance for user /crawl prompts.

    Separater Worker-Pool mit höherer Priorität und schnellerer Verarbeitung
    für User-initiierte Crawl-Jobs über das /crawl Kommando.
    """

    def __init__(self) -> None:
        settings = get_settings()

        # Dedicated user crawler manager
        self._manager = CrawlerManager()
        self._manager._instance_name = "user-crawler"

        self._settings = settings
        self._workers: List[asyncio.Task] = []
        self._worker_count = settings.user_crawler_workers
        self._max_concurrent = settings.user_crawler_max_concurrent
        self._stop_event = asyncio.Event()

        # Statistics
        self._stats = {
            "jobs_processed": 0,
            "jobs_active": 0,
            "jobs_queued": 0,
            "avg_processing_time": 0.0,
            "total_pages_crawled": 0,
        }

    async def start(self) -> None:
        """Start dedicated user crawler workers."""
        if self._workers:
            logger.warning("User crawler already running")
            return

        logger.info("Starting user crawler with %d workers", self._worker_count)
        self._stop_event.clear()

        # Start the underlying manager
        await self._manager.start()

        # Start dedicated workers for faster processing
        for i in range(self._worker_count):
            worker = asyncio.create_task(
                self._dedicated_worker(worker_id=i),
                name=f"user-crawler-worker-{i}"
            )
            self._workers.append(worker)

        logger.info("User crawler started with %d workers", self._worker_count)

    async def stop(self) -> None:
        """Stop user crawler workers."""
        if not self._workers:
            return

        logger.info("Stopping user crawler")
        self._stop_event.set()

        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

        await self._manager.stop()
        logger.info("User crawler stopped")

    async def _dedicated_worker(self, worker_id: int) -> None:
        """Dedicated worker for user crawl jobs (prioritizes high-priority queue)."""
        logger.info(f"User crawler worker {worker_id} started")

        while not self._stop_event.is_set():
            job_id = None
            try:
                # Always prioritize high-priority queue (user requests)
                job_id = await asyncio.wait_for(
                    self._manager._high_priority_job_queue.get(),
                    timeout=0.5
                )

                if job_id:
                    self._stats["jobs_active"] += 1
                    logger.info(f"Worker {worker_id} processing user job: {job_id}")

                    # Let the manager handle the actual crawling
                    # Worker just manages the queue
                    self._stats["jobs_processed"] += 1

            except asyncio.TimeoutError:
                # No jobs in queue, continue waiting
                continue
            except asyncio.CancelledError:
                logger.info(f"User crawler worker {worker_id} cancelled")
                break
            except Exception as exc:
                logger.error(f"Error in user crawler worker {worker_id}: {exc}", exc_info=True)
                await asyncio.sleep(1)
            finally:
                if job_id:
                    self._stats["jobs_active"] = max(0, self._stats["jobs_active"] - 1)

        logger.info(f"User crawler worker {worker_id} stopped")

    async def crawl_url(self, url: str, *, keywords: Optional[List[str]] = None, max_pages: int = 10) -> CrawlJob:
        """
        Fast crawl for user prompts - always high priority.

        Args:
            url: URL to crawl
            keywords: Optional keywords
            max_pages: Maximum pages to crawl

        Returns:
            CrawlJob instance
        """
        if not keywords:
            keywords = ["tech", "news", "ai", "linux", "software"]

        job = await self._manager.create_job(
            keywords=keywords,
            seeds=[url],
            max_depth=2,
            max_pages=max_pages,
            allow_external=False,
            user_context="User /crawl command",
            requested_by="user",
            priority="high",  # User jobs always high priority
        )

        self._stats["jobs_queued"] += 1
        return job

    async def get_status(self) -> dict:
        """Get user crawler status and statistics."""
        queue_size_high = self._manager._high_priority_job_queue.qsize()
        queue_size_low = self._manager._job_queue.qsize()

        return {
            "instance": "user-crawler",
            "running": not self._stop_event.is_set(),
            "workers": {
                "count": self._worker_count,
                "active": len([w for w in self._workers if not w.done()]),
            },
            "queues": {
                "high_priority": queue_size_high,
                "low_priority": queue_size_low,
                "total": queue_size_high + queue_size_low,
            },
            "stats": self._stats,
            "jobs": {
                "total": len(self._manager._jobs),
                "active": self._stats["jobs_active"],
                "processed": self._stats["jobs_processed"],
                "queued": self._stats["jobs_queued"],
            },
        }


# Global user crawler instance
user_crawler = UserCrawler()
