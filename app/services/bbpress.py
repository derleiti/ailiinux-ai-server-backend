from __future__ import annotations

import base64
import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin

import httpx

from ..config import get_settings
from ..utils.errors import api_error

logger = logging.getLogger("ailinux.bbpress")


class BBPressService:
    """
    bbPress Forum Integration via WordPress REST API.

    Ermöglicht das Erstellen von Forum Topics und Replies
    direkt aus dem Backend.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._wordpress_url: Optional[httpx.URL] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None

    def _ensure_client(self) -> None:
        if self._client:
            return

        settings = get_settings()
        if not settings.wordpress_url or not settings.wordpress_user or not settings.wordpress_password:
            raise api_error("BBPress (WordPress) credentials/url are not configured", status_code=503, code="bbpress_unavailable")

        self._wordpress_url = settings.wordpress_url
        self._username = settings.wordpress_user
        self._password = settings.wordpress_password
        self._client = httpx.AsyncClient(base_url=str(self._wordpress_url), timeout=settings.request_timeout)

    def _get_auth_headers(self) -> Dict[str, str]:
        """Erstellt Basic Auth Headers."""
        if not self._username or not self._password:
            raise RuntimeError("BBPress client not initialized. Call _ensure_client first.")

        credentials = f"{self._username}:{self._password}"
        token = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def create_topic(
        self,
        forum_id: int,
        title: str,
        content: str,
        *,
        tags: Optional[List[str]] = None,
    ) -> Dict:
        """
        Erstellt ein neues bbPress Forum Topic.

        Args:
            forum_id: ID des Forums
            title: Topic-Titel
            content: Topic-Inhalt (HTML erlaubt)
            tags: Optional Topic-Tags

        Returns:
            dict: Erstelltes Topic mit ID
        """
        self._ensure_client()
        if not self._wordpress_url or not self._client:
            raise RuntimeError("BBPress client not initialized.")

        # bbPress REST API Endpoint
        # Hinweis: bbPress hat keine offizielle REST API
        # Wir nutzen die bbPress Plugin REST API (falls installiert)
        # oder erstellen Topics als Custom Post Type
        base = str(self._wordpress_url).rstrip("/") + "/"
        url = urljoin(base, "wp-json/wp/v2/topic")
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        data = {
            "title": title,
            "content": content,
            "status": "publish",
            "meta": {
                "_bbp_forum_id": forum_id,
            },
        }

        # Tags als Topic Tags (wenn bbPress Plugin Tags unterstützt)
        if tags:
            data["topic-tag"] = tags

        try:
            response = await self._client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            logger.info("Created bbPress topic: %s (ID: %s)", title, result.get("id"))
            return result

        except httpx.HTTPStatusError as exc:
            logger.error(
                "bbPress topic creation failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise api_error(
                f"Failed to create bbPress topic: {exc.response.status_code}",
                status_code=exc.response.status_code,
                code="bbpress_create_failed",
            )
        except Exception as exc:
            logger.error("Error creating bbPress topic: %s", exc, exc_info=True)
            raise

    async def create_reply(
        self,
        topic_id: int,
        content: str,
    ) -> Dict:
        """
        Erstellt eine Reply auf ein bestehendes Topic.

        Args:
            topic_id: ID des Topics
            content: Reply-Inhalt (HTML erlaubt)

        Returns:
            dict: Erstellte Reply mit ID
        """
        self._ensure_client()
        if not self._wordpress_url or not self._client:
            raise RuntimeError("BBPress client not initialized.")

        # bbPress Reply als Custom Post Type
        base = str(self._wordpress_url).rstrip("/") + "/"
        url = urljoin(base, "wp-json/wp/v2/reply")
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        data = {
            "content": content,
            "status": "publish",
            "meta": {
                "_bbp_topic_id": topic_id,
            },
        }

        try:
            response = await self._client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            logger.info("Created bbPress reply on topic %d (ID: %s)", topic_id, result.get("id"))
            return result

        except httpx.HTTPStatusError as exc:
            logger.error(
                "bbPress reply creation failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise api_error(
                f"Failed to create bbPress reply: {exc.response.status_code}",
                status_code=exc.response.status_code,
                code="bbpress_reply_failed",
            )
        except Exception as exc:
            logger.error("Error creating bbPress reply: %s", exc, exc_info=True)
            raise

    async def get_forums(self) -> List[Dict]:
        """
        Holt Liste aller verfügbaren Foren.

        Returns:
            list: Liste von Foren mit ID und Name
        """
        self._ensure_client()
        if not self._wordpress_url or not self._client:
            raise RuntimeError("BBPress client not initialized.")

        base = str(self._wordpress_url).rstrip("/") + "/"
        url = urljoin(base, "wp-json/wp/v2/forum?per_page=100")
        headers = self._get_auth_headers()

        try:
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "bbPress forums list failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text,
            )
            # Fallback: Return empty list
            return []
        except Exception as exc:
            logger.error("Error getting bbPress forums: %s", exc, exc_info=True)
            return []


# Globale Instanz
bbpress_service = BBPressService()
