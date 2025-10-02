from __future__ import annotations

import base64
from typing import Dict, List, Optional

import httpx
from app.config import get_settings
from app.utils.errors import api_error

class WordPressService:
    def __init__(self) -> None:
        s = get_settings()
        self.wordpress_url = s.wordpress_url
        self.username = s.wordpress_user
        self.password = s.wordpress_password
        if not self.wordpress_url or not self.username or not self.password:
            raise api_error("WordPress credentials/url are not configured", status_code=503, code="wordpress_unavailable")

    async def create_post(self, title: str, content: str, status: str = "publish") -> dict:
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
