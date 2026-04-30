
# --------------------------------------------------
# Intent Template Library
# --------------------------------------------------
import subprocess
import yaml
import re
import shutil

from ncp import tool

INTENT_TEMPLATES = {
    "bgp_peering": {
        "intent_type": "bgp_peering",
        "bgp_intent": {
            "as_number": 65000,
            "routers": []
        }
    }
}


# --------------------------------------------------
# TOOL: List Supported Intents
# --------------------------------------------------

@tool
def list_supported_intents() -> list:
    return list(INTENT_TEMPLATES.keys())


# --------------------------------------------------
# TOOL: Get Intent Template
# --------------------------------------------------

@tool
def get_intent_template(intent_type: str) -> dict:

    template = INTENT_TEMPLATES.get(intent_type)

    if template:
        return template

    return {"error": "Intent template not found"}


# --------------------------------------------------
# TOOL: Parse BGP Intent
# --------------------------------------------------

@tool
def parse_bgp_intent(user_input: str) -> dict:
    """
    Extract IPs, ASN and credentials from user request
    """

    # Extract ASN
    as_match = re.search(r"(?:asn|as)\s*(?:number)?\s*(\d+)", user_input, re.IGNORECASE)
    as_number = int(as_match.group(1)) if as_match else 1001

    # Extract IP addresses
    ip_pattern = r"(?:\d{1,3}\.){3}\d{1,3}"
    ips = list(set(re.findall(ip_pattern, user_input)))

    if len(ips) < 2:
        return {"error": "At least two IP addresses required"}

    # Extract credentials
    cred_match = re.search(r"creds?\s*(?:are|=)?\s*([\w\-]+)\/([\w@\!\#\$%\^\&\*\(\)\-]+)", user_input)

    username = cred_match.group(1) if cred_match else "admin"
    password = cred_match.group(2) if cred_match else "admin"

    routers = []

    for i, ip in enumerate(ips):

        neighbors = []

        for peer in ips:
            if peer != ip:
                neighbors.append({
                    "ip": peer,
                    "remote_as": as_number
                })

        routers.append({
            "hostname": f"router{i+1}",
            "router_id": ip,
            "username": username,
            "password": password,
            "neighbors": neighbors
        })

    return {
        "intent_type": "bgp_peering",
        "bgp_intent": {
            "as_number": as_number,
            "routers": routers
        }
    }


# --------------------------------------------------
# TOOL: Validate Intent
# --------------------------------------------------

@tool
def validate_bgp_intent(intent: dict) -> str:

    if "bgp_intent" not in intent:
        return "Invalid intent: missing bgp_intent"

    bgp = intent["bgp_intent"]

    if "as_number" not in bgp:
        return "Invalid intent: missing AS number"

    if not bgp.get("routers"):
        return "Invalid intent: routers missing"

    return "Intent validation successful"


# --------------------------------------------------
# TOOL: Generate YAML
# --------------------------------------------------

@tool
def generate_intent_yaml(intent: dict) -> str:
    return yaml.dump(intent, sort_keys=False)


# --------------------------------------------------
# TOOL: Check if Ansible Exists
# --------------------------------------------------

@tool
def check_ansible_installed() -> str:

    if shutil.which("ansible"):
        return "Ansible is installed"
    else:
        return "Ansible is NOT installed"


# --------------------------------------------------
# TOOL: Configure BGP
# --------------------------------------------------
# @tool
# def run_ansible_bgp(intent_yaml: str) -> str:

#     import yaml
#     import subprocess

#     intent = yaml.safe_load(intent_yaml)

#     routers = intent["bgp_intent"]["routers"]
#     base_as = intent["bgp_intent"]["as_number"]

#     results = []

#     for i, router in enumerate(routers):

#         router_ip = router["router_id"]
#         user = router["username"]
#         pwd = router["password"]

#         local_as = base_as + i

#         for neighbor in router["neighbors"]:

#             neighbor_ip = neighbor["ip"]
#             neighbor_as = base_as + (0 if i == 1 else 1)

#             cmd_text = f"""
# vtysh -c "configure terminal" \
# -c "no router bgp" \
# -c "router bgp {local_as}" \
# -c "bgp router-id {router_ip}" \
# -c "neighbor {neighbor_ip} remote-as {neighbor_as}" \
# -c "end" \
# -c "write memory"
# """

#             cmd = [
#                 "ansible",
#                 router_ip,
#                 "-i",
#                 f"{router_ip},",
#                 "-m",
#                 "shell",
#                 "-a",
#                 cmd_text,
#                 "-e",
#                 f"ansible_user={user} ansible_password={pwd} ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
#             ]

#             result = subprocess.run(cmd, capture_output=True, text=True)

#             results.append(result.stdout)

#     return "\n".join(results)

@tool
def run_ansible_bgp(intent_yaml: str) -> str:

    import yaml
    import subprocess
    from concurrent.futures import ThreadPoolExecutor, as_completed

    intent = yaml.safe_load(intent_yaml)

    routers = intent["bgp_intent"]["routers"]
    base_as = intent["bgp_intent"]["as_number"]

    results = []

    def configure_router(router_index, router):

        router_ip = router["router_id"]
        username = router["username"]
        password = router["password"]

        local_as = base_as + router_index

        neighbors_cmd = ""

        for peer_index, peer in enumerate(routers):

            if peer["router_id"] != router_ip:

                peer_ip = peer["router_id"]
                peer_as = base_as + peer_index

                neighbors_cmd += f'-c "neighbor {peer_ip} remote-as {peer_as}" '

        cmd_text = f"""
vtysh -c "configure terminal" \
-c "router bgp {local_as}" \
-c "bgp router-id {router_ip}" \
{neighbors_cmd} \
-c "end" \
-c "write memory"
"""

        cmd = [
            "ansible",
            router_ip,
            "-i",
            f"{router_ip},",
            "-m",
            "shell",
            "-a",
            cmd_text,
            "-e",
            f"ansible_user={username} ansible_password={password} ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        return f"\nRouter {router_ip}:\n{result.stdout if result.stdout else result.stderr}"

    # Parallel execution
    with ThreadPoolExecutor(max_workers=20) as executor:

        futures = [
            executor.submit(configure_router, i, router)
            for i, router in enumerate(routers)
        ]

        for future in as_completed(futures):
            results.append(future.result())

        # Create a playbook file and save
        with open("bgp_configuration_playbook.yaml", "w") as f:
            yaml.dump(intent, f, sort_keys=False)   

            

    return "\n".join(results)


# --------------------------------------------------
# TOOL: Check Existing BGP
# --------------------------------------------------

@tool
def check_existing_bgp_connection(intent: dict) -> str:

    try:

        routers = intent["bgp_intent"]["routers"]

        r1 = routers[0]
        r2 = routers[1]

        router_ip = r1["router_id"]
        neighbor_ip = r2["router_id"]

        user = r1["username"]
        pwd = r1["password"]

        cmd = [
            "ansible",
            router_ip,
            "-i",
            f"{router_ip},",
            "-m",
            "shell",
            "-a",
            f"vtysh -c 'show ip bgp neighbor {neighbor_ip}'",
            "-e",
            f"ansible_user={user} ansible_password={pwd} ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout.lower()

        if "established" in output:
            return f"BGP session ESTABLISHED between {router_ip} and {neighbor_ip}\n\n{result.stdout}"

        if "active" in output or "idle" in output:
            return f"BGP configured but NOT established between {router_ip} and {neighbor_ip}\n\n{result.stdout}"

        return f"No BGP session detected between {router_ip} and {neighbor_ip}"

    except Exception as e:
        return str(e)


# --------------------------------------------------
# TOOL: Check BGP Summary
# --------------------------------------------------

@tool
def check_bgp_status(intent: dict) -> str:

    try:

        routers = intent["bgp_intent"]["routers"]

        outputs = []

        for router in routers:

            router_ip = router["router_id"]
            user = router["username"]
            pwd = router["password"]

            cmd = [
                "ansible",
                router_ip,
                "-i",
                f"{router_ip},",
                "-m",
                "shell",
                "-a",
                "vtysh -c 'show ip bgp summary'",
                "-e",
                f"ansible_user={user} ansible_password={pwd} ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            outputs.append(f"\nRouter {router_ip}:\n{result.stdout}")

        return "\n".join(outputs)

    except Exception as e:
        return str(e)


# --------------------------------------------------
# TOOL: Remove BGP
# --------------------------------------------------

@tool
def remove_bgp_configuration(intent: dict) -> str:

    try:

        intent = yaml.safe_load(intent) if isinstance(intent, str) else intent

        routers = intent["bgp_intent"]["routers"]
        asn = intent["bgp_intent"]["as_number"]

        results = []

        for router in routers:

            router_ip = router["router_id"]
            user = router["username"]
            pwd = router["password"]

            cmd_text = f'vtysh -c "configure terminal" -c "no router bgp {asn}" -c "write memory"'

            cmd = [
                "ansible",
                router_ip,
                "-i",
                f"{router_ip},",
                "-m",
                "shell",
                "-a",
                cmd_text,
                "-e",
                f"ansible_user={user} ansible_password={pwd} ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            results.append(result.stdout if result.returncode == 0 else result.stderr)

        return "\n".join(results)

    except Exception as e:
        return str(e)
    

##### VLAN
@tool
def parse_vlan_intent(user_input: str) -> dict:
    """
    Extract VLAN ID, VLAN name and switch IPs
    """

    vlan_match = re.search(r"vlan\s*(\d+)", user_input, re.IGNORECASE)
    vlan_id = int(vlan_match.group(1)) if vlan_match else None

    name_match = re.search(r"name\s*(\w+)", user_input, re.IGNORECASE)
    vlan_name = name_match.group(1) if name_match else f"VLAN{vlan_id}"

    ip_pattern = r"(?:\d{1,3}\.){3}\d{1,3}"
    ips = list(set(re.findall(ip_pattern, user_input)))

    cred_match = re.search(r"creds?\s*(?:are|=)?\s*([\w\-]+)\/([\w@\!\#\$%\^\&\*\(\)\-]+)", user_input)

    username = cred_match.group(1) if cred_match else "admin"
    password = cred_match.group(2) if cred_match else "admin"

    switches = []

    for ip in ips:
        switches.append({
            "ip": ip,
            "username": username,
            "password": password
        })

    return {
        "intent_type": "vlan_create",
        "vlan_intent": {
            "vlan_id": vlan_id,
            "vlan_name": vlan_name,
            "switches": switches
        }
    }

@tool
def run_ansible_vlan(intent: dict) -> str:

    intent = yaml.safe_load(intent) if isinstance(intent, str) else intent

    vlan_id = intent["vlan_intent"]["vlan_id"]
    vlan_name = intent["vlan_intent"]["vlan_name"]
    switches = intent["vlan_intent"]["switches"]

    results = []

    for sw in switches:

        ip = sw["ip"]
        user = sw["username"]
        pwd = sw["password"]

        # SONiC style VLAN configuration
        cmd_text = f"""
config vlan add {vlan_id}
"""

        cmd = [
            "ansible",
            ip,
            "-i",
            f"{ip},",
            "-m",
            "shell",
            "-a",
            cmd_text,
            "-e",
            f"ansible_user={user} ansible_password={pwd} ansible_become=true ansible_become_method=sudo ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        results.append(result.stdout if result.stdout else result.stderr)

    return "\n".join(results)

@tool
def remove_vlan(intent: dict) -> str:

    try:

        intent = yaml.safe_load(intent) if isinstance(intent, str) else intent

        vlan_id = intent["vlan_intent"]["vlan_id"]
        switches = intent["vlan_intent"]["switches"]

        results = []

        for sw in switches:

            ip = sw["ip"]
            user = sw["username"]
            pwd = sw["password"]

            cmd_text = f"config vlan del {vlan_id}"

            cmd = [
                "ansible",
                ip,
                "-i",
                f"{ip},",
                "-m",
                "shell",
                "-a",
                cmd_text,
                "-e",
                f"ansible_user={user} ansible_password={pwd} ansible_become=true ansible_become_method=sudo ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
   
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                results.append(f"VLAN {vlan_id} removed from {ip}\n{result.stdout}")
            else:
                results.append(f"Failed on {ip}\n{result.stderr}")

        return "\n".join(results)

    except Exception as e:
        return str(e)

@tool
def list_vlans(user_input: str) -> str:
    """
    List all VLANs from switches
    """

    ip_pattern = r"(?:\d{1,3}\.){3}\d{1,3}"
    ips = list(set(re.findall(ip_pattern, user_input)))

    cred_match = re.search(
        r"creds?\s*(?:are|=)?\s*([\w\-]+)\/([\w@\!\#\$%\^\&\*\(\)\-]+)",
        user_input
    )

    username = cred_match.group(1) if cred_match else "admin"
    password = cred_match.group(2) if cred_match else "admin"

    results = []

    for ip in ips:

        cmd = [
            "ansible",
            ip,
            "-i",
            f"{ip},",
            "-m",
            "shell",
            "-a",
            "show vlan brief",
            "-e",
            f"ansible_user={username} ansible_password={password} ansible_become=true ansible_become_method=sudo ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout if result.stdout else result.stderr

        results.append(f"\nSwitch {ip} VLANs:\n{output}")

    return "\n".join(results)