import json
from typing import Optional
from ncp import tool, Metrics

# Database

# FastAPI
from fastapi.encoders import jsonable_encoder

# Data & ML
import pandas as pd

import json
import requests
import statistics
from datetime import datetime, timedelta


@tool
def network_level_memory_leak_analysis():
    """
    Analyzes all devices in the inventory for memory leaks.
    1. Fetches all devices (filtering for 'available': True).
    2. Checks Global Memory Trend for each.
    3. If trend is 'Increasing', performs Service-Level Deep Dive.
    4. Returns a summary of leaking devices.
    """
    from .agent_mo_tools import BASE_URL_ONES, USERNAME_ONES, PASSWORD_ONES, get_all_devices, get_device_memory_analysis, get_service_memory_stats

    
    BASE_URL = BASE_URL_ONES
    USERNAME = USERNAME_ONES
    PASSWORD = PASSWORD_ONES
    
    # Login
    # (Assuming the simple login helper from previous turn exists)
    login_url = f"{BASE_URL}/api/user/login"
    try:
        auth_resp = requests.post(
            login_url, 
            json={"username": USERNAME, "password": PASSWORD, "extendedExpiry": True}, 
            headers={'Content-Type': 'application/json'}, 
            verify=False
        )
        auth_resp.raise_for_status()
        token = auth_resp.json().get("data", {}).get("token")
    except Exception:
        return json.dumps({"error": "Login failed"})

    # Get Devices
    all_devices = get_all_devices(BASE_URL, token)
    
    if not all_devices:
        return json.dumps({"status": "No devices found"})

    leaking_devices = []
    
    # Iterate
    for mac in all_devices:
        # Step A: Global Check
        global_stats = get_device_memory_analysis(BASE_URL, token, mac, hours=24)
        
        if global_stats.get("verdict") == "Increasing":
            # Step B: Service Check (Deep Dive)
            services = get_service_memory_stats(BASE_URL, token, mac, hours=1)
            
            leaking_devices.append({
                "device_mac": mac,
                "global_trend": global_stats,
                "suspect_services": services
            })

    # Summary Report
    result = {
        "scan_time": datetime.now().isoformat(),
        "devices_scanned": len(all_devices),
        "leaks_detected": len(leaking_devices),
        "details": leaking_devices
    }

    return json.dumps(result, indent=2)


@tool
def device_level_memory_leak_analysis(mac_address, is_catalyst_center_device: Optional[bool] = False, hostname: Optional[str] = None):
    """
    Use this tool to analyze memory leak trends for a specific device.
    1. Logs in.
    2. Fetches 'memUtil' for global trend analysis.
    3. Fetches 'memConsump' for specific service analysis.
    4. Returns combined JSON.
    """
    from .agent_mo_tools import BASE_URL_ONES, USERNAME_ONES, PASSWORD_ONES, get_device_memory_analysis, get_service_memory_stats
    from .catalyst_center_tools import memory_leak_analysis_and_detection_for_catalyst_center_devices

    if is_catalyst_center_device:    
        # Use method memory_leak_analysis_and_detection_for_catalyst_center_devices
        return memory_leak_analysis_and_detection_for_catalyst_center_devices(hostname)
        
    else:
        # Configuration
        BASE_URL = BASE_URL_ONES
        USERNAME = USERNAME_ONES
        PASSWORD = PASSWORD_ONES
        
        # 1. Login
        token = login(BASE_URL, USERNAME, PASSWORD)
        
        if not token:
            return json.dumps({"error": "Authentication failed"})

        # 2. Get Global Trend (using 'memUtil' from API)
        # We use 24 hours for better trend detection
        global_row = get_device_memory_analysis(BASE_URL, token, mac_address, hours=24)
        
        # 3. Get Service Level Analysis (using 'memConsump' from API)
        service_rows = get_service_memory_stats(BASE_URL, token, mac_address, hours=1)
        
        # 4. Construct Final Result
        result = {
            "global_trend": global_row,
            "services": service_rows
        }
        
        return json.dumps(result, indent=4)
    

@tool
def service_level_memory_analysis(device_mac):
    """
    Tool to fetch service-level memory analysis for a specific device.
    """
    from .agent_mo_tools import BASE_URL_ONES, USERNAME_ONES, PASSWORD_ONES, login, get_service_memory_stats
    
    BASE_URL = BASE_URL_ONES
    USERNAME = USERNAME_ONES
    PASSWORD = PASSWORD_ONES
    token = login(BASE_URL, USERNAME, PASSWORD)
    if not token:
        return json.dumps({"error": "Authentication failed"})
    service_rows = get_service_memory_stats(BASE_URL, token, device_mac, hours=1)
    return json.dumps({"device_mac": device_mac, "services": service_rows}, indent=4)