"""Intent management tools for Intent Drift Detector.

This module provides tools for:
1. Fetching intent YAML files from GitHub URLs
2. Providing sample intent templates
3. Parsing intent YAML content
"""

import yaml
import requests
from typing import Dict, Any


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
        Dict containing:
            - success: bool
            - content: Raw YAML content string (if successful)
            - url: The URL that was fetched
            - error: Error message (if failed)
    """
    try:
        # Convert regular GitHub URLs to raw content URLs
        raw_url = github_url
        if "github.com" in github_url and "/blob/" in github_url:
            raw_url = github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        
        # Fetch the content
        response = requests.get(raw_url, timeout=30)
        response.raise_for_status()
        
        content = response.text
        
        # Validate it's valid YAML
        yaml.safe_load(content)
        
        return {
            "success": True,
            "content": content,
            "url": github_url,
            "raw_url": raw_url
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Failed to fetch from GitHub: {str(e)}",
            "url": github_url
        }
    except yaml.YAMLError as e:
        return {
            "success": False,
            "error": f"Invalid YAML content: {str(e)}",
            "url": github_url
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": github_url
        }


def get_sample_intent_template() -> Dict[str, Any]:
    """
    Get a sample intent YAML template that users can use as a starting point.
    
    Returns a complete sample intent file with all supported sections:
    - intent metadata
    - fabric info
    - devices
    - interfaces
    - port-channels
    - VRFs
    - networks
    
    Users can copy this template, modify it for their environment,
    and upload it to GitHub for drift detection.
    
    Returns:
        Dict containing:
            - success: bool
            - template: The sample YAML template as a string
            - description: Brief description of each section
    """
    template = '''# Intent Drift Detection - Sample Intent File
# ============================================
# This file defines your desired/intended network configuration.
# Modify this template according to your fabric requirements,
# then upload to GitHub and provide the URL for drift detection.

intent:
  name: "My Fabric Intent"
  version: "1.0"
  description: "Intended configuration for production fabric"
  created_by: "network-admin"
  created_date: "2026-02-10"

fabric:
  name: "NCP-Eng"  # Your fabric name
  type: "VXLAN-EVPN"

# Define all devices in your fabric
devices:
  - hostname: "leaf-01"
    role: "leaf"
    management_ip: "10.4.6.21"
    model: "N9K-C93180YC-EX"
    nxos_version: "9.3(9)"
    
  - hostname: "leaf-02"
    role: "leaf"
    management_ip: "10.4.6.22"
    model: "N9K-C93180YC-EX"
    nxos_version: "9.3(9)"
    
  - hostname: "spine-01"
    role: "spine"
    management_ip: "10.4.6.11"
    model: "N9K-C9336C-FX2"
    nxos_version: "9.3(9)"

# Define interface configurations
interfaces:
  # Management interfaces
  - device: "leaf-01"
    name: "mgmt0"
    admin_state: "up"
    mtu: 1500
    ip_address: "10.4.6.21/24"
    vrf: "management"
    
  # Loopback interfaces (Router ID)
  - device: "leaf-01"
    name: "Loopback0"
    admin_state: "up"
    ip_address: "10.255.0.1/32"
    description: "Router ID"
    
  # Uplink interfaces (trunk mode)
  - device: "leaf-01"
    name: "Ethernet1/49"
    admin_state: "up"
    mtu: 9216
    mode: "trunk"
    allowed_vlans: "100-200"
    native_vlan: 1
    description: "Uplink to Spine-01"
    
  # Access ports (server facing)
  - device: "leaf-01"
    name: "Ethernet1/1"
    admin_state: "up"
    mtu: 9216
    mode: "access"
    access_vlan: 100
    description: "Server-01 NIC1"

# Port-channel configurations
port_channels:
  - device: "leaf-01"
    name: "port-channel10"
    admin_state: "up"
    mode: "trunk"
    allowed_vlans: "100-200"
    members:
      - "Ethernet1/10"
      - "Ethernet1/11"
    description: "VPC to Server Cluster"
    
  - device: "leaf-01"
    name: "port-channel100"
    admin_state: "up"
    mode: "trunk"
    allowed_vlans: "100-200"
    members:
      - "Ethernet1/49"
      - "Ethernet1/50"
    description: "VPC Peer-Link"

# VRF definitions (for VXLAN EVPN)
vrfs:
  - name: "PROD_VRF"
    vni: 50001
    vlan: 2001
    description: "Production VRF"
    devices:
      - "leaf-01"
      - "leaf-02"
      
  - name: "DEV_VRF"
    vni: 50002
    vlan: 2002
    description: "Development VRF"
    devices:
      - "leaf-01"
      - "leaf-02"

# VXLAN Network definitions
networks:
  - name: "PROD_WEB_NET"
    vni: 30100
    vlan: 100
    vrf: "PROD_VRF"
    gateway: "10.100.1.1/24"
    description: "Production Web Tier"
    devices:
      - "leaf-01"
      - "leaf-02"
      
  - name: "PROD_APP_NET"
    vni: 30101
    vlan: 101
    vrf: "PROD_VRF"
    gateway: "10.101.1.1/24"
    description: "Production App Tier"
    devices:
      - "leaf-01"
      - "leaf-02"
      
  - name: "PROD_DB_NET"
    vni: 30102
    vlan: 102
    vrf: "PROD_VRF"
    gateway: "10.102.1.1/24"
    description: "Production Database Tier"
    devices:
      - "leaf-01"
      - "leaf-02"
'''

    sections_description = {
        "intent": "Metadata about the intent file (name, version, author)",
        "fabric": "Fabric name and type (must match your actual fabric)",
        "devices": "List of all switches with hostname, role, IP, model, version",
        "interfaces": "Interface configurations (admin state, MTU, mode, VLANs, IPs)",
        "port_channels": "Port-channel/LAG configurations with member interfaces",
        "vrfs": "VRF definitions with VNI, VLAN, and device attachments",
        "networks": "VXLAN network segments with VNI, VLAN, VRF, gateway"
    }
    
    return {
        "success": True,
        "template": template,
        "sections": sections_description,
        "usage": "Copy this template, modify for your environment, upload to GitHub, then provide the URL for drift detection."
    }


def parse_intent_yaml(yaml_content: str) -> Dict[str, Any]:
    """
    Parse a YAML intent file content into structured format for drift comparison.
    
    Args:
        yaml_content: The YAML content as a string
    
    Returns:
        Parsed intent structure with devices, interfaces, VRFs, networks, etc.
    """
    try:
        intent = yaml.safe_load(yaml_content)
        
        # Validate basic structure
        if not intent:
            return {"success": False, "error": "Empty YAML content"}
        
        # Extract and normalize key sections
        result = {
            "success": True,
            "intent_name": intent.get("intent", {}).get("name", "Unnamed Intent"),
            "intent_version": intent.get("intent", {}).get("version", "1.0"),
            "fabric": intent.get("fabric", {}),
            "devices": intent.get("devices", []),
            "interfaces": intent.get("interfaces", []),
            "port_channels": intent.get("port_channels", []),
            "vrfs": intent.get("vrfs", []),
            "networks": intent.get("networks", []),
            "raw_intent": intent
        }
        
        # Create lookup maps for easier comparison
        result["device_map"] = {d.get("hostname"): d for d in result["devices"]}
        result["interface_map"] = {}
        for intf in result["interfaces"]:
            device = intf.get("device")
            if device not in result["interface_map"]:
                result["interface_map"][device] = {}
            result["interface_map"][device][intf.get("name")] = intf
        
        return result
    except yaml.YAMLError as e:
        return {"success": False, "error": f"YAML parsing error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error processing intent: {str(e)}"}
