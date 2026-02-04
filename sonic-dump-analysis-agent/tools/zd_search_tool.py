import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

import requests
from ncp import tool
from .zd_tools import _get_zendesk_auth, _lookup_name, _request

logging.basicConfig(level=logging.INFO)


def _coerce_int(value: Optional[Any], name: str) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer (got {value!r})")


def _parse_ts(ts: str) -> datetime:
    # Zendesk timestamps: "2025-11-21T07:10:23Z"
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _fetch_user(user_id: int, auth_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch a single user by ID."""
    try:
        resp = requests.get(
            f"{auth_cfg['base_url']}/users/{user_id}.json",
            headers={"Content-Type": "application/json"},
            auth=auth_cfg["auth"],
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("user", {})
    except Exception as e:
        logging.warning(f"Failed to fetch user {user_id}: {e}")
        return {}


def _fetch_organization(org_id: int, auth_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch a single organization by ID."""
    try:
        resp = requests.get(
            f"{auth_cfg['base_url']}/organizations/{org_id}.json",
            headers={"Content-Type": "application/json"},
            auth=auth_cfg["auth"],
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("organization", {})
    except Exception as e:
        logging.warning(f"Failed to fetch organization {org_id}: {e}")
        return {}


def _resolve_user_name(user_id: Optional[int], users_idx: Dict[int, Dict[str, Any]], 
                       auth_cfg: Dict[str, Any]) -> str:
    """Resolve user ID to name, fetching from API if not in cache."""
    if not user_id:
        return "Unassigned"
    
    # Check cache first
    if user_id in users_idx:
        return users_idx[user_id].get("name", "Unknown User")
    
    # Fetch from API and cache
    user = _fetch_user(user_id, auth_cfg)
    if user:
        users_idx[user_id] = user
        return user.get("name", "Unknown User")
    
    return "Unknown User"


def _resolve_org_name(org_id: Optional[int], orgs_idx: Dict[int, Dict[str, Any]], 
                      auth_cfg: Dict[str, Any]) -> Optional[str]:
    """Resolve organization ID to name, fetching from API if not in cache."""
    if not org_id:
        return None
    
    # Check cache first
    if org_id in orgs_idx:
        return orgs_idx[org_id].get("name")
    
    # Fetch from API and cache
    org = _fetch_organization(org_id, auth_cfg)
    if org:
        orgs_idx[org_id] = org
        return org.get("name")
    
    return None

def _format_timestamp_with_relative(ts: Optional[str]) -> str:
    """Convert ISO timestamp to human-readable format with relative time."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt
        
        # Relative time
        if diff.total_seconds() < 60:
            relative = "just now"
        elif diff.total_seconds() < 3600:
            mins = int(diff.total_seconds() / 60)
            relative = f"{mins} min{'s' if mins != 1 else ''} ago"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            relative = f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.days < 7:
            relative = f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            relative = f"{weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            # For dates older than a month, just show the absolute date
            return dt.strftime("%b %d, %Y %I:%M %p UTC")
        
        # Absolute time (for recent dates)
        absolute = dt.strftime("%b %d, %I:%M %p UTC")
        
        return f"{relative} ({absolute})"
    except Exception as e:
        logging.warning(f"Failed to format timestamp {ts}: {e}")
        return ts

def _build_search_query(
    days_back: int,
    time_field: str,
    requester_name: Optional[str],
    organization_name: Optional[str],
    assignee_name: Optional[str],
    status: Optional[str],
    priority: Optional[str],
    keyword: Optional[str],
) -> str:
    """
    Build Zendesk search query string.
    """
    parts: List[str] = ["type:ticket"]

    # Broad time window (Zendesk only supports date-level granularity)
    if days_back and days_back > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        since_str = since.strftime("%Y-%m-%d")
        tf = "created" if time_field == "created" else "updated"
        parts.append(f"{tf}>={since_str}")

    if requester_name:
        parts.append(f'requester:"{requester_name}"')

    if organization_name:
        parts.append(f'organization:"{organization_name}"')

    if assignee_name:
        parts.append(f'assignee:"{assignee_name}"')

    if status:
        # Handle multiple statuses: "open,pending" or single "open"
        statuses = [s.strip() for s in status.split(',')]
        for s in statuses:
            if s.lower() in ["new", "open", "pending", "hold", "solved", "closed"]:
                parts.append(f"status:{s.lower()}")

    if priority:
        # Handle priority filter
        p = priority.strip().lower()
        if p in ["low", "normal", "high", "urgent"]:
            parts.append(f"priority:{p}")
        elif p.startswith('>') or p.startswith('<'):
            parts.append(f"priority{p}")
        else:
            parts.append(f"priority:{p}")

    if keyword:
        # Clean up keyword - remove ALL invalid Zendesk syntax
        cleaned = keyword.strip()
        
        # List of invalid patterns and words to completely remove
        invalid_patterns = [
            'sort:', 'sort_by:', 'sort_order:', 
            'fields=', 'include=', 
            'desc', 'asc',
            'ticket_id', 'subject', 'status', 'priority', 
            'updated_at', 'created_at', 'assignee', 'group', 'requester'
        ]
        
        # Split keyword into words and filter out invalid ones
        words = cleaned.split()
        valid_words = []
        
        for word in words:
            # Check if word starts with any invalid pattern or is an invalid word
            is_invalid = False
            for pattern in invalid_patterns:
                if word.lower().startswith(pattern) or word.lower() == pattern:
                    is_invalid = True
                    break
            
            if not is_invalid:
                valid_words.append(word)
        
        cleaned = ' '.join(valid_words)
        
        if cleaned:
            parts.append(cleaned)

    return " ".join(parts)


@tool
def search_zendesk_tickets(
    days_back: int = 7,
    minutes_back: Optional[int] = None,
    max_results: int = 50,
    requester_name: Optional[str] = None,
    organization_name: Optional[str] = None,
    assignee_name: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    keyword: Optional[str] = None,
    time_field: str = "updated",
) -> Dict[str, Any]:
    """
    Search Zendesk tickets with support for minute-level filtering.

    Parameters:
      - days_back: Number of days to look back (default: 7)
      - minutes_back: Optional precise minute-level filter
      - max_results: Maximum number of results to return (default: 50)
      - requester_name: Filter by requester name
      - organization_name: Filter by organization name
      - assignee_name: Filter by assignee name
      - status: Filter by status - single ("open") or multiple ("open,pending")
      - priority: Filter by priority:
          * Exact: "low", "normal", "high", "urgent"
          * Comparison: ">normal" (gets high+urgent), ">=high"
      - keyword: Additional free-text search terms
      - time_field: Which timestamp to filter on - "created" or "updated" (default: "updated")

    Returns tickets with requester, assignee, and organization names resolved.
    """

    # Normalise / coerce inputs
    days_back_int = _coerce_int(days_back, "days_back") or 0
    max_results_int = _coerce_int(max_results, "max_results") or 50
    minutes_back_int = (
        _coerce_int(minutes_back, "minutes_back") if minutes_back is not None else None
    )

    if max_results_int <= 0:
        raise ValueError("max_results must be > 0")

    # Sanitise time_field
    time_field = (time_field or "updated").lower()
    if time_field not in ("created", "updated"):
        time_field = "updated"

    query = _build_search_query(
        days_back=days_back_int,
        time_field=time_field,
        requester_name=requester_name,
        organization_name=organization_name,
        assignee_name=assignee_name,
        status=status,
        priority=priority,
        keyword=keyword,
    )

    logging.info(f"Zendesk search query: {query} (time_field={time_field})")

    cfg = _get_zendesk_auth()
    base_url = cfg["base_url"]
    auth = cfg["auth"]
    auth_cfg = {"base_url": base_url, "auth": auth}

    # Add include=users,organizations to get user/org details
    endpoint = f"{base_url}/search.json"
    all_tickets: List[Dict[str, Any]] = []
    users_idx: Dict[int, Dict[str, Any]] = {}
    orgs_idx: Dict[int, Dict[str, Any]] = {}
    url: Optional[str] = endpoint
    params: Optional[Dict[str, Any]] = {
        "query": query,
        "sort_by": f"{time_field}_at",
        "sort_order": "desc",
        "include": "users,organizations",  # Include user and org data
    }

    # Fetch results across pages
    while url and len(all_tickets) < max_results_int:
        resp = requests.get(
            url,
            headers={"Content-Type": "application/json"},
            auth=auth,
            params=params if "search.json" in url else None,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # Build user and organization indexes from included data
        for u in data.get("users", []):
            users_idx[u["id"]] = u
        for o in data.get("organizations", []):
            orgs_idx[o["id"]] = o

        for r in data.get("results", []):
            if r.get("result_type") != "ticket":
                continue
            
            # Get IDs
            requester_id = r.get("requester_id")
            assignee_id = r.get("assignee_id")
            org_id = r.get("organization_id")
            
            # Resolve names (will fetch from API if not in cache)
            requester_name = _resolve_user_name(requester_id, users_idx, auth_cfg)
            assignee_name = _resolve_user_name(assignee_id, users_idx, auth_cfg) if assignee_id else "Unassigned"
            org_name = _resolve_org_name(org_id, orgs_idx, auth_cfg)
            
            all_tickets.append(
                {
                    "id": r.get("id"),
                    "subject": r.get("subject"),
                    "description": r.get("description"),
                    "status": r.get("status"),
                    "priority": r.get("priority"),
                    "type": r.get("type"),
                    "requester": requester_name,
                    "assignee": assignee_name,
                    "organization": org_name,
                    "tags": r.get("tags", []),
                    # Store RAW timestamps for filtering
                    "created_at_raw": r.get("created_at"),
                    "updated_at_raw": r.get("updated_at"),
                    # Store FORMATTED timestamps for display
                    "created_at": _format_timestamp_with_relative(r.get("created_at")),
                    "updated_at": _format_timestamp_with_relative(r.get("updated_at")),
                }
            )
            #logging.info(f"DEBUG: Ticket {r.get('id')} - Raw: {r.get('updated_at')} -> Formatted: {_format_timestamp_with_relative(r.get('updated_at'))}")
            if len(all_tickets) >= max_results_int:
                break

        url = data.get("next_page")
        params = None

    # Precise time-window filtering
    if minutes_back_int is not None and minutes_back_int > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes_back_int)
        ts_key = f"{time_field}_at_raw"  # Use the RAW timestamp
        all_tickets = [
            t
            for t in all_tickets
            if t.get(ts_key) and _parse_ts(t[ts_key]) >= cutoff
        ]

    # Clean up: ALWAYS remove the _raw fields before returning
    for ticket in all_tickets:
        ticket.pop("created_at_raw", None)
        ticket.pop("updated_at_raw", None)

    return {
        "query": query,
        "time_field": time_field,
        "minutes_back": minutes_back_int,
        "count": len(all_tickets),
        "tickets": all_tickets,
    }