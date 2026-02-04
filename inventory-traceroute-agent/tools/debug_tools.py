"""Debug tool to run raw SSH commands on devices."""
from ncp import tool
import paramiko
import json
import os

# Use the same DB logic as your traceroute tool
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "device_db.json")

def get_credentials(ip_address: str):
    try:
        with open(DB_FILE, 'r') as f:
            data = json.load(f)
        dev = data.get(ip_address)
        return (dev["username"], dev["password"]) if dev else (None, None)
    except:
        return None, None

@tool
def run_ssh_command(mgmt_ip: str, command: str) -> str:
    """
    Run a raw command on a device to debug configuration.
    Useful for checking 'show ip interface brief' output manually.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    user, password = get_credentials(mgmt_ip)
    if not user:
        return f"Error: No credentials found for {mgmt_ip}"

    try:
        # Dell SONiC usually requires 'look_for_keys=False' to force password auth
        client.connect(mgmt_ip, username=user, password=password, timeout=10, allow_agent=False, look_for_keys=False)
        
        stdin, stdout, stderr = client.exec_command(command, timeout=10)
        output = stdout.read().decode(errors='ignore')
        error = stderr.read().decode(errors='ignore')
        
        # FIX: Only show the Error section if there is actual error text
        result = f"--- Output from {mgmt_ip} ---\n{output}"
        if error and error.strip():
            result += f"\n\n--- Errors ---\n{error}"
            
        return result

    except Exception as e:
        return f"SSH Failed: {str(e)}"
    finally:
        client.close()
