"""ONES Fabric Manager (onesfm) Tools for Intent Drift Detector.

This module provides helper utilities for integrating with ONES Fabric Manager's MCP server.

ONES FM exposes the following tool via its MCP server:
- fetch_running_config: Get current running config from a device by IP

Note: The actual MCP tool is accessed via the ones_fm_mcp_server configuration
in the agent. These are helper functions for processing the results.

Intent Configuration:
- For ONES FM, the intended configuration comes from a GitHub URL (user-provided YAML)
- NOT from fetch_last_orchestrated_intent_from_db
"""

from typing import Dict, Any, List


def process_ones_running_config(raw_config: Any) -> Dict[str, Any]:
    """
    Process and normalize running configuration fetched from ONES FM.
    
    This helper function takes the raw configuration returned by the
    ONES FM MCP server's fetch_running_config tool and normalizes it
    for comparison with intent files.
    
    Args:
        raw_config: The raw configuration from fetch_running_config MCP tool
    
    Returns:
        Dict containing normalized configuration data
    """
    if raw_config is None:
        return {
            "success": False,
            "error": "No configuration data received"
        }
    
    return {
        "success": True,
        "config": raw_config,
        "source": "ones_fm"
    }


def aggregate_ones_running_configs(configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate running configurations from multiple ONES-managed devices.
    
    This helper function combines running configs from multiple devices
    into a single structure for comprehensive drift detection.
    
    Args:
        configs: List of configuration results, each with device_ip and config
    
    Returns:
        Dict containing:
            - success: bool
            - devices: Dict mapping device IP to its normalized config
            - failed_devices: List of devices that failed to respond
    """
    devices = {}
    failed_devices = []
    
    for config_result in configs:
        device_ip = config_result.get("device_ip", "unknown")
        
        if config_result.get("success"):
            devices[device_ip] = config_result.get("config") or config_result.get("running_config")
        else:
            failed_devices.append({
                "device_ip": device_ip,
                "error": config_result.get("error", "Unknown error")
            })
    
    if not devices:
        return {
            "success": False,
            "error": "Failed to fetch config from any device",
            "failed_devices": failed_devices
        }
    
    return {
        "success": True,
        "devices": devices,
        "failed_devices": failed_devices,
        "total_devices": len(configs),
        "successful_devices": len(devices)
    }
