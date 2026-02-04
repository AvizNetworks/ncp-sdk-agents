import logging
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import wraps
import time

logger = logging.getLogger(__name__)


@dataclass
class KBClientConfig:
    """Configuration for KB client."""
    base_url: str = "http://SERVER-IP:PORT"
    api_version: str = "v1"
    timeout: int = 30
    max_retries: int = 3
    backoff_factor: float = 0.5
    api_key: Optional[str] = None


class KBClientError(Exception):
    """Base exception for KB client errors."""
    pass


class KBConnectionError(KBClientError):
    """Connection-related errors."""
    pass


class KBValidationError(KBClientError):
    """Validation errors."""
    pass


class KBServerError(KBClientError):
    """Server-side errors."""
    pass


def retry_on_failure(func):
    """Decorator to add retry logic to client methods."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                return func(self, *args, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    wait_time = self.config.backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.config.max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {self.config.max_retries} attempts")

        raise KBConnectionError(f"Failed after {self.config.max_retries} retries") from last_error

    return wrapper


class KBClient:
    """HTTP client for KB service with retry and error handling."""

    def __init__(self, config: Optional[KBClientConfig] = None):
        """Initialize KB client."""
        self.config = config or KBClientConfig()
        self.session = self._build_session()
        self.base_url = f"{self.config.base_url.rstrip('/')}/api/{self.config.api_version}"


    def _build_session(self) -> requests.Session:
        """Build requests session with retry configuration."""
        session = requests.Session()

        # Configure retries for specific HTTP methods and status codes
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
            raise_on_status=False,
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "KB-Client/2.0"
        })

        # Add API key if configured
        if self.config.api_key:
            session.headers["X-API-Key"] = self.config.api_key

        return session

    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to KB service.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            json_data: JSON payload for POST/PUT
            params: Query parameters

        Returns:
            Response JSON as dict

        Raises:
            KBConnectionError: Connection failed
            KBValidationError: 4xx client error
            KBServerError: 5xx server error
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                timeout=self.config.timeout
            )
        except requests.ConnectionError as e:
            raise KBConnectionError(f"Failed to connect to KB service at {url}") from e
        except requests.Timeout as e:
            raise KBConnectionError(f"Request timeout ({self.config.timeout}s)") from e
        except requests.RequestException as e:
            raise KBConnectionError(f"Request failed: {e}") from e

        # Handle HTTP errors
        if 400 <= response.status_code < 500:
            try:
                error_detail = response.json().get('detail', response.text[:200])
            except:
                error_detail = response.text[:200]

            raise KBValidationError(
                f"Client error {response.status_code}: {error_detail}"
            )

        if response.status_code >= 500:
            raise KBServerError(
                f"Server error {response.status_code}: {response.reason}"
            )

        # Parse response
        try:
            return response.json()
        except ValueError as e:
            raise KBServerError("Invalid JSON response from server") from e

    def health_check(self) -> Dict[str, Any]:
        """Check service health."""
        return self._request("GET", "/health")

    def get_entry_by_id(self, kb_id: int) -> Dict[str, Any]:
        """
        Fetch a single KB entry by its ID.
        
        Args:
            kb_id: The KB entry ID
            
        Returns:
            Dict containing the KB entry data
            
        Raises:
            KBClientError: If the entry is not found or request fails
        """
        # Build the full endpoint URL
        endpoint = f"entries/{kb_id}"
        
        try:
            response = self._request("GET", endpoint)
            
            if not response.get("success"):
                raise KBClientError(
                    f"Failed to fetch KB entry {kb_id}: {response.get('message', 'Unknown error')}"
                )
            
            entry = response.get("entry")
            if not entry:
                raise KBClientError(f"KB entry {kb_id} not found")
            
            return entry
            
        except Exception as e:
            raise KBClientError(f"Error fetching KB entry {kb_id}: {str(e)}")
        
    def save_entry(
        self,
        ticket_id: int,
        subject: str,
        summary: str,
        root_cause: str,
        resolution: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Save or update a KB entry.

        Args:
            ticket_id: Zendesk ticket ID
            subject: Ticket subject
            summary: Brief summary of the issue
            root_cause: Root cause (should start with "Hypothesis:" or "Confirmed:")
            resolution: How the issue was resolved
            **kwargs: Additional fields (organization, hardware_sku, etc.)

        Returns:
            Response dict with success status and ticket_id
        """
        payload = {
            "ticket_id": ticket_id,
            "subject": subject,
            "summary": summary,
            "root_cause": root_cause,
            "resolution": resolution,
            **kwargs
        }

        return self._request("POST", "/entries", json_data=payload)

    def get_entry(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a KB entry by ticket ID.

        Args:
            ticket_id: Zendesk ticket ID

        Returns:
            Entry dict or None if not found
        """
        try:
            return self._request("GET", f"/entries/{ticket_id}")
        except KBValidationError:
            return None

    def search(
        self,
        query: str,
        organization: Optional[str] = None,
        hardware_sku: Optional[str] = None,
        product: Optional[str] = None,
        limit: int = 50,
        lite: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search KB entries.

        Args:
            query: Search query (use "*" for match-all)
            organization: Filter by organization
            hardware_sku: Filter by hardware SKU
            product: Filter by product
            limit: Maximum results to return
            lite: Return lightweight entries (just metadata)
            **kwargs: Additional filters (created_after, type, etc.)

        Returns:
            Dict with 'count', 'entries', and 'query_time_ms'
        """
        payload = {
            "query": query,
            "limit": limit,
            "lite": lite,
        }

        if organization:
            payload["organization"] = organization
        if hardware_sku:
            payload["hardware_sku"] = hardware_sku
        if product:
            payload["product"] = product

        # Add any additional filters
        payload.update(kwargs)

        return self._request("POST", "/search", json_data=payload)

    def find_similar(
        self,
        ticket_id: int,
        organization: Optional[str] = None,
        limit: int = 20,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Find entries similar to a given ticket.

        Args:
            ticket_id: Reference ticket ID
            organization: Filter by organization
            limit: Maximum results to return
            **kwargs: Additional filters

        Returns:
            Dict with 'count', 'entries', and 'query_time_ms'
        """
        payload = {
            "ticket_id": ticket_id,
            "limit": limit,
        }

        if organization:
            payload["organization"] = organization # type: ignore

        payload.update(kwargs)

        return self._request("POST", f"/similar/{ticket_id}", json_data=payload)