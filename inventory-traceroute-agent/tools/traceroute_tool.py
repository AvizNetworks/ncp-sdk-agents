"""Traceroute tools for NCP agent with SSH Interface Discovery."""

from ncp import tool
import paramiko
import json
import os
import re
from typing import Dict, Any, List

# Locate the DB file relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "device_db.json")

def get_credentials(ip_address: str):
    """Fetch credentials from the simulated External DB (JSON)."""
    try:
        if not os.path.exists(DB_FILE):
            return None, None
        
        with open(DB_FILE, 'r') as f:
            data = json.load(f)
            
        device = data.get(ip_address)
        if device:
            return device.get("username"), device.get("password")
        return None, None
    except Exception as e:
        print(f"DB Error: {e}")
        return None, None

def parse_hops(output: str) -> List[Dict]:
    """Parses raw traceroute text into a structured list of hops."""
    hops = []
    lines = output.split('\n')
    for line in lines:
        line = line.strip()
        match = re.search(r'^\s*(\d+)\s+([\d\.]+)\s+', line)
        if match:
            hops.append({
                "hop_number": int(match.group(1)),
                "ip": match.group(2),
                "raw": line
            })
    return hops

@tool
def find_data_interface_ip(mgmt_ip: str) -> Dict[str, Any]:
    """
    SSH into the device and find a valid Data Plane IP (non-management).
    Runs 'show ip interface brief' and filters out the management subnet.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    username, password = get_credentials(mgmt_ip)
    if not username:
        return {"success": False, "error": f"No credentials for {mgmt_ip}"}

    try:
        client.connect(hostname=mgmt_ip, username=username, password=password, timeout=10, look_for_keys=False, allow_agent=False)
        
        # Run command to get IPs. Works on SONiC and most Cisco
        cmd = "show ip interface brief"
        stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
        output = stdout.read().decode(errors='ignore')
        
        # Parse for IPs. Looking for patterns like: Ethernet0  10.1.1.1
        # We explicitly exclude 10.4.6.x (Management Subnet)
        found_ips = []
        for line in output.split('\n'):
            # Regex to grab Interface Name and IP Address
            match = re.search(r'([A-Za-z]+\d+[/\d]*)\s+([\d\.]+)', line)
            if match:
                intf = match.group(1)
                ip = match.group(2)
                # FILTER: Ignore loopback, unassigned, and Mgmt Subnet (10.4.6.x)
                if ip and ip != 'unassigned' and not ip.startswith('127.') and '10.4.6.' not in ip:
                    found_ips.append({"interface": intf, "ip": ip})

        return {
            "success": True, 
            "mgmt_ip": mgmt_ip,
            "data_interfaces": found_ips,
            "raw_output": output[:500] # Snippet for debugging
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        client.close()

@tool
def run_traceroute(source_mgmt_ip: str, target_ip: str, source_interface_ip: str) -> Dict[str, Any]:
    """Run traceroute with specific source interface IP."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    username, password = get_credentials(source_mgmt_ip)
    if not username:
        return {"success": False, "error": f"No credentials for {source_mgmt_ip}"}

    try:
        client.connect(hostname=source_mgmt_ip, username=username, password=password, timeout=10, look_for_keys=False, allow_agent=False)
        
        # 1. Try Linux/SONiC Syntax (-s)
        cmd = f"traceroute -s {source_interface_ip} {target_ip}"
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        output = stdout.read().decode(errors='ignore')
        
        # 2. Fallback to Cisco Syntax
        if "invalid" in output.lower() or "syntax" in output.lower() or "%" in output:
            cmd = f"traceroute {target_ip} source {source_interface_ip}"
            stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
            output = stdout.read().decode(errors='ignore')

        hops = parse_hops(output)

        return {
            "success": True,
            "source": source_mgmt_ip,
            "source_intf": source_interface_ip,
            "target": target_ip,
            "hop_count": len(hops),
            "hops": hops,
            "raw_output": output
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        client.close()
