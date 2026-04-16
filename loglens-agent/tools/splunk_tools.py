"""Splunk REST API tools for NCP LogLens agent.

Connects directly to the Splunk REST API (port 8089) using token or
username/password authentication. All credentials are read from
environment variables.

Environment variables:
    SPLUNK_HOST        - Splunk server hostname or IP  (default: localhost)
    SPLUNK_PORT        - Splunk management API port    (default: 8089)
    SPLUNK_TOKEN       - Bearer token (preferred over user/pass)
    SPLUNK_USERNAME    - Splunk username (used if no token)
    SPLUNK_PASSWORD    - Splunk password (used if no token)
    SPLUNK_VERIFY_SSL  - Verify TLS cert: "true" / "false" (default: false)
"""

import os
import time
import json
import requests
from typing import Any, Dict, Optional

from ncp import tool

# ---------------------------------------------------------------------------
# Configuration (read once at import time)
# ---------------------------------------------------------------------------

_SPLUNK_HOST = os.getenv("SPLUNK_HOST", "localhost")
_SPLUNK_PORT = int(os.getenv("SPLUNK_PORT", "8089"))
_SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "")
_SPLUNK_USERNAME = os.getenv("SPLUNK_USERNAME", "admin")
_SPLUNK_PASSWORD = os.getenv("SPLUNK_PASSWORD", "changeme")
_VERIFY_SSL = os.getenv("SPLUNK_VERIFY_SSL", "false").lower() == "true"

_BASE_URL = f"https://{_SPLUNK_HOST}:{_SPLUNK_PORT}"

# Suppress InsecureRequestWarning when SSL verification is disabled
if not _VERIFY_SSL:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _session() -> requests.Session:
    """Return a pre-authenticated requests Session."""
    s = requests.Session()
    s.verify = _VERIFY_SSL
    if _SPLUNK_TOKEN:
        s.headers.update({"Authorization": f"Bearer {_SPLUNK_TOKEN}"})
    else:
        s.auth = (_SPLUNK_USERNAME, _SPLUNK_PASSWORD)
    return s


def _normalize_time(value: str) -> str:
    """Normalise human-friendly time strings to Splunk relative-time tokens."""
    v = value.strip().lower()
    mapping = {
        "now": "now",
        "all": "0",
        "all time": "0",
        "alltime": "0",
        "last 24 hours": "-24h",
        "past 24 hours": "-24h",
        "last hour": "-1h",
        "past hour": "-1h",
        "last 6 hours": "-6h",
        "past 6 hours": "-6h",
        "last 2 hours": "-2h",
        "past 2 hours": "-2h",
        "last 7 days": "-7d",
        "past 7 days": "-7d",
        "last 30 days": "-30d",
        "past 30 days": "-30d",
        "last week": "-7d",
        "last month": "-30d",
    }
    return mapping.get(v, value)


def _run_search(
    spl: str,
    earliest: str,
    latest: str,
    max_results: int,
) -> Dict[str, Any]:
    """Submit a one-shot SPL search and return parsed results."""
    s = _session()
    url = f"{_BASE_URL}/services/search/jobs"
    payload = {
        "search": spl if spl.lstrip().lower().startswith("search") else f"search {spl}",
        "earliest_time": earliest,
        "latest_time": latest,
        "exec_mode": "oneshot",
        "output_mode": "json",
        "count": str(max_results),
    }
    try:
        resp = s.post(url, data=payload, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        results = body.get("results", [])
        return {
            "success": True,
            "count": len(results),
            "results": results,
            "earliest_time": earliest,
            "latest_time": latest,
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Exported tools
# ---------------------------------------------------------------------------

@tool
def search_splunk(
    spl_query: str,
    earliest_time: str = "-24h",
    latest_time: str = "now",
    max_results: int = 1000,
) -> Dict[str, Any]:
    """Execute a Splunk SPL query against the configured Splunk instance.

    Use this tool to run any SPL (Search Processing Language) query.
    Results are returned as a list of JSON records.

    Args:
        spl_query:     Full SPL query string (with or without leading 'search').
                       Examples:
                         "search index=syslog sourcetype=syslog | stats count by host"
                         "index=main sourcetype=syslog severity=error | head 50"
        earliest_time: Splunk time token for start of range.
                       Examples: "-24h", "-7d", "-1h", "-2h", "0" (all time),
                       "2025-05-12T00:00:00", "-30d".  Default: "-24h".
        latest_time:   Splunk time token for end of range. Default: "now".
        max_results:   Maximum number of rows to return. Default: 1000.

    Returns:
        {
            "success": true,
            "count": <int>,
            "results": [ {field: value, ...}, ... ],
            "earliest_time": "<token>",
            "latest_time": "<token>"
        }
        or on error:
        {
            "success": false,
            "error": "<message>"
        }
    """
    earliest = _normalize_time(earliest_time)
    latest = _normalize_time(latest_time)
    return _run_search(spl_query, earliest, latest, max_results)


@tool
def list_indexes() -> Dict[str, Any]:
    """List all available Splunk indexes with their sourcetypes and event counts.

    Use this tool first (when you don't yet know what data is available) to
    discover index names and sourcetypes before constructing SPL queries.

    Returns:
        {
            "success": true,
            "indexes": [
                {
                    "name": "<index_name>",
                    "total_event_count": <int>,
                    "max_time": "<latest event timestamp>",
                    "min_time": "<oldest event timestamp>"
                },
                ...
            ],
            "sourcetypes": [
                { "sourcetype": "<name>", "count": <int> },
                ...
            ]
        }
    """
    s = _session()
    indexes: list = []
    sourcetypes: list = []

    # --- Indexes ---
    try:
        resp = s.get(
            f"{_BASE_URL}/services/data/indexes",
            params={"output_mode": "json", "count": 200},
            timeout=30,
        )
        resp.raise_for_status()
        for entry in resp.json().get("entry", []):
            c = entry.get("content", {})
            indexes.append({
                "name": entry.get("name"),
                "total_event_count": c.get("totalEventCount", 0),
                "max_time": c.get("maxTime", ""),
                "min_time": c.get("minTime", ""),
            })
    except Exception as e:
        return {"success": False, "error": f"Failed to list indexes: {e}"}

    # --- Sourcetypes (quick search) ---
    try:
        st_result = _run_search(
            "search index=* | stats count by sourcetype | sort -count | head 50",
            earliest="-7d",
            latest="now",
            max_results=50,
        )
        if st_result.get("success"):
            sourcetypes = [
                {"sourcetype": r.get("sourcetype", ""), "count": int(r.get("count", 0))}
                for r in st_result["results"]
            ]
    except Exception:
        pass  # sourcetypes is best-effort

    return {"success": True, "indexes": indexes, "sourcetypes": sourcetypes}


@tool
def discover_syslog_fields(index: str = "main") -> Dict[str, Any]:
    """Discover all field names available in syslog data for the given index.

    Runs a lightweight SPL probe against the syslog sourcetype and returns
    a sample record showing every field and its value. Use the field names
    returned here in all subsequent syslog queries.

    Args:
        index: Splunk index that contains syslog data (e.g. "main", "syslog",
               "network_logs"). Default: "main".

    Returns:
        {
            "success": true,
            "index": "<name>",
            "sourcetype": "syslog",
            "fields": [
                { "field_name": "<name>", "sample_value": "<value>" },
                ...
            ],
            "note": "Use exact field names in subsequent search_splunk calls."
        }

    Common syslog fields (actual names vary by sourcetype config):
        _time, host, severity, program, message, facility, source
    """
    spl = (
        f"search index={index} sourcetype=syslog earliest=-1h latest=now "
        "| head 1 | transpose "
        "| rename column as field_name, \"row 1\" as sample_value "
        "| table field_name sample_value"
    )
    result = _run_search(spl, earliest="-1h", latest="now", max_results=100)
    if not result.get("success"):
        # Fallback: try without sourcetype filter
        spl2 = (
            f"search index={index} earliest=-1h latest=now "
            "| head 1 | transpose "
            "| rename column as field_name, \"row 1\" as sample_value "
            "| table field_name sample_value"
        )
        result = _run_search(spl2, earliest="-1h", latest="now", max_results=100)

    if not result.get("success"):
        return {"success": False, "error": result.get("error", "No data found")}

    fields = [
        {"field_name": r.get("field_name", ""), "sample_value": r.get("sample_value", "")}
        for r in result.get("results", [])
        if r.get("field_name", "").strip()
    ]
    return {
        "success": True,
        "index": index,
        "sourcetype": "syslog",
        "fields": fields,
        "note": (
            "Use the exact field names above in subsequent search_splunk calls. "
            "Never guess or invent field names."
        ),
    }


@tool
def discover_flow_fields(index: str, sourcetype: str) -> Dict[str, Any]:
    """Discover all field names available in flow log data for the given index and sourcetype.

    Use this tool when querying flow telemetry data (sFlow, NetFlow, IPFIX, flowlog).
    Call it AFTER identifying the correct index and sourcetype via list_indexes.

    Flow sourcetypes vary by vendor and collector — common values:
        "sflow", "netflow", "flow", "flowlog", "ipfix", "cflow"

    Args:
        index:      Splunk index containing flow data (e.g. "main", "netflow", "flows").
        sourcetype: Sourcetype for the flow data (e.g. "sflow", "netflow", "flowlog").

    Returns:
        {
            "success": true,
            "index": "<name>",
            "sourcetype": "<name>",
            "fields": [
                { "field_name": "<name>", "sample_value": "<value>" },
                ...
            ],
            "note": "Use exact field names in subsequent search_splunk calls."
        }

    Common flow fields (actual names vary by sourcetype):
        src_addr / src / src_ip    — source IP
        dst_addr / dst / dst_ip    — destination IP
        src_port / sport           — source port
        dst_port / dport           — destination port
        proto / protocol           — L4 protocol (TCP, UDP, ...)
        bytes / total_bytes        — byte count
        packets / pkts             — packet count
        in_bytes / out_bytes       — directional byte counts
        _time                      — event timestamp
        host                       — reporting device

    Always call this tool once per index/sourcetype combination and cache
    the field names — never guess flow field names.
    """
    spl = (
        f"search index={index} sourcetype={sourcetype} earliest=-1h latest=now "
        "| head 1 | transpose "
        "| rename column as field_name, \"row 1\" as sample_value "
        "| table field_name sample_value"
    )
    result = _run_search(spl, earliest="-1h", latest="now", max_results=100)

    if not result.get("success") or not result.get("results"):
        # Fallback: broader time window
        spl2 = (
            f"search index={index} sourcetype={sourcetype} earliest=-7d latest=now "
            "| head 1 | transpose "
            "| rename column as field_name, \"row 1\" as sample_value "
            "| table field_name sample_value"
        )
        result = _run_search(spl2, earliest="-7d", latest="now", max_results=100)

    if not result.get("success"):
        return {"success": False, "error": result.get("error", "No flow data found")}

    fields = [
        {"field_name": r.get("field_name", ""), "sample_value": r.get("sample_value", "")}
        for r in result.get("results", [])
        if r.get("field_name", "").strip()
    ]

    if not fields:
        return {
            "success": False,
            "error": (
                f"No records found in index={index} sourcetype={sourcetype} "
                "in the last 7 days. Verify the index and sourcetype via list_indexes."
            ),
        }

    return {
        "success": True,
        "index": index,
        "sourcetype": sourcetype,
        "fields": fields,
        "note": (
            "Use the exact field names above in subsequent search_splunk calls. "
            "Common aliases: src_addr/src/src_ip, dst_addr/dst/dst_ip, "
            "bytes/total_bytes, proto/protocol. Never guess — use only discovered names."
        ),
    }


@tool
def get_splunk_connection_info() -> Dict[str, Any]:
    """Check Splunk connectivity and return server info.

    Use this to verify the agent can reach Splunk before running queries.
    Returns server version, build, and whether authentication succeeded.

    Returns:
        {
            "success": true,
            "host": "<hostname>",
            "port": <int>,
            "version": "<splunk version>",
            "build": "<build number>",
            "auth_method": "token" | "username_password"
        }
    """
    s = _session()
    try:
        resp = s.get(
            f"{_BASE_URL}/services/server/info",
            params={"output_mode": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        content = resp.json().get("entry", [{}])[0].get("content", {})
        return {
            "success": True,
            "host": _SPLUNK_HOST,
            "port": _SPLUNK_PORT,
            "version": content.get("version", "unknown"),
            "build": content.get("build", "unknown"),
            "auth_method": "token" if _SPLUNK_TOKEN else "username_password",
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": (
                f"Cannot connect to Splunk at {_SPLUNK_HOST}:{_SPLUNK_PORT}. "
                "Check SPLUNK_HOST and SPLUNK_PORT environment variables."
            ),
        }
    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "error": (
                f"Authentication failed (HTTP {e.response.status_code}). "
                "Check SPLUNK_TOKEN or SPLUNK_USERNAME/SPLUNK_PASSWORD."
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
