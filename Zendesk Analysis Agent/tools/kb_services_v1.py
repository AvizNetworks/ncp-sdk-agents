from typing import Any, Dict, List, Optional, Union
import os
import logging

from ncp import tool
from .kb_client import KBClient, KBClientConfig, KBClientError

logger = logging.getLogger(__name__)

# Initialize client from environment
_kb_client = None


def get_kb_client() -> KBClient:
    """Get or create KB client instance."""
    global _kb_client
    if _kb_client is None:
        config = KBClientConfig(
            base_url=os.getenv("KB_API_BASE", "http://SERVER-IP:PORT"),
            timeout=int(os.getenv("KB_TIMEOUT", "30")),
            max_retries=int(os.getenv("KB_MAX_RETRIES", "3")),
            api_key=os.getenv("KB_API_KEY"),
        )
        _kb_client = KBClient(config)
    return _kb_client


@tool
def kb_save_entry(
    ticket_id: int,
    subject: str,
    summary: str,
    root_cause: str,
    resolution: str,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    type: Optional[str] = None,
    organization: Optional[str] = None,
    hardware_sku: Optional[str] = None,
    category: Optional[str] = None,
    product: Optional[str] = None,
    kb_tags: Optional[Union[str, List[str]]] = None,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save or update a KB entry for a Zendesk ticket.

    The KB stores essential ticket information and LLM-generated analysis:
      • Subject and summary of the issue
      • Root cause analysis (prefixed with "Hypothesis:" or "Confirmed:")
      • Resolution steps and recommendations
      • Metadata (org, hardware, product, category)

    Args:
        ticket_id: Zendesk ticket ID (required)
        subject: Ticket subject (required)
        summary: Brief summary of the issue (required, min 10 chars)
        root_cause: Root cause analysis (required, min 10 chars)
        resolution: How it was resolved / recommended steps (required, min 10 chars)
        description: Detailed description (optional)
        status: Ticket status (new, open, pending, solved, closed)
        priority: Priority level (low, normal, high, urgent)
        type: Ticket type (question, incident, problem, task)
        organization: Organization name (e.g., "eBay", "KDDI")
        hardware_sku: Hardware SKU (e.g., "DCS-7050TX3-48C8")
        category: Issue category
        product: Product name (e.g., "NCP", "Flow Analytics")
        kb_tags: KB tags for categorization (list or comma-separated string)
        created_at: ISO timestamp when ticket was created
        updated_at: ISO timestamp when ticket was last updated

    Returns:
        Dict with:
          - success: bool
          - updated: bool (True if updated existing, False if created new)
          - ticket_id: int
          - message: str
    """
    client = get_kb_client()

    try:
        result = client.save_entry(
            ticket_id=ticket_id,
            subject=subject,
            summary=summary,
            root_cause=root_cause,
            resolution=resolution,
            description=description,
            status=status,
            priority=priority,
            type=type,
            organization=organization,
            hardware_sku=hardware_sku,
            category=category,
            product=product,
            kb_tags=kb_tags,
            created_at=created_at,
            updated_at=updated_at,
        )

        logger.info(f"KB entry saved: ticket_id={ticket_id}, updated={result.get('updated')}")
        return result

    except KBClientError as e:
        error_msg = f"Failed to save KB entry: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "updated": False,
            "message": error_msg,
        }


@tool
def kb_search_entries(
    query: str,
    organization: Optional[str] = None,
    ticket_id: Optional[int] = None,
    hardware_sku: Optional[str] = None,
    product: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    updated_after: Optional[str] = None,
    updated_before: Optional[str] = None,
    limit: int = 50,
    lite: bool = False,
) -> Dict[str, Any]:
    """
    Search the Knowledge Base for relevant entries using keywords/filters.

    Use this to find issues by keywords, hardware, organization, or time range.

    Args:
        query: Search query. Use "*" for match-all. Examples:
            - "bgp flap" - find BGP-related issues
            - "high memory usage" - find memory issues
            - "esi lag" - find ESI/LAG issues
            - "*" - return all entries (with filters)
        organization: Filter by organization (e.g., "eBay", "KDDI", "Macnica")
        ticket_id: Search for a specific ticket ID
        hardware_sku: Filter by hardware SKU
        product: Filter by product (e.g., "NCP", "Flow Analytics")
        type: Filter by ticket type (question, incident, problem, task)
        category: Filter by category
        created_after: ISO timestamp - entries created after this time
        created_before: ISO timestamp - entries created before this time
        updated_after: ISO timestamp - entries updated after this time
        updated_before: ISO timestamp - entries updated before this time
        limit: Maximum number of results (default 50, max 200)
        lite: Return lightweight entries (just metadata, no full content)

    Returns:
        Dict with:
          - success: bool
          - count: int - number of results
          - entries: List[Dict] - matching KB entries with scores
          - query_time_ms: float - search duration
          - message: str - status message
    """
    client = get_kb_client()

    try:
        result = client.search(
            query=query,
            organization=organization,
            ticket_id=ticket_id,
            hardware_sku=hardware_sku,
            product=product,
            type=type,
            category=category,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            limit=limit,
            lite=lite,
        )

        logger.info(
            f"KB search completed: query='{query}', count={result.get('count')}, "
            f"time={result.get('query_time_ms', 0):.2f}ms"
        )

        return {
            "success": True,
            **result
        }

    except KBClientError as e:
        error_msg = f"KB search failed: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "count": 0,
            "entries": [],
            "message": error_msg,
        }


@tool
def kb_get_entry(kb_id: int) -> Dict[str, Any]:
    """
    Fetch a single KB entry by its KB ID.
    
    Use this when you know the exact KB entry number.
    
    Args:
        kb_id: The KB entry ID (not ticket_id)
    
    Returns:
        Dict with:
          - success: bool
          - entry: Dict - The KB entry with full details
          - message: str
    """
    client = get_kb_client()
    
    try:
        result = client.get_entry_by_id(kb_id=kb_id)
        
        logger.info(f"KB entry fetched: kb_id={kb_id}")
        return {
            "success": True,
            "entry": result,
            "message": f"KB entry #{kb_id} retrieved successfully"
        }
    
    except KBClientError as e:
        error_msg = f"KB entry not found: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "entry": None,
            "message": error_msg,
        }


@tool
def kb_search_similar_entries(
    ticket_id: int,
    organization: Optional[str] = None,
    hardware_sku: Optional[str] = None,
    product: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Find KB entries semantically similar to a given ticket.

    Use this to find related issues even if they use different terminology.
    This uses AI/vector similarity, not keyword matching.

    Args:
        ticket_id: Reference ticket ID to find similar entries for
        organization: Filter results by organization
        hardware_sku: Filter results by hardware SKU
        product: Filter results by product
        type: Filter by ticket type
        category: Filter by category
        limit: Maximum number of results (default 20, max 100)

    Returns:
        Dict with:
          - success: bool
          - count: int - number of similar entries found
          - entries: List[Dict] - similar KB entries with similarity scores
          - query_time_ms: float - search duration
          - message: str - status message
    """
    client = get_kb_client()

    try:
        result = client.find_similar(
            ticket_id=ticket_id,
            organization=organization,
            hardware_sku=hardware_sku,
            product=product,
            type=type,
            category=category,
            limit=limit,
        )

        logger.info(
            f"Similar search completed: ticket_id={ticket_id}, count={result.get('count')}, "
            f"time={result.get('query_time_ms', 0):.2f}ms"
        )

        return {
            "success": True,
            **result
        }

    except KBClientError as e:
        error_msg = f"Similar search failed: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "count": 0,
            "entries": [],
            "message": error_msg,
        }