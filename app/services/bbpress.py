from __future__ import annotations

import base64
import logging
from typing import Dict, List, Optional

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
        settings = get_settings()
        self.wordpress_url = settings.wordpress_url
        self.username = settings.wordpress_username
        self.password = settings.wordpress_password

    def _get_auth_headers(self) -> Dict[str, str]:
        """Erstellt Basic Auth Headers."""
        if not self.username or not self.password:
            raise api_error(
                "WordPress credentials are not configured",
                status_code=503,
                code="wordpress_unavailable",
            )

        credentials = f"{self.username}:{self.password}"
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
        if not self.wordpress_url:
            raise api_error(
                "WordPress URL is not configured",
                status_code=503,
                code="wordpress_unavailable",
            )

        # bbPress REST API Endpoint
        # Hinweis: bbPress hat keine offizielle REST API
        # Wir nutzen die bbPress Plugin REST API (falls installiert)
        # oder erstellen Topics als Custom Post Type
        url = self.wordpress_url.join("wp-json/wp/v2/topic")
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=data)
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
        if not self.wordpress_url:
            raise api_error(
                "WordPress URL is not configured",
                status_code=503,
                code="wordpress_unavailable",
            )

        # bbPress Reply als Custom Post Type
        url = self.wordpress_url.join("wp-json/wp/v2/reply")
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        data = {
            "content": content,
            "status": "publish",
            "meta": {
                "_bbp_topic_id": topic_id,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=data)
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
        if not self.wordpress_url:
            raise api_error(
                "WordPress URL is not configured",
                status_code=503,
                code="wordpress_unavailable",
            )

        url = self.wordpress_url.join("wp-json/wp/v2/forum?per_page=100")
        headers = self._get_auth_headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=headers)
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
