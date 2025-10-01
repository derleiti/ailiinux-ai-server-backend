"""
Integration tests for RobustHTTPClient.

Tests HTTP client retry logic, timeouts, and error handling.
Uses pytest framework with async support and mocking.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx
from app.utils.http_client import RobustHTTPClient


class TestRobustHTTPClient:
    """Test suite for RobustHTTPClient with retry logic and error handling."""

    @pytest.fixture
    def http_client(self):
        """Create a RobustHTTPClient instance for testing."""
        return RobustHTTPClient(timeout=30.0, max_retries=3)

    @pytest.mark.asyncio
    async def test_get_request_success(self, http_client):
        """
        Test successful GET request.

        Happy path: Verify successful HTTP GET request returns expected response.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": "test"}
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            response = await http_client.get("https://example.com/api")

            assert response.status_code == 200
            assert response.json() == {"data": "test"}
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_request_with_headers_and_params(self, http_client):
        """
        Test GET request with custom headers and query parameters.

        Verifies that headers and params are properly passed to the HTTP client.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            headers = {"Authorization": "Bearer token123"}
            params = {"page": 1, "limit": 10}

            await http_client.get("https://example.com/api", headers=headers, params=params)

            mock_client.get.assert_called_once_with(
                "https://example.com/api",
                headers=headers,
                params=params
            )

    @pytest.mark.asyncio
    async def test_post_request_success(self, http_client):
        """
        Test successful POST request with JSON payload.

        Happy path: Verify POST request with JSON data works correctly.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "123", "status": "created"}
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            json_data = {"name": "test", "value": 42}
            response = await http_client.post("https://example.com/api", json=json_data)

            assert response.status_code == 201
            assert response.json()["id"] == "123"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_exception_with_retry(self, http_client):
        """
        Test timeout exception triggers retry logic.

        Error condition: Verify that TimeoutException is retried up to max_retries.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Simulate timeout on all attempts
            mock_client.get.side_effect = httpx.TimeoutException("Request timeout")
            mock_client_class.return_value = mock_client

            with pytest.raises(httpx.TimeoutException, match="Request timeout"):
                await http_client.get("https://example.com/timeout")

            # Verify retry happened (3 attempts as per decorator)
            assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_network_error_with_retry(self, http_client):
        """
        Test network error triggers retry logic.

        Error condition: Verify that NetworkError is retried.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Simulate network error
            mock_client.post.side_effect = httpx.NetworkError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(httpx.NetworkError, match="Connection refused"):
                await http_client.post("https://example.com/api", json={"test": "data"})

            # Verify retry happened
            assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_retryable_status_codes(self, http_client):
        """
        Test retryable status codes (429, 500, 502, 503, 504) trigger retry.

        Error condition: Verify that specific HTTP status codes trigger retry logic.
        """
        retryable_codes = [429, 500, 502, 503, 504]

        for status_code in retryable_codes:
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_response = Mock()
                mock_response.status_code = status_code
                mock_response.request = Mock()

                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get.return_value = mock_response
                mock_client_class.return_value = mock_client

                with pytest.raises(httpx.HTTPStatusError):
                    await http_client.get(f"https://example.com/status/{status_code}")

                # Verify retry happened for retryable status codes
                assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_status_code(self, http_client):
        """
        Test non-retryable status codes (e.g., 404) do not trigger retry.

        Error condition: Verify that non-retryable status codes fail immediately.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.request = Mock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found",
                request=mock_response.request,
                response=mock_response
            )

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await http_client.get("https://example.com/notfound")

            # Should only be called once (no retry for 404)
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_eventually_succeeds(self, http_client):
        """
        Test that retry logic eventually succeeds after initial failures.

        Happy path after retry: Verify successful response after retries.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response_fail = Mock()
            mock_response_fail.status_code = 503
            mock_response_fail.request = Mock()

            mock_response_success = Mock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"status": "ok"}
            mock_response_success.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # First two calls fail with 503, third succeeds
            mock_client.get.side_effect = [
                mock_response_fail,
                mock_response_fail,
                mock_response_success
            ]
            mock_client_class.return_value = mock_client

            response = await http_client.get("https://example.com/flaky")

            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_custom_timeout_configuration(self):
        """
        Test custom timeout configuration.

        Verify that custom timeout values are properly configured.
        """
        custom_client = RobustHTTPClient(timeout=60.0, max_retries=5)

        assert custom_client.timeout.timeout == 60.0
        assert custom_client.max_retries == 5

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, http_client):
        """
        Test exponential backoff between retries.

        Verify that retry delays increase exponentially (implicit test via decorator).
        This test verifies the retry decorator is configured correctly.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client_class.return_value = mock_client

            import time
            start_time = time.time()

            with pytest.raises(httpx.TimeoutException):
                await http_client.get("https://example.com/slow")

            elapsed = time.time() - start_time

            # With exponential backoff (min=2, max=10), expect at least 2 seconds delay
            # First retry after 2s, second retry after ~4s
            assert elapsed >= 2.0, "Expected exponential backoff delay"

    @pytest.mark.asyncio
    async def test_post_with_form_data(self, http_client):
        """
        Test POST request with form data instead of JSON.

        Verify that form data is properly handled.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            form_data = {"username": "test", "password": "secret"}
            await http_client.post("https://example.com/login", data=form_data)

            mock_client.post.assert_called_once_with(
                "https://example.com/login",
                headers=None,
                json=None,
                data=form_data
            )

    @pytest.mark.asyncio
    async def test_unexpected_exception_handling(self, http_client):
        """
        Test handling of unexpected exceptions.

        Error condition: Verify that unexpected errors are properly logged and raised.
        """
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = ValueError("Unexpected error")
            mock_client_class.return_value = mock_client

            with pytest.raises(ValueError, match="Unexpected error"):
                await http_client.get("https://example.com/error")
