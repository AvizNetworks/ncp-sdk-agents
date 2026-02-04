from ncp import tool
import paramiko
import json
import os

# Locate the DB file relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "device_db.json")

def get_credentials(ip_address: str):
    """Fetch credentials from the local JSON DB."""
    try:
        if not os.path.exists(DB_FILE):
            return None, None
        
        with open(DB_FILE, 'r') as f:
            data = json.load(f)
            
        device = data.get(ip_address)
        if device:
            return device.get("username"), device.get("password")
        return None, None
    except Exception:
        return None, None

def internal_ssh_command(ip, cmd):
    """
    Internal helper to run SSH commands without using the @tool wrapper.
    This prevents the 'Tool object is not callable' error.
    """
    username, password = get_credentials(ip)
    if not username:
        return "Authentication Failed: No credentials found."

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(
            hostname=ip, 
            username=username, 
            password=password, 
            timeout=5, 
            look_for_keys=False, 
            allow_agent=False
        )
        stdin, stdout, stderr = client.exec_command(cmd, timeout=5)
        return stdout.read().decode(errors='ignore')
    except Exception as e:
        return f"Connection Failed: {str(e)}"
    finally:
        client.close()

# Full list of devices from device_db.json with vendor-specific LLDP commands
CRITICAL_DEVICES = [
    # --- SONiC Fabric ---
    {"ip": "10.4.6.13", "name": "SONiC Spine 1", "cmd": "show lldp neighbor"},
    {"ip": "10.4.6.14", "name": "SONiC Spine 2", "cmd": "show lldp neighbor"},
    {"ip": "10.4.6.11", "name": "SONiC Leaf 1",  "cmd": "show lldp neighbor"},
    {"ip": "10.4.6.12", "name": "SONiC Leaf 2",  "cmd": "show lldp neighbor"},

    # --- Arista Fabric ---
    {"ip": "10.4.6.18", "name": "Arista Spine 1", "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.19", "name": "Arista Spine 2", "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.16", "name": "Arista Leaf 1",  "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.17", "name": "Arista Leaf 2",  "cmd": "show lldp neighbors"},

    # --- Cisco Nexus Fabric ---
    {"ip": "10.4.6.23", "name": "Cisco Nexus Spine 1", "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.24", "name": "Cisco Nexus Spine 2", "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.21", "name": "Cisco Nexus Leaf 1",  "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.22", "name": "Cisco Nexus Leaf 2",  "cmd": "show lldp neighbors"},

    # --- Cisco Catalyst Fabric ---
    {"ip": "10.4.6.28", "name": "Cisco Cat Spine 1", "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.29", "name": "Cisco Cat Spine 2", "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.26", "name": "Cisco Cat Leaf 1",  "cmd": "show lldp neighbors"},
    {"ip": "10.4.6.27", "name": "Cisco Cat Leaf 2",  "cmd": "show lldp neighbors"}
]

@tool
def scan_live_topology(target: str = "all") -> str:
    """
    Dynamically scans the network using LLDP to find real-time physical connections.
    
    Args:
        target: Filter by vendor/name (e.g., 'all', 'arista', 'sonic', 'cisco').
    Returns:
        A formatted table of LIVE active links found on the devices.
    """
    report = []
    report.append(f"DYNAMIC TOPOLOGY SCAN (LLDP) - Target: {target.upper()}")
    report.append("======================================================")
    
    for device in CRITICAL_DEVICES:
        # Filter logic: skip if target is specified and doesn't match device name
        if target != "all" and target.lower() not in device["name"].lower():
            continue

        report.append(f"\n[ Scanning {device['name']} ({device['ip']}) ]")
        
        # USE THE INTERNAL HELPER, NOT THE TOOL
        result = internal_ssh_command(device["ip"], device["cmd"])
        
        # Check for SSH failures
        if "Authentication Failed" in result or "Connection Failed" in result:
            report.append("   ⚠️  Connection Failed (Device Unreachable)")
            continue

        # Basic parsing to extract neighbor info
        lines = result.split('\n')
        relevant_lines = [
            line for line in lines 
            if any(k in line for k in ["Eth", "Ethernet", "Gi", "Te", "mgmt"])
        ]
        
        if not relevant_lines:
             report.append("   No LLDP neighbors found (or output parsing failed).")
        else:
             report.append(f"   {'Local Port':<15} | {'Neighbor Device':<25} | {'Remote Port'}")
             report.append("   " + "-"*65)
             
             for line in relevant_lines[:8]: 
                 report.append(f"   {line.strip()}")

    return "\n".join(report)
