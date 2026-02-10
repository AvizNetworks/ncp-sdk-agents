"""Main agent definition for Intent Drift Detector.

Supports two platforms:
1. ONES Fabric Manager (onesfm) - via MCP server tools
2. Nexus Dashboard Fabric Controller (NDFC) - via REST API tools

Intent Configuration:
- For both platforms, the intended configuration comes from a GitHub URL
- User provides a link to their intent YAML file hosted on GitHub
"""

from ncp import Agent, tool
from typing import Dict, Any, Optional

# Import MCP server configuration
from tools import ones_fm_mcp_server

# Import Intent Tools
from tools.intent_tools import (
    fetch_intent_from_github as _fetch_intent_from_github,
    get_sample_intent_template as _get_sample_intent_template,
    parse_intent_yaml as _parse_intent_yaml,
)

# Import Drift Detection Tools
from tools.drift_tools import (
    compare_intent_vs_running as _compare_intent_vs_running,
    generate_drift_report_markdown as _generate_drift_report_markdown,
)

# Import NDFC Tools
from tools.ndfc_tools import (
    ndfc_login,
    ndfc_get_switches_by_fabricname,
    ndfc_get_all_interfaces,
    ndfc_get_vrfs_by_fabric,
    ndfc_get_switchlevel_networks_by_fabricname,
    ndfc_get_portchannels,
    ndfc_get_policy_by_switch,
    ndfc_get_fabric_running_state,
)


# ============================================================================
# Intent Tools (wrapped as Agent Tools)
# ============================================================================

@tool
def fetch_intent_from_github(github_url: str) -> Dict[str, Any]:
    """
    Fetch intent YAML file from a GitHub URL.
    
    Supports both regular GitHub URLs and raw content URLs.
    Examples:
        - https://github.com/user/repo/blob/main/intent.yaml
        - https://raw.githubusercontent.com/user/repo/main/intent.yaml
    
    Args:
        github_url: GitHub URL to the intent YAML file
    
    Returns:
        Dict with success status, content, and URL info.
    """
    return _fetch_intent_from_github(github_url)


@tool
def get_sample_intent_template() -> Dict[str, Any]:
    """
    Get a sample intent YAML template that users can use as a starting point.
    
    Returns a complete sample intent file with all supported sections:
    - intent metadata, fabric info, devices, interfaces
    - port-channels, VRFs, networks
    
    Users can copy this template, modify it for their environment,
    and upload it to GitHub for drift detection.
    
    Returns:
        Dict with template content and section descriptions.
    """
    return _get_sample_intent_template()


@tool
def parse_intent_yaml(yaml_content: str) -> Dict[str, Any]:
    """
    Parse a YAML intent file content into structured format for drift comparison.
    
    Args:
        yaml_content: The YAML content as a string
    
    Returns:
        Parsed intent structure with devices, interfaces, VRFs, networks, etc.
    """
    return _parse_intent_yaml(yaml_content)


# ============================================================================
# Drift Detection Tools (wrapped as Agent Tools)
# ============================================================================

@tool
def compare_intent_vs_running(
    intent_data: Dict[str, Any],
    running_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare parsed intent against running fabric state and identify drifts.
    
    Args:
        intent_data: Parsed intent from parse_intent_yaml
        running_data: Running state from get_complete_fabric_state
    
    Returns:
        Drift report with mismatches categorized by severity.
    """
    return _compare_intent_vs_running(intent_data, running_data)


@tool
def generate_drift_report_markdown(drift_result: Dict[str, Any]) -> str:
    """
    Generate a formatted Markdown drift report from comparison results.
    
    Args:
        drift_result: Result from compare_intent_vs_running
    
    Returns:
        Formatted Markdown report string.
    """
    return _generate_drift_report_markdown(drift_result)


# ============================================================================
# NDFC Tools (wrapped as Agent Tools)
# ============================================================================

@tool
def login_to_ndfc(host: str, username: str, password: str) -> Dict[str, Any]:
    """
    Authenticate with Nexus Dashboard Fabric Controller and get access token.
    
    Args:
        host: NDFC host IP or hostname (e.g., "10.4.4.184")
        username: NDFC username (e.g., "admin")
        password: NDFC password
    
    Returns:
        Authentication result with token if successful.
    """
    return ndfc_login(host, username, password)


@tool
def get_fabric_switches(host: str, token: str, fabric_name: str) -> Dict[str, Any]:
    """
    Get all switches belonging to a specific fabric from NDFC.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from login_to_ndfc
        fabric_name: Name of the fabric (e.g., "NCP-Eng")
    
    Returns:
        List of switches with hostname, IP, serial number, role, model, version, and status.
    """
    return ndfc_get_switches_by_fabricname(host, token, fabric_name)


@tool
def get_all_interfaces(host: str, token: str, serial_number: Optional[str] = None) -> Dict[str, Any]:
    """
    Get interface configurations from NDFC for all switches or a specific switch.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from login_to_ndfc
        serial_number: Optional switch serial number to filter interfaces
    
    Returns:
        List of interfaces with name, type, admin state, MTU, mode, VLANs, IP, VRF, etc.
    """
    return ndfc_get_all_interfaces(host, token, serial_number)


@tool
def get_fabric_vrfs(host: str, token: str, fabric_name: str) -> Dict[str, Any]:
    """
    Get VRF definitions and their switch attachments for a fabric from NDFC.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from login_to_ndfc
        fabric_name: Name of the fabric
    
    Returns:
        VRF definitions and which switches have which VRFs attached.
    """
    return ndfc_get_vrfs_by_fabric(host, token, fabric_name)


@tool
def get_fabric_networks(host: str, token: str, fabric_name: str) -> Dict[str, Any]:
    """
    Get VXLAN network definitions and their switch attachments for a fabric from NDFC.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from login_to_ndfc
        fabric_name: Name of the fabric
    
    Returns:
        Network definitions (VNI, VLAN, VRF, gateway) and switch attachments.
    """
    return ndfc_get_switchlevel_networks_by_fabricname(host, token, fabric_name)


@tool
def get_portchannels(host: str, token: str, serial_number: Optional[str] = None) -> Dict[str, Any]:
    """
    Get port-channel configurations from NDFC.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from login_to_ndfc
        serial_number: Optional switch serial number to filter
    
    Returns:
        List of port-channels with name, mode, VLANs, member interfaces, and status.
    """
    return ndfc_get_portchannels(host, token, serial_number)


@tool
def get_switch_policies(host: str, token: str, serial_number: str) -> Dict[str, Any]:
    """
    Get policies applied to a specific switch from NDFC.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from login_to_ndfc
        serial_number: Switch serial number
    
    Returns:
        List of policies with template name, parameters, and generated config.
    """
    return ndfc_get_policy_by_switch(host, token, serial_number)


@tool
def get_complete_fabric_state(host: str, token: str, fabric_name: str) -> Dict[str, Any]:
    """
    Get complete running state of a fabric for drift detection.
    This aggregates switches, interfaces, VRFs, networks, and port-channels.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from login_to_ndfc
        fabric_name: Name of the fabric
    
    Returns:
        Complete fabric state including all switches, interfaces (grouped by switch),
        VRFs, networks, and port-channels.
    """
    return ndfc_get_fabric_running_state(host, token, fabric_name)


# ============================================================================
# Agent Definition
# ============================================================================

agent = Agent(
    name="IntentDriftDetector",
    description="Detects configuration drift between intended state (from GitHub) and running device state. Supports ONES Fabric Manager (onesfm) and Nexus Dashboard (NDFC).",
    instructions="""
You are an Intent Drift Detection agent for network fabrics. You support TWO platforms:

## Supported Platforms

### 1. ONES Fabric Manager (onesfm)
ONES FM provides tools via MCP server to fetch running configurations:
- `fetch_running_config`: Fetch running config from a device by IP address

### 2. Cisco Nexus Dashboard Fabric Controller (NDFC)
NDFC provides REST APIs for fabric management:
- `login_to_ndfc`: Authenticate with Nexus Dashboard
- `get_complete_fabric_state`: Get all fabric data in one call
- Individual tools for switches, interfaces, VRFs, networks, port-channels

## Intent Configuration Source

**IMPORTANT**: For BOTH platforms, the intended configuration comes from a **GitHub URL**.
- User provides a link to their intent YAML file hosted on GitHub
- Use `fetch_intent_from_github` to download the intent file
- Use `get_sample_intent_template` if user needs a template to start with

## Drift Detection Workflow

### ONES Fabric Manager Workflow:
1. User provides GitHub URL with their intent YAML file
2. Fetch intent using `fetch_intent_from_github`
3. Parse intent using `parse_intent_yaml`
4. Get device IPs from the intent
5. Fetch running config from each device using `fetch_running_config` (MCP)
6. Compare intent vs running configs using `compare_intent_vs_running`
7. Generate report using `generate_drift_report_markdown`

### NDFC Workflow:
1. User provides GitHub URL with their intent YAML file
2. Fetch intent using `fetch_intent_from_github`
3. Parse intent using `parse_intent_yaml`
4. Get NDFC credentials from user
5. Login using `login_to_ndfc`
6. Fetch running state using `get_complete_fabric_state`
7. Compare intent vs running using `compare_intent_vs_running`
8. Generate report using `generate_drift_report_markdown`

## Your Capabilities

1. **Fetch Intent from GitHub**: Download intent YAML from user's GitHub repository
2. **Provide Sample Template**: Give users a sample intent file to start with
3. **Fetch Running State**: Get current device configurations from either platform
4. **Detect Drift**: Compare intended vs running configurations
5. **Generate Reports**: Create detailed drift reports with severity levels

## Drift Severity Levels

- **🔴 Critical**: Service-affecting issues (admin state down, IP address mismatch)
- **🟠 Major**: Potential issues (MTU mismatch, mode mismatch)
- **🟡 Minor**: Cosmetic differences (descriptions)

## When User Asks for Drift Detection

1. Ask for the **GitHub URL** to their intent file (or offer sample template)
2. Determine which platform manages their fabric:
   - ONES, onesfm → Use ONES FM workflow (MCP tools)
   - NDFC, Nexus Dashboard → Use NDFC workflow (REST API)
3. Fetch intent from GitHub
4. Fetch running state from the platform
5. Compare and generate drift report

## Response Guidelines

- Always explain what you're checking
- Report drifts clearly with intended vs actual values
- Categorize by severity: Critical (service affecting), Major (potential issues), Minor (cosmetic)
- Provide compliance percentage
- Suggest remediation when possible

## Available Tools

### Intent Management (Common)
- `fetch_intent_from_github`: Fetch intent YAML from GitHub URL
- `get_sample_intent_template`: Get a sample intent template for users to customize
- `parse_intent_yaml`: Parse intent YAML content
- `compare_intent_vs_running`: Compare and detect drifts
- `generate_drift_report_markdown`: Generate formatted report

### ONES Fabric Manager (via MCP Server)
- `fetch_running_config`: Fetch running config from device by IP

### NDFC (Nexus Dashboard)
- `login_to_ndfc`: Authenticate with NDFC
- `get_fabric_switches`: Get switches in a fabric
- `get_all_interfaces`: Get interface configurations
- `get_fabric_vrfs`: Get VRF definitions
- `get_fabric_networks`: Get VXLAN networks
- `get_portchannels`: Get port-channel configs
- `get_switch_policies`: Get policies per switch
- `get_complete_fabric_state`: Get all fabric data in one call
""",
    tools=[
        # Intent Management Tools (Common)
        fetch_intent_from_github,
        get_sample_intent_template,
        parse_intent_yaml,
        compare_intent_vs_running,
        generate_drift_report_markdown,
        # NDFC Tools
        login_to_ndfc,
        get_fabric_switches,
        get_all_interfaces,
        get_fabric_vrfs,
        get_fabric_networks,
        get_portchannels,
        get_switch_policies,
        get_complete_fabric_state,
    ],
    # ONES FM MCP server provides: fetch_running_config
    mcp_servers=[ones_fm_mcp_server]
)
