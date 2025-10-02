from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .crawler.manager import crawler_manager
from .wordpress import wordpress_service
from .bbpress import bbpress_service
from . import chat as chat_service
from ..config import get_settings
from .model_registry import registry

logger = logging.getLogger("ailinux.auto_publisher")


class AutoPublisher:
    """
    Automatisches WordPress Publishing System.

    Prüft stündlich Crawler-Ergebnisse und postet interessante Findings
    als WordPress Posts und bbPress Forum Topics.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._interval = 3600  # 1 Stunde
        self._min_score = 0.6  # Minimum Relevanz-Score
        self._max_posts_per_hour = 3  # Max Posts pro Stunde

    async def start(self) -> None:
        """Startet den Auto-Publisher Background-Task."""
        if self._task:
            logger.warning("Auto-publisher already running")
            return

        logger.info("Starting auto-publisher (interval: %d seconds)", self._interval)
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stoppt den Auto-Publisher."""
        if not self._task:
            return

        logger.info("Stopping auto-publisher")
        self._stop_event.set()
        await self._task
        self._task = None
        logger.info("Auto-publisher stopped")

    async def _run(self) -> None:
        """Haupt-Loop: Prüft stündlich auf neue Crawler-Ergebnisse."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._interval)
                await self._process_hourly()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in auto-publisher loop: %s", exc, exc_info=True)

    async def _process_hourly(self) -> None:
        """Verarbeitet Crawler-Ergebnisse der letzten Stunde."""
        logger.info("Auto-publisher: Processing hourly crawl results...")

        try:
            # Hole die besten ungeposteten Ergebnisse der letzten Stunde
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

            # Suche nach hochqualitativen Ergebnissen
            results = await crawler_manager.search(
                query="",  # Leer = alle
                limit=20,
                min_score=self._min_score,
                freshness_days=1,
            )

            # Filtere bereits gepostete
            unposted = [r for r in results if not r.get("posted_at")]

            if not unposted:
                logger.info("No new high-quality results to publish")
                return

            # Sortiere nach Score
            unposted.sort(key=lambda x: x.get("score", 0), reverse=True)

            # Poste die Top N Ergebnisse
            posted_count = 0
            for result_data in unposted[:self._max_posts_per_hour]:
                try:
                    result_id = result_data.get("id")
                    if not result_id:
                        continue

                    result = await crawler_manager.get_result(result_id)
                    if not result or result.posted_at:
                        continue

                    # Erstelle WordPress Post
                    await self._create_wordpress_post(result)

                    # Erstelle bbPress Forum Topic
                    await self._create_forum_topic(result)

                    posted_count += 1
                    logger.info(
                        "Published result: %s (score: %.2f)",
                        result.title,
                        result.score,
                    )

                except Exception as exc:
                    logger.error(
                        "Error publishing result %s: %s",
                        result_data.get("id"),
                        exc,
                        exc_info=True,
                    )

            logger.info("Auto-publisher: Posted %d new articles", posted_count)

        except Exception as exc:
            logger.error("Error in hourly processing: %s", exc, exc_info=True)

    async def _create_wordpress_post(self, result) -> None:
        """Erstellt WordPress Post aus Crawler-Ergebnis."""
        # Generiere Artikel mit GPT-OSS
        model_id = getattr(self._settings, "crawler_summary_model", None) or "gpt-oss:cloud/120b"
        model = await registry.get_model(model_id)

        if not model:
            logger.warning("Model %s not found, skipping post generation", model_id)
            return

        # Prompt für Artikel-Generierung
        prompt = f"""Schreibe einen professionellen News-Artikel auf Deutsch basierend auf folgenden Informationen:

Titel: {result.title}
URL: {result.url}
Zusammenfassung: {result.summary}

Inhalt:
{result.content[:2000]}

Schreibe einen gut strukturierten Artikel mit:
- Einleitung (2-3 Sätze)
- Hauptteil (3-4 Absätze)
- Fazit (1-2 Sätze)
- Quellenangabe am Ende

Nutze professionellen Journalismus-Stil, sei objektiv und informativ."""

        messages = [
            {"role": "system", "content": "Du bist ein professioneller Tech-Journalist für AILinux."},
            {"role": "user", "content": prompt},
        ]

        # Generiere Artikel
        chunks = []
        try:
            async for chunk in chat_service.stream_chat(
                model,
                model_id,
                messages,
                stream=True,
                temperature=0.7,
            ):
                chunks.append(chunk)
        except Exception as exc:
            logger.error("Error generating article: %s", exc)
            return

        article_content = "".join(chunks)

        # Füge Quelle hinzu
        article_content += f"\n\n<hr>\n<p><strong>Quelle:</strong> <a href=\"{result.url}\" target=\"_blank\">{result.url}</a></p>"

        # Poste zu WordPress
        try:
            wp_result = await wordpress_service.create_post(
                title=result.title,
                content=article_content,
                status="publish",
                categories=[self._settings.wordpress_category_id] if self._settings.wordpress_category_id > 0 else None,
            )

            # Markiere als gepostet
            result.posted_at = datetime.now(timezone.utc)
            result.post_id = wp_result.get("id")
            await crawler_manager._store.update(result)

            logger.info("Created WordPress post: %s (ID: %s)", result.title, result.post_id)

        except Exception as exc:
            logger.error("Error creating WordPress post: %s", exc, exc_info=True)

    async def _create_forum_topic(self, result) -> None:
        """Erstellt bbPress Forum Topic aus Crawler-Ergebnis."""
        # Standard Forum ID (sollte in .env konfigurierbar sein)
        # TODO: Add BBPRESS_FORUM_ID to config
        forum_id = self._settings.bbpress_forum_id

        try:
            # Erstelle Forum-freundliche Zusammenfassung
            summary = result.summary or result.excerpt or "Interessanter Artikel entdeckt!"

            # Inhalt mit Link zum Original
            content = f"""<p>{summary}</p>

<p><strong>Original-Artikel:</strong> <a href="{result.url}" target="_blank">{result.title}</a></p>

<p><em>Dieser Topic wurde automatisch vom AILinux Crawler erstellt.</em></p>"""

            # Erstelle Topic
            topic = await bbpress_service.create_topic(
                forum_id=forum_id,
                title=result.title,
                content=content,
                tags=result.labels if result.labels else None,
            )

            logger.info(
                "Created bbPress topic: %s (ID: %s)",
                result.title,
                topic.get("id"),
            )

            # Optional: Speichere Topic ID am Result
            result.topic_id = topic.get("id")
            await crawler_manager._store.update(result)

        except Exception as exc:
            logger.error(
                "Error creating forum topic for %s: %s",
                result.title,
                exc,
                exc_info=True,
            )


# Globale Instanz
auto_publisher = AutoPublisher()
