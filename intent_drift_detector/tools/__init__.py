"""Custom tools for intent_drift_detector.

This module provides tools for two platforms:
1. ONES Fabric Manager (onesfm) - via MCP server integration
2. Nexus Dashboard Fabric Controller (NDFC) - via REST API

Intent Source:
For BOTH platforms, the intended configuration comes from a GitHub URL.
User provides a link to their intent YAML file hosted on GitHub.

Tool Categories:
- Intent Tools: Fetch from GitHub, parse YAML, get sample template
- Drift Tools: Compare intent vs running, generate reports
- NDFC Tools: REST API integration for Nexus Dashboard
- ONES Tools: Helper utilities for MCP server integration
"""

from ncp import MCPConfig

# MCP Server configuration for ONES Fabric Manager
# Provides: fetch_running_config tool
ones_fm_mcp_server = MCPConfig(
    transport_type="sse",
    url="http://10.4.5.113:4321/sse"
)

# Import Intent Tools (GitHub fetching, YAML parsing, templates)
from .intent_tools import (
    fetch_intent_from_github,
    get_sample_intent_template,
    parse_intent_yaml,
)

# Import Drift Detection Tools (comparison, reporting)
from .drift_tools import (
    compare_intent_vs_running,
    generate_drift_report_markdown,
)

# Import NDFC tools for direct use (Nexus Dashboard)
from .ndfc_tools import (
    ndfc_login,
    ndfc_get_switches_by_fabricname,
    ndfc_get_all_interfaces,
    ndfc_get_vrfs_by_fabric,
    ndfc_get_switchlevel_networks_by_fabricname,
    ndfc_get_portchannels,
    ndfc_get_policy_by_switch,
    ndfc_get_fabric_running_state,
)

# Import ONES FM helper utilities
from .ones_tools import (
    process_ones_running_config,
    aggregate_ones_running_configs,
)

__all__ = [
    # MCP Servers
    "ones_fm_mcp_server",
    
    # Intent Tools
    "fetch_intent_from_github",
    "get_sample_intent_template",
    "parse_intent_yaml",
    
    # Drift Detection Tools
    "compare_intent_vs_running",
    "generate_drift_report_markdown",
    
    # NDFC Tools (Nexus Dashboard Fabric Controller)
    "ndfc_login",
    "ndfc_get_switches_by_fabricname",
    "ndfc_get_all_interfaces",
    "ndfc_get_vrfs_by_fabric",
    "ndfc_get_switchlevel_networks_by_fabricname",
    "ndfc_get_portchannels",
    "ndfc_get_policy_by_switch",
    "ndfc_get_fabric_running_state",
    
    # ONES FM Helper Utilities
    "process_ones_running_config",
    "aggregate_ones_running_configs",
]