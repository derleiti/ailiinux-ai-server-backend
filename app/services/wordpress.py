from __future__ import annotations

import base64
from typing import Dict, List, Optional

import httpx

from ..config import get_settings
from ..utils.errors import api_error
from ..utils.http_client import robust_client

class WordPressService:
    def __init__(self) -> None:
        settings = get_settings()
        self.wordpress_url = settings.wordpress_url
        self.username = settings.wordpress_username
        self.password = settings.wordpress_password

    def _get_auth_headers(self) -> Dict[str, str]:
        if not self.username or not self.password:
            raise api_error("WordPress credentials are not configured", status_code=503, code="wordpress_unavailable")
        
        credentials = f"{self.username}:{self.password}"
        token = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def create_post(self, title: str, content: str, status: str = "publish", categories: Optional[List[int]] = None, featured_media: Optional[int] = None) -> Dict:
        if not self.wordpress_url:
            raise api_error("WordPress URL is not configured", status_code=503, code="wordpress_unavailable")

        url = self.wordpress_url.join("wp-json/wp/v2/posts")
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

        response = await robust_client.post(str(url), headers=headers, json=data)
        response.raise_for_status()
        return response.json()

    async def upload_media(self, filename: str, file_content: bytes, content_type: str) -> Dict:
        if not self.wordpress_url:
            raise api_error("WordPress URL is not configured", status_code=503, code="wordpress_unavailable")

        url = self.wordpress_url.join("wp-json/wp/v2/media")
        headers = self._get_auth_headers()
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        headers["Content-Type"] = content_type

        response = await robust_client.post(str(url), headers=headers, content=file_content)
        response.raise_for_status()
        return response.json()

    async def list_categories(self) -> List[Dict]:
        if not self.wordpress_url:
            raise api_error("WordPress URL is not configured", status_code=503, code="wordpress_unavailable")

        url = self.wordpress_url.join("wp-json/wp/v2/categories")
        
        response = await robust_client.get(str(url))
        response.raise_for_status()
        return response.json()

    async def create_category(self, name: str) -> Dict:
        if not self.wordpress_url:
            raise api_error("WordPress URL is not configured", status_code=503, code="wordpress_unavailable")

        url = self.wordpress_url.join("wp-json/wp/v2/categories")
        headers = self._get_auth_headers()

        data = {"name": name}

        response = await robust_client.post(str(url), headers=headers, json=data)
        response.raise_for_status()
        return response.json()

wordpress_service = WordPressService()
