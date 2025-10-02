from __future__ import annotations

import base64
from typing import Dict, List, Optional

import httpx
from app.config import get_settings
from app.utils.errors import api_error

class WordPressService:
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
            raise api_error("WordPress credentials/url are not configured", status_code=503, code="wordpress_unavailable")

        self._wordpress_url = settings.wordpress_url
        self._username = settings.wordpress_user
        self._password = settings.wordpress_password
        self._client = httpx.AsyncClient(base_url=str(self._wordpress_url), timeout=settings.request_timeout)

    def _get_auth_headers(self) -> Dict[str, str]:
        if not self._username or not self._password:
            raise RuntimeError("WordPress client not initialized. Call _ensure_client first.")
        credentials = f"{self._username}:{self._password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode("ascii")
        return {"Authorization": f"Basic {encoded_credentials}"}

    async def create_post(self, title: str, content: str, status: str = "publish", categories: Optional[List[int]] = None, featured_media: Optional[int] = None) -> dict:
        self._ensure_client()
        if not self._wordpress_url or not self._client:
            raise RuntimeError("WordPress client not initialized.")

        url = self._wordpress_url.join("wp-json/wp/v2/posts")
        headers = self._get_auth_headers()
        
        data = {
            "title": title,
            "content": content,
            "status": status,
        }
        if categories:
            data["categories"] = categories
        if featured_media:
            data["featured_media"] = featured_media

        response = await self._client.post(str(url), headers=headers, json=data)
        response.raise_for_status()
        return response.json()

    async def upload_media(self, filename: str, file_content: bytes, content_type: str) -> Dict:
        self._ensure_client()
        if not self._wordpress_url or not self._client:
            raise RuntimeError("WordPress client not initialized.")

        url = self._wordpress_url.join("wp-json/wp/v2/media")
        headers = self._get_auth_headers()
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        headers["Content-Type"] = content_type

        response = await self._client.post(str(url), headers=headers, content=file_content)
        response.raise_for_status()
        return response.json()

    async def list_categories(self) -> List[Dict]:
        self._ensure_client()
        if not self._wordpress_url or not self._client:
            raise RuntimeError("WordPress client not initialized.")

        url = self._wordpress_url.join("wp-json/wp/v2/categories")
        
        response = await self._client.get(str(url))
        response.raise_for_status()
        return response.json()

    async def create_category(self, name: str) -> Dict:
        self._ensure_client()
        if not self._wordpress_url or not self._client:
            raise RuntimeError("WordPress client not initialized.")

        url = self._wordpress_url.join("wp-json/wp/v2/categories")
        headers = self._get_auth_headers()

        data = {"name": name}

        response = await self._client.post(str(url), headers=headers, json=data)
        response.raise_for_status()
        return response.json()

wordpress_service = WordPressService()
