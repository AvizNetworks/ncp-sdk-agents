# tools/inventory.py

# Full Inventory mapped from "AI-Center Engineering (1).pdf"
DEVICE_REGISTRY = {
    # --- SONiC Pod (Linux) ---
    "10.4.6.11": {"name": "sonic-leaf1", "platform": "linux", "user": "admin", "pass": "aviz@123"},
    "10.4.6.12": {"name": "sonic-leaf2", "platform": "linux", "user": "admin", "pass": "aviz@123"},
    "10.4.6.13": {"name": "sonic-spine1", "platform": "linux", "user": "admin", "pass": "aviz@123"},
    "10.4.6.14": {"name": "sonic-spine2", "platform": "linux", "user": "admin", "pass": "aviz@123"},

    # --- Arista Pod (EOS) ---
    "10.4.6.16": {"name": "arista-leaf1", "platform": "arista_eos", "user": "admin", "pass": "aviz@123"},
    "10.4.6.17": {"name": "arista-leaf2", "platform": "arista_eos", "user": "admin", "pass": "aviz@123"},
    "10.4.6.18": {"name": "arista-spine1", "platform": "arista_eos", "user": "admin", "pass": "aviz@123"},
    "10.4.6.19": {"name": "arista-spine2", "platform": "arista_eos", "user": "admin", "pass": "aviz@123"},

    # --- Nexus Pod (NX-OS) ---
    "10.4.6.21": {"name": "nexus-leaf1", "platform": "cisco_nxos", "user": "admin", "pass": "Aviz@123"},
    "10.4.6.22": {"name": "nexus-leaf2", "platform": "cisco_nxos", "user": "admin", "pass": "Aviz@123"},
    "10.4.6.23": {"name": "nexus-spine1", "platform": "cisco_nxos", "user": "admin", "pass": "Aviz@123"},
    "10.4.6.24": {"name": "nexus-spine2", "platform": "cisco_nxos", "user": "admin", "pass": "Aviz@123"},

    # --- Catalyst Pod (IOS-XE) ---
    "10.4.6.26": {"name": "catalyst-leaf1", "platform": "cisco_ios", "user": "admin", "pass": "Aviz@123"},
    "10.4.6.27": {"name": "catalyst-leaf2", "platform": "cisco_ios", "user": "admin", "pass": "Aviz@123"},
    "10.4.6.28": {"name": "catalyst-spine1", "platform": "cisco_ios", "user": "admin", "pass": "Aviz@123"},
    "10.4.6.29": {"name": "catalyst-spine2", "platform": "cisco_ios", "user": "admin", "pass": "Aviz@123"}
}

def get_device_details(query):
    """Resolves IP or Name to a device dictionary with credentials."""
    query = query.lower()
    # Direct IP Lookup
    if query in DEVICE_REGISTRY:
        return {"ip": query, **DEVICE_REGISTRY[query]}
    
    # Name Lookup
    for ip, data in DEVICE_REGISTRY.items():
        if data['name'] == query:
            return {"ip": ip, **data}
    return None

def get_hostname(ip):
    if ip in DEVICE_REGISTRY:
        return DEVICE_REGISTRY[ip]['name']
    return ip
