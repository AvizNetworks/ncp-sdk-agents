import os
import sys
import json
import time
import logging
from typing import Dict, Any, List, Optional
from functools import lru_cache

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ncp import tool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from creds_loader import get_zendesk_config


log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_EXPECTED_FIELDS = {
    # Identity
    "hostname": "Host Name",
    "serial_number": "Device Serial #",
    
    # Hardware Context
    "product": "Product",
    "switch_vendor": "Switch Vendor",
    "hardware_model": "Hardware Model",
    "chipset": "Chipset (ASIC vendor)",
    
    # Software Context
    "software_version": "Software Version",
    
    # Categorization
    "form": "Form", 
}

def _get_zendesk_auth() -> Dict[str, Any]:
    zd_config = get_zendesk_config()
    subdomain = zd_config.get("subdomain")
    email = zd_config.get("email")
    api_token = zd_config.get("api_token")

    if not subdomain or not email or not api_token:
        raise RuntimeError("Missing Zendesk credentials.")

    base_url = f"https://{subdomain}.zendesk.com/api/v2"
    auth = (f"{email}/token", api_token)
    return {"base_url": base_url, "auth": auth}

# ---------------------------------------------------------------------------
# HTTP Session
# ---------------------------------------------------------------------------

_SESSION: Optional[requests.Session] = None

def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    s = requests.Session()
    retry = Retry(
        total=3, connect=3, read=3, status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    _SESSION = s
    return s

def _request(endpoint: str, method: str = "GET", params: dict = None, data: dict = None) -> Dict[str, Any]:
    cfg = _get_zendesk_auth()
    url = endpoint if endpoint.startswith("http") else f"{cfg['base_url']}{endpoint}"
    
    session = _get_session()
    kwargs = {
        "headers": {"Content-Type": "application/json"},
        "auth": cfg["auth"],
        "params": params,
        "json": data,
        "timeout": 30
    }
    
    try:
        if method.upper() == "GET": resp = session.get(url, **kwargs)
        elif method.upper() == "PUT": resp = session.put(url, **kwargs)
        elif method.upper() == "POST": resp = session.post(url, **kwargs)
        else: raise ValueError(f"Method {method} not implemented")

        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", 2)))
            if method.upper() == "GET": resp = session.get(url, **kwargs)

        if resp.status_code >= 400:
            log.error(f"Zendesk API Error {resp.status_code}: {resp.text}")
            raise RuntimeError(f"Zendesk Error {resp.status_code}")

        return resp.json()
    except Exception as e:
        log.error(f"Request failed for {endpoint}: {e}")
        raise

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_all_ticket_fields() -> List[Dict[str, Any]]:
    fields = []
    url = "/ticket_fields.json?active=true"
    while url:
        resp = _request(url)
        fields.extend(resp.get("ticket_fields", []))
        url = resp.get("next_page")
    return fields

@lru_cache(maxsize=1)
def _get_resolved_field_map(ttl_hash=None) -> Dict[str, int]:
    # 1. Manual Override
    manual_raw = os.getenv("ZENDESK_CUSTOM_FIELD_MAP_JSON", "")
    manual_map = json.loads(manual_raw) if manual_raw else {}
    
    # 2. API Discovery
    try:
        api_fields = _fetch_all_ticket_fields()
        title_lookup = {f["title"].lower(): f["id"] for f in api_fields}
    except Exception:
        title_lookup = {}

    # 3. Merge
    final_map = manual_map.copy()
    for key, search_title in DEFAULT_EXPECTED_FIELDS.items():
        if key not in final_map:
            fid = title_lookup.get(search_title.lower())
            if fid: final_map[key] = fid
    return final_map

def _lookup_name(user_id: int, users_idx: dict) -> str:
    user = users_idx.get(user_id)
    return user.get("name", "Unknown User") if user else "Unknown User"

# ---------------------------------------------------------------------------
# The Tool
# ---------------------------------------------------------------------------

@tool
def get_zendesk_ticket(ticket_id: int) -> Dict[str, Any]:
    """
    Fetch a Zendesk ticket with FULL details:
    1. Metadata (Subject, Status)
    2. Complete Conversation History (Comments)
    3. Audit Log (Status Changes)
    4. Custom Fields (Resolved by name)
    """
    log.info(f"--- Fetching Full Details for Ticket {ticket_id} ---")

    # 1. Core Ticket
    ticket_resp = _request(f"/tickets/{ticket_id}.json?include=users,groups,organizations")
    ticket = ticket_resp.get("ticket")
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found.")

    # Build User Index
    users_idx = {u["id"]: u for u in ticket_resp.get("users", [])}
    groups_idx = {g["id"]: g for g in ticket_resp.get("groups", [])}
    orgs_idx = {o["id"]: o for o in ticket_resp.get("organizations", [])}

    # 2. Comments
    comments_resp = _request(f"/tickets/{ticket_id}/comments.json?include=users&per_page=100")
    raw_comments = comments_resp.get("comments", [])
    log.info(f"DEBUG: Found {len(raw_comments)} comments.")

    # Update User Index with comment authors
    for u in comments_resp.get("users", []):
        users_idx[u["id"]] = u

    full_conversation = []
    for c in raw_comments:
        full_conversation.append({
            "author": _lookup_name(c.get("author_id"), users_idx),
            "public": c.get("public"),
            "body": c.get("body"),
            "timestamp": c.get("created_at")
        })

    # 3. Audits
    audits_resp = _request(f"/tickets/{ticket_id}/audits.json?include=users&per_page=100")
    raw_audits = audits_resp.get("audits", [])
    log.info(f"DEBUG: Found {len(raw_audits)} audits.")
    
    # Update User Index with audit actors
    for u in audits_resp.get("users", []):
        users_idx[u["id"]] = u

    status_history = []
    for audit in raw_audits:
        for event in audit.get("events", []):
            if event.get("type") == "Change" and event.get("field_name") == "status":
                status_history.append({
                    "from": event.get("previous_value"),
                    "to": event.get("value"),
                    "actor": _lookup_name(audit.get("author_id"), users_idx),
                    "timestamp": audit.get("created_at")
                })

    # 4. Custom Fields
    field_map = _get_resolved_field_map(ttl_hash=int(time.time() / 3600))
    ticket_cf_map = {f["id"]: f["value"] for f in ticket.get("custom_fields", [])}
    
    resolved_fields = {}
    for key, fid in field_map.items():
        resolved_fields[key] = ticket_cf_map.get(fid)

    # 5. Construct Return Object
    # We place 'full_conversation' at the top level to ensure the LLM sees it.
    return {
        # --- HEADER INFO ---
        "id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "priority": ticket.get("priority"),
        "type": ticket.get("type"),
        "ticket_form": ticket.get("ticket_form_id"), # Or map to name if available
        
        # --- PEOPLE & ORG ---
        "requester": _lookup_name(ticket.get("requester_id"), users_idx),
        "organization": orgs_idx.get(ticket.get("organization_id"), {}).get("name"),
        "assignee": _lookup_name(ticket.get("assignee_id"), users_idx),
        
        # --- DEVICE CONTEXT (The Custom Fields) ---
        "device_context": {
            "hostname": resolved_fields.get("hostname"),
            "serial": resolved_fields.get("serial_number"),
            "model": resolved_fields.get("hardware_model"),
            "vendor": resolved_fields.get("switch_vendor"),
            "chipset": resolved_fields.get("chipset"),
            "version": resolved_fields.get("software_version"),
            "product": resolved_fields.get("product"),
        },
        
        # --- CLASSIFICATION ---
        "tags": ticket.get("tags", []),
        
        # --- ACTIONABLE EXTRAS ("What Else?") ---
        "next_sla_breach": ticket.get("next_sla_breach_at"), # Crucial for urgency
        "problem_id": ticket.get("problem_id"),              # Linked outage
        "attachments": [                                     # Extracted from comments
            a.get("content_url") 
            for c in raw_comments 
            for a in c.get("attachments", [])
        ],

        # --- THE CONVERSATION (Cleaned) ---
        "conversation": [
            {
                "author": c["author"],
                "role": "agent" if "Aviz" in c.get("author", "") else "customer", # Optional heuristic
                "body": c["body"], # Consider c["plain_body"] if you want to strip HTML bloat
                "public": c["public"],
                "timestamp": c["timestamp"]
            }
            for c in full_conversation
        ]
    }

@tool
def add_zendesk_private_comment(ticket_id: int, body: str) -> Dict[str, Any]:
    """
    Add a private (internal) comment to a Zendesk ticket.

    The agent MUST use this tool whenever the user asks to:
    - "add a private comment"
    - "add an internal note"
    - "add a note" to a specific ticket ID.

    The agent MUST NOT claim a comment was added unless this tool
    returns success=True.
    """
    if not body: return {"success": False, "error": "Empty body"}
    payload = {"ticket": {"comment": { "body": body, "public": False }}}
    try:
        _request(f"/tickets/{ticket_id}.json", method="PUT", data=payload)
        return {"success": True, "ticket_id": ticket_id}
    except Exception as e:
        return {"success": False, "error": str(e)}