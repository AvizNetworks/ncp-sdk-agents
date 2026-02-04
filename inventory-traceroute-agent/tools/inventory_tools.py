"""Inventory tools using the NCP Metrics API."""
from ncp import tool
from ncp.data import Metrics
from typing import Dict, Any, Optional, List
from datetime import datetime, date

def make_serializable(obj: Any) -> Any:
    """Helper to convert datetime objects to strings for JSON safety."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(i) for i in obj]
    return obj

@tool
def get_device_inventory(
    ip_address: Optional[str] = None,
    layer: Optional[str] = None,
    region: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query the network device inventory with optional filtering.
    """
    metrics = Metrics()
    try:
        filters = {}
        if ip_address: filters["ip_address"] = ip_address
        if layer: filters["layer"] = layer
        if region: filters["region"] = region

        # Query devices
        devices = metrics.get_devices(**filters)
        
        # Sanitize output
        safe_devices = make_serializable(devices)

        return {
            "success": True,
            "devices": safe_devices,
            "total_count": len(safe_devices),
            "filters_applied": filters or "None"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        metrics.close()

@tool
def find_device_details(hostname_pattern: str) -> Dict[str, Any]:
    """
    Find a specific device by its Hostname (supports wildcards like 'switch*').
    Useful when you don't know the exact hostname.
    """
    metrics = Metrics()
    try:
        search_pattern = hostname_pattern
        if "%" not in search_pattern and "*" not in search_pattern:
             search_pattern = f"%{hostname_pattern}%"
        
        search_pattern = search_pattern.replace("*", "%")
        devices = metrics.get_devices(hostname=search_pattern)
        
        if not devices:
            return {"success": False, "error": f"No device found matching '{hostname_pattern}'"}
            
        safe_devices = make_serializable(devices)
            
        return {
            "success": True,
            "count": len(safe_devices),
            "devices": safe_devices[:10],
            "note": "Showing top 10 results" if len(safe_devices) > 10 else "All results shown"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        metrics.close()

@tool
def list_interfaces(hostname: str, status: Optional[str] = None) -> Dict[str, Any]:
    """
    List network interfaces for a specific device.
    
    Args:
        hostname: The specific device hostname (e.g., 'leaf-01')
        status: Optional filter for 'up' or 'down' interfaces
    """
    metrics = Metrics()
    try:
        filters = {"hostname": hostname}
        if status:
            filters["status"] = status

        # NOTE: Using 'get_interfaces' as per standard SDK patterns.
        # If this fails, the error message will suggest alternatives.
        if hasattr(metrics, 'get_interfaces'):
            interfaces = metrics.get_interfaces(**filters)
        else:
            # Fallback: some SDKs return interfaces inside get_device_details
            details = metrics.get_device_details(hostname=hostname)
            interfaces = details.get('interfaces', [])
            # Apply manual filtering if we had to fallback
            if status:
                interfaces = [i for i in interfaces if i.get('status') == status]

        safe_interfaces = make_serializable(interfaces)

        return {
            "success": True,
            "hostname": hostname,
            "count": len(safe_interfaces),
            "interfaces": safe_interfaces
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to list interfaces: {str(e)}"}
    finally:
        metrics.close()

@tool
def get_device_details(hostname: str) -> Dict[str, Any]:
    """
    Get comprehensive information about a single network device.
    Includes: Hardware specs, Software versions, CPU/Mem metrics, and Neighbors.
    """
    metrics = Metrics()
    try:
        # This matches Tool #4 from your README
        if hasattr(metrics, 'get_device_details'):
            details = metrics.get_device_details(hostname=hostname)
        else:
            # Fallback to standard get_devices if the detailed method is missing
            # and take the first result
            results = metrics.get_devices(hostname=hostname)
            details = results[0] if results else {}

        if not details:
            return {"success": False, "error": f"Device '{hostname}' not found."}

        safe_details = make_serializable(details)

        return {
            "success": True,
            "data": safe_details
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        metrics.close()
