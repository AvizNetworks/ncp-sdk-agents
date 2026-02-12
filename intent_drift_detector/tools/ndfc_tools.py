"""NDFC (Nexus Dashboard Fabric Controller) API Tools for Intent Drift Detector."""

import requests
import urllib3
from typing import Optional, Dict, List, Any

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Base API path for NDFC LAN Fabric
NDFC_API_BASE = "/appcenter/cisco/ndfc/api/v1/lan-fabric/rest"


def ndfc_login(host: str, username: str, password: str) -> Dict[str, Any]:
    """
    Authenticate with Nexus Dashboard and get JWT token and session cookies.
    
    Args:
        host: NDFC host IP or hostname (e.g., "10.4.4.184")
        username: NDFC username
        password: NDFC password
    
    Returns:
        Dict containing:
            - success: bool
            - token: JWT token string (if successful)
            - cookies: Session cookies dict (if successful)
            - error: error message (if failed)
    
    Example:
        result = ndfc_login("10.4.4.184", "admin", "password123")
        if result["success"]:
            token = result["token"]
            cookies = result["cookies"]
    """
    url = f"https://{host}/login"
    payload = {
        "userName": username,
        "userPasswd": password,
        "domain": "local"
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # NDFC returns token in either 'token' or 'jwttoken' field
        token = data.get("token") or data.get("jwttoken")
        if token:
            # Extract session cookies - CRITICAL for NDFC authentication
            cookies = dict(response.cookies)
            return {
                "success": True,
                "token": token,
                "cookies": cookies,
                "username": data.get("username"),
                "usertype": data.get("usertype")
            }
        else:
            return {
                "success": False,
                "error": "No token in response",
                "response": data
            }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


def ndfc_get_all_fabrics(host: str, token: str, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get list of all fabrics configured in NDFC.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        cookies: Session cookies from ndfc_login (optional - if not provided, AuthCookie will be set from token)
    
    Returns:
        Dict containing:
            - success: bool
            - fabrics: List of fabric objects (if successful)
            - error: error message (if failed)
    
    Each fabric object contains:
        - fabricName: Name of the fabric
        - fabricType: Type (VXLAN_EVPN, etc.)
        - asn: BGP ASN for the fabric
        - nvPairs: Fabric configuration parameters
        - templateName: Fabric template used
        - provisionMode: Provisioning mode
    """
    url = f"https://{host}{NDFC_API_BASE}/control/fabrics"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # If cookies not provided, use token as AuthCookie (they're the same in NDFC)
    if cookies is None:
        cookies = {"AuthCookie": token}
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, verify=False, timeout=30)
        response.raise_for_status()
        fabrics = response.json()
        
        # Extract key fields for easier consumption
        simplified_fabrics = []
        for fabric in fabrics:
            simplified_fabrics.append({
                "fabricName": fabric.get("fabricName"),
                "fabricType": fabric.get("fabricType"),
                "asn": fabric.get("asn"),
                "templateName": fabric.get("templateName"),
                "provisionMode": fabric.get("provisionMode"),
                "replicationMode": fabric.get("replicationMode"),
                "networkExtensionTemplate": fabric.get("networkExtensionTemplate")
            })
        
        return {
            "success": True,
            "fabrics": simplified_fabrics,
            "count": len(simplified_fabrics),
            "raw_data": fabrics  # Include full data for advanced use
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


def ndfc_get_switches_by_fabricname(host: str, token: str, fabric_name: str, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get all switches belonging to a specific fabric.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        fabric_name: Name of the fabric (e.g., "NCP-Eng")
        cookies: Session cookies from ndfc_login (required for authentication)
    
    Returns:
        Dict containing:
            - success: bool
            - switches: List of switch objects (if successful)
            - error: error message (if failed)
    
    Each switch object contains:
        - hostName: Switch hostname
        - ipAddress: Management IP
        - serialNumber: Serial number (used for other API calls)
        - switchRole: Role (leaf/spine/border)
        - model: Hardware model
        - release: NX-OS version
        - status: Reachability status
        - operStatus: Operational status
        - isVpcConfigured: VPC enabled flag
        - vpcDomain: VPC domain ID
    """
    url = f"https://{host}{NDFC_API_BASE}/control/fabrics/{fabric_name}/inventory"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # If cookies not provided, use token as AuthCookie (they're the same in NDFC)
    if cookies is None:
        cookies = {"AuthCookie": token}
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, verify=False, timeout=30)
        response.raise_for_status()
        switches = response.json()
        
        # Extract key fields for easier consumption
        simplified_switches = []
        for sw in switches:
            simplified_switches.append({
                "hostName": sw.get("hostName") or sw.get("logicalName"),
                "ipAddress": sw.get("ipAddress"),
                "serialNumber": sw.get("serialNumber"),
                "switchRole": sw.get("switchRole"),
                "model": sw.get("model"),
                "release": sw.get("release"),
                "status": sw.get("status"),
                "operStatus": sw.get("operStatus"),
                "isVpcConfigured": sw.get("isVpcConfigured"),
                "vpcDomain": sw.get("vpcDomain"),
                "fabricName": sw.get("fabricName")
            })
        
        return {
            "success": True,
            "switches": simplified_switches,
            "count": len(simplified_switches),
            "raw_data": switches  # Include full data for advanced use
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


def ndfc_get_all_interfaces(host: str, token: str, serial_number: Optional[str] = None, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get interface details for all switches or a specific switch.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        serial_number: Optional switch serial number to filter interfaces
        cookies: Session cookies from ndfc_login (required for authentication)
    
    Returns:
        Dict containing:
            - success: bool
            - interfaces: List of interface objects (if successful)
            - error: error message (if failed)
    
    Each interface object contains:
        - ifName: Interface name (e.g., Ethernet1/1)
        - ifType: Interface type (INTERFACE_ETHERNET, INTERFACE_MGMT, etc.)
        - serialNo: Switch serial number
        - sysName: Switch hostname
        - adminStatusStr: Admin state (up/down)
        - operStatusStr: Operational state
        - mtu: MTU value
        - mode: Interface mode (access/trunk)
        - allowedVLANs: Allowed VLANs for trunk
        - nativeVlanId: Native VLAN ID
        - ipAddress: IP address (for L3 interfaces)
        - vrf: VRF membership
        - channelId: Port-channel membership
        - speedValue: Interface speed
        - neighbours: CDP/LLDP neighbors
    """
    url = f"https://{host}{NDFC_API_BASE}/interface/detail"
    if serial_number:
        url += f"?serialNumber={serial_number}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # If cookies not provided, use token as AuthCookie (they're the same in NDFC)
    if cookies is None:
        cookies = {"AuthCookie": token}
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, verify=False, timeout=60)
        response.raise_for_status()
        interfaces = response.json()
        
        # Extract key fields for easier consumption
        simplified_interfaces = []
        for intf in interfaces:
            simplified_interfaces.append({
                "ifName": intf.get("ifName"),
                "ifType": intf.get("ifType"),
                "serialNo": intf.get("serialNo"),
                "sysName": intf.get("sysName"),
                "fabricName": intf.get("fabricName"),
                "adminStatusStr": intf.get("adminStatusStr"),
                "operStatusStr": intf.get("operStatusStr"),
                "mtu": intf.get("mtu"),
                "mode": intf.get("mode"),
                "allowedVLANs": intf.get("allowedVLANs"),
                "nativeVlanId": intf.get("nativeVlanId"),
                "ipAddress": intf.get("ipAddress"),
                "vrf": intf.get("vrf"),
                "channelId": intf.get("channelId"),
                "vpcId": intf.get("vpcId"),
                "speedValue": intf.get("speedValue"),
                "description": intf.get("description"),
                "neighbours": intf.get("neighbours")
            })
        
        return {
            "success": True,
            "interfaces": simplified_interfaces,
            "count": len(simplified_interfaces),
            "raw_data": interfaces
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


def ndfc_get_vrfs_by_fabric(host: str, token: str, fabric_name: str, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get VRF definitions and their switch attachments for a fabric.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        fabric_name: Name of the fabric
        cookies: Session cookies from ndfc_login (required for authentication)
    
    Returns:
        Dict containing:
            - success: bool
            - vrfs: List of VRF definitions (if successful)
            - attachments: VRF-to-switch attachments
            - error: error message (if failed)
    
    Each VRF object contains:
        - vrfName: VRF name
        - vrfId: VRF ID (VNI for VXLAN)
        - vrfVlanId: SVI VLAN for VRF
        - vrfStatus: Deployment status
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # If cookies not provided, use token as AuthCookie (they're the same in NDFC)
    if cookies is None:
        cookies = {"AuthCookie": token}
    
    result = {
        "success": True,
        "vrfs": [],
        "attachments": []
    }
    
    try:
        # Get VRF definitions
        vrf_url = f"https://{host}{NDFC_API_BASE}/top-down/fabrics/{fabric_name}/vrfs"
        vrf_response = requests.get(vrf_url, headers=headers, cookies=cookies, verify=False, timeout=30)
        vrf_response.raise_for_status()
        result["vrfs"] = vrf_response.json()
        
        # Get VRF attachments (which switches have which VRFs)
        attach_url = f"https://{host}{NDFC_API_BASE}/top-down/fabrics/{fabric_name}/vrfs/attachments"
        attach_response = requests.get(attach_url, headers=headers, cookies=cookies, verify=False, timeout=30)
        attach_response.raise_for_status()
        result["attachments"] = attach_response.json()
        
        result["vrf_count"] = len(result["vrfs"])
        result["attachment_count"] = len(result["attachments"])
        
        return result
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


def ndfc_get_switchlevel_networks_by_fabricname(host: str, token: str, fabric_name: str, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get VXLAN network definitions and their switch-level attachments for a fabric.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        fabric_name: Name of the fabric
        cookies: Session cookies from ndfc_login (required for authentication)
    
    Returns:
        Dict containing:
            - success: bool
            - networks: List of network definitions (if successful)
            - attachments: Network-to-switch attachments
            - error: error message (if failed)
    
    Each network object contains:
        - networkName: Network name
        - networkId: L2 VNI
        - vlanId: VLAN ID
        - vlanName: VLAN name
        - vrfName: Associated VRF
        - gatewayIpAddress: Anycast gateway IP
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # If cookies not provided, use token as AuthCookie (they're the same in NDFC)
    if cookies is None:
        cookies = {"AuthCookie": token}
    
    result = {
        "success": True,
        "networks": [],
        "attachments": []
    }
    
    try:
        # Get network definitions
        net_url = f"https://{host}{NDFC_API_BASE}/top-down/fabrics/{fabric_name}/networks"
        net_response = requests.get(net_url, headers=headers, cookies=cookies, verify=False, timeout=30)
        net_response.raise_for_status()
        result["networks"] = net_response.json()
        
        # Get network attachments (which switches have which networks)
        attach_url = f"https://{host}{NDFC_API_BASE}/top-down/fabrics/{fabric_name}/networks/attachments"
        attach_response = requests.get(attach_url, headers=headers, cookies=cookies, verify=False, timeout=30)
        attach_response.raise_for_status()
        result["attachments"] = attach_response.json()
        
        result["network_count"] = len(result["networks"])
        result["attachment_count"] = len(result["attachments"])
        
        return result
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


def ndfc_get_portchannels(host: str, token: str, serial_number: Optional[str] = None, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get port-channel interface details.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        serial_number: Optional switch serial number to filter
        cookies: Session cookies from ndfc_login (required for authentication)
    
    Returns:
        Dict containing:
            - success: bool
            - portchannels: List of port-channel objects (if successful)
            - error: error message (if failed)
    
    Each port-channel object contains:
        - ifName: Port-channel name (e.g., port-channel10)
        - channelId: Port-channel number
        - serialNo: Switch serial number
        - sysName: Switch hostname
        - mode: Access/Trunk mode
        - allowedVLANs: Allowed VLANs
        - portChannelMemberList: Member interfaces
        - adminStatusStr: Admin state
        - operStatusStr: Operational state
    """
    url = f"https://{host}{NDFC_API_BASE}/interface/detail?ifType=INTERFACE_PORT_CHANNEL"
    if serial_number:
        url += f"&serialNumber={serial_number}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # If cookies not provided, use token as AuthCookie (they're the same in NDFC)
    if cookies is None:
        cookies = {"AuthCookie": token}
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, verify=False, timeout=30)
        response.raise_for_status()
        portchannels = response.json()
        
        # Extract key fields
        simplified_pcs = []
        for pc in portchannels:
            simplified_pcs.append({
                "ifName": pc.get("ifName"),
                "channelId": pc.get("channelId"),
                "serialNo": pc.get("serialNo"),
                "sysName": pc.get("sysName"),
                "fabricName": pc.get("fabricName"),
                "mode": pc.get("mode"),
                "allowedVLANs": pc.get("allowedVLANs"),
                "nativeVlanId": pc.get("nativeVlanId"),
                "adminStatusStr": pc.get("adminStatusStr"),
                "operStatusStr": pc.get("operStatusStr"),
                "mtu": pc.get("mtu"),
                "vpcId": pc.get("vpcId"),
                "portChannelMemberList": pc.get("portChannelMemberList"),
                "priMemberIntfList": pc.get("priMemberIntfList"),
                "secMemberIntfList": pc.get("secMemberIntfList")
            })
        
        return {
            "success": True,
            "portchannels": simplified_pcs,
            "count": len(simplified_pcs),
            "raw_data": portchannels
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


def ndfc_get_policy_by_switch(host: str, token: str, serial_number: str, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get policies applied to a specific switch.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        serial_number: Switch serial number
        cookies: Session cookies from ndfc_login (required for authentication)
    
    Returns:
        Dict containing:
            - success: bool
            - policies: List of policy objects (if successful)
            - error: error message (if failed)
    
    Each policy object contains:
        - policyId: Policy ID
        - description: Policy description
        - templateName: Template name
        - nvPairs: Policy parameters
        - generatedConfig: Generated configuration
        - status: Policy status
    """
    url = f"https://{host}{NDFC_API_BASE}/control/policies/switches/{serial_number}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # If cookies not provided, use token as AuthCookie (they're the same in NDFC)
    if cookies is None:
        cookies = {"AuthCookie": token}
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, verify=False, timeout=30)
        response.raise_for_status()
        policies = response.json()
        
        # Extract key fields
        simplified_policies = []
        for policy in policies:
            simplified_policies.append({
                "policyId": policy.get("policyId"),
                "description": policy.get("description"),
                "templateName": policy.get("templateName"),
                "templateContentType": policy.get("templateContentType"),
                "nvPairs": policy.get("nvPairs"),
                "generatedConfig": policy.get("generatedConfig"),
                "status": policy.get("status"),
                "priority": policy.get("priority"),
                "autoGenerated": policy.get("autoGenerated")
            })
        
        return {
            "success": True,
            "policies": simplified_policies,
            "count": len(simplified_policies),
            "serial_number": serial_number,
            "raw_data": policies
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e)
        }


# Convenience function to get a complete running state for drift detection
def ndfc_get_fabric_running_state(host: str, token: str, fabric_name: str, cookies: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get complete running state of a fabric for drift detection.
    This is a convenience function that aggregates data from multiple APIs.
    
    Args:
        host: NDFC host IP or hostname
        token: JWT token from ndfc_login
        fabric_name: Name of the fabric
        cookies: Session cookies from ndfc_login (required for authentication)
    
    Returns:
        Dict containing:
            - success: bool
            - fabric_name: Fabric name
            - switches: All switches in fabric
            - interfaces: All interfaces (grouped by switch)
            - vrfs: VRF definitions and attachments
            - networks: Network definitions and attachments
            - portchannels: Port-channel configurations
            - errors: List of any errors encountered
    """
    result = {
        "success": True,
        "fabric_name": fabric_name,
        "switches": [],
        "interfaces_by_switch": {},
        "vrfs": {},
        "networks": {},
        "portchannels": [],
        "errors": []
    }
    
    # Get switches
    switches_result = ndfc_get_switches_by_fabricname(host, token, fabric_name, cookies)
    if switches_result["success"]:
        result["switches"] = switches_result["switches"]
    else:
        result["errors"].append(f"Failed to get switches: {switches_result.get('error')}")
    
    # Get all interfaces
    interfaces_result = ndfc_get_all_interfaces(host, token, cookies=cookies)
    if interfaces_result["success"]:
        # Group interfaces by switch hostname
        for intf in interfaces_result["interfaces"]:
            switch_name = intf.get("sysName", "unknown")
            if switch_name not in result["interfaces_by_switch"]:
                result["interfaces_by_switch"][switch_name] = []
            result["interfaces_by_switch"][switch_name].append(intf)
    else:
        result["errors"].append(f"Failed to get interfaces: {interfaces_result.get('error')}")
    
    # Get VRFs
    vrfs_result = ndfc_get_vrfs_by_fabric(host, token, fabric_name, cookies)
    if vrfs_result["success"]:
        result["vrfs"] = {
            "definitions": vrfs_result["vrfs"],
            "attachments": vrfs_result["attachments"]
        }
    else:
        result["errors"].append(f"Failed to get VRFs: {vrfs_result.get('error')}")
    
    # Get Networks
    networks_result = ndfc_get_switchlevel_networks_by_fabricname(host, token, fabric_name, cookies)
    if networks_result["success"]:
        result["networks"] = {
            "definitions": networks_result["networks"],
            "attachments": networks_result["attachments"]
        }
    else:
        result["errors"].append(f"Failed to get networks: {networks_result.get('error')}")
    
    # Get Port-channels
    portchannels_result = ndfc_get_portchannels(host, token, cookies=cookies)
    if portchannels_result["success"]:
        result["portchannels"] = portchannels_result["portchannels"]
    else:
        result["errors"].append(f"Failed to get port-channels: {portchannels_result.get('error')}")
    
    # Set overall success based on whether we got critical data
    if not result["switches"]:
        result["success"] = False
    
    return result
