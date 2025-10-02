import httpx
import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CircuitBreakerOpen(Exception):
    """Custom exception for when the circuit breaker is open."""
    pass

class HttpClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout_ms: int = 30000):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout_ms / 1000.0 # Convert ms to seconds
        self.client = httpx.AsyncClient(base_url=base_url, timeout=self.timeout)

        # Circuit Breaker state
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._circuit_open = False
        self._reset_timeout = 60 # seconds to wait before trying to close circuit

    async def _check_circuit(self):
        if not self._circuit_open:
            return

        # Circuit is open, check if it's time to try to close it (half-open state)
        if time.time() - self._last_failure_time > self._reset_timeout:
            logger.warning(f"Circuit breaker for {self.base_url} is half-open. Attempting to close.")
            self._circuit_open = False # Try to close
        else:
            raise CircuitBreakerOpen(f"Circuit breaker for {self.base_url} is open.")

    async def _record_success(self):
        self._failure_count = 0
        self._circuit_open = False

    async def _record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= 3: # Threshold for opening circuit
            logger.error(f"Circuit breaker for {self.base_url} opened due to {self._failure_count} failures.")
            self._circuit_open = True

    async def post(self, path: str, json: Dict[str, Any], headers: Optional[Dict[str, str]] = None,
                   correlation_id: Optional[str] = None, idempotency_key: Optional[str] = None,
                   retries: int = 3, backoff_factor: float = 0.5) -> Dict[str, Any]:
        await self._check_circuit()

        full_headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": correlation_id or str(uuid.uuid4()),
            **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
            **(headers or {})
        }

        for attempt in range(retries):
            try:
                response = await self.client.post(path, json=json, headers=full_headers)
                response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx responses
                await self._record_success()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in [429, 500, 502, 503, 504] and attempt < retries - 1:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning(f"Attempt {attempt + 1}/{retries} failed for {self.base_url}{path} with status {e.response.status_code}. Retrying in {sleep_time:.2f}s.")
                    await asyncio.sleep(sleep_time)
                    await self._record_failure()
                else:
                    await self._record_failure()
                    logger.error(f"Request to {self.base_url}{path} failed after {attempt + 1} attempts: {e}")
                    raise
            except httpx.RequestError as e:
                if attempt < retries - 1:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning(f"Attempt {attempt + 1}/{retries} failed for {self.base_url}{path} with network error: {e}. Retrying in {sleep_time:.2f}s.")
                    await asyncio.sleep(sleep_time)
                    await self._record_failure()
                else:
                    await self._record_failure()
                    logger.error(f"Request to {self.base_url}{path} failed after {attempt + 1} attempts: {e}")
                    raise
            except CircuitBreakerOpen:
                raise # Re-raise if circuit is already open
            except Exception as e:
                await self._record_failure()
                logger.error(f"An unexpected error occurred during request to {self.base_url}{path}: {e}")
                raise
        raise Exception("Max retries exceeded.") # Should not be reached