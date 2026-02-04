"""Tools for Agent Mo."""

# ncp (project / external)
import json
from ncp import tool

# Database

# FastAPI
from fastapi.encoders import jsonable_encoder

# Data & ML
import pandas as pd

import json
import requests
import statistics
from datetime import datetime, timedelta


# Since ncp-db is not available for SDK, Using Harcoded value for ONES-Collector.
# SWSS, BGP, ONES-Agent, SYNCd, etc are not capturing in metrics DB, need to make use of API, thats why using creds.
# Ones NCP_DB allow for SDK or we started capturing these services in metrics DB, we can remove this hardcoding.
BASE_URL_ONES = 'Your_ONES_SERVER_URL' 
USERNAME_ONES = "YOUR_ONES_USERNAME"
PASSWORD_ONES = "YOUR_ONES_PASSWORD"



# initializr metrics client

@tool
def get_device_info():
    """Fetch device information using API."""
    BASE_URL = BASE_URL_ONES
    USERNAME = USERNAME_ONES
    PASSWORD = PASSWORD_ONES
    try:
        # Authenticate
        url = f"{BASE_URL}/api/user/login"
        headers = {'Content-Type': 'application/json', 'accept': 'application/json'}
        payload = {"username": USERNAME, "password": PASSWORD, "extendedExpiry": True}
        resp = requests.post(url, json=payload, headers=headers, verify=False)
        resp.raise_for_status()
        token = resp.json().get("data", {}).get("token")
        if not token:
            return {"error": "Authentication failed"}

        # Fetch device list
        device_url = f"{BASE_URL}/api/health/DeviceList"
        headers = {"authorization": token, "accept": "application/json"}
        device_resp = requests.get(device_url, headers=headers, verify=False)
        device_resp.raise_for_status()
        device_list = device_resp.json()
        if not isinstance(device_list, list):
            device_list = device_list.get('data', [])
        return jsonable_encoder({"device_info": device_list})
    except Exception as e:
        return {"error": str(e)}

@tool
def get_memory_utilization():
    """Fetch device memory utilization using API (last 24 hours, limit 100)."""
    BASE_URL = BASE_URL_ONES
    USERNAME = USERNAME_ONES
    PASSWORD = PASSWORD_ONES
    try:
        # Authenticate
        url = f"{BASE_URL}/api/user/login"
        headers = {'Content-Type': 'application/json', 'accept': 'application/json'}
        payload = {"username": USERNAME, "password": PASSWORD, "extendedExpiry": True}
        resp = requests.post(url, json=payload, headers=headers, verify=False)
        resp.raise_for_status()
        token = resp.json().get("data", {}).get("token")
        if not token:
            return {"error": "Authentication failed"}

        # Fetch all devices
        devices = get_all_devices(BASE_URL, token)
        results = []
        for mac in devices[:100]:  # Limit to 100 devices
            stats = get_device_memory_analysis(BASE_URL, token, mac, hours=24)
            results.append(stats)
        return jsonable_encoder({"memory_utilization_data": results})
    except Exception as e:
        return {"error": str(e)}


def login(base_url=BASE_URL_ONES, username=USERNAME_ONES, password=PASSWORD_ONES):
    """Authenticates with the API."""
    url = f"{base_url}/api/user/login"
    headers = {'Content-Type': 'application/json', 'accept': 'application/json'}
    payload = {"username": username, "password": password, "extendedExpiry": True}
    
    try:
        response = requests.post(url, json=payload, headers=headers, verify=False)
        response.raise_for_status()
        return response.json().get("data", {}).get("token")
    except Exception as e:
        print(f"Login failed: {e}")
        return None


def get_all_devices(base_url, token):
    """
    Fetches the list of all available devices from the inventory.
    Adapts to the schema: List of Dicts, using 'macaddress' key.
    """
    if not token:
        return []

    headers = {"authorization": token, "accept": "application/json"}
    url = f"{base_url}/api/health/DeviceList" 

    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        
        # PARSING ADJUSTMENT: Response is a direct list, not {"data": [...]}
        data_list = response.json()
        
        if not isinstance(data_list, list):
            # Fallback in case it's wrapped
            data_list = data_list.get('data', [])

        # Extract MAC addresses using the correct lowercase key 'macaddress'
        # We also filter for 'available': True to avoid querying decommissioned devices
        devices = [
            d.get('macaddress') 
            for d in data_list 
            if d.get('macaddress') and d.get('available') is True
        ]
        
        # limit 20
        return devices[:30]
    except Exception as e:
        print(f"Error fetching device inventory: {e}")
        return []


    
# --- 1. Helper: Global Trend Analysis ---
def get_device_memory_analysis(base_url, token, device_mac, hours=24):
    """
    Fetches global memory metrics (memUtil) and performs Mann-Kendall trend analysis.
    """
    import pymannkendall as mk
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=hours)
    fmt = "%Y-%m-%d %H:%M:%S"
    
    headers = {"authorization": token, "accept": "application/json"}
    filter_params = {
        "fromDate": start_dt.strftime(fmt),
        "toDate": end_dt.strftime(fmt),
        "windowSize": "1 hour",
        "deviceAddress": device_mac,
        "activeTab": "system"
    }

    try:
        url = f"{base_url}/api/health/mega"
        response = requests.get(url, headers=headers, params={"filter": json.dumps(filter_params)}, verify=False)
        # We don't raise status here to allow the loop to continue for other devices even if one fails
        if response.status_code != 200:
            return {"verdict": "Fetch Error", "p_value": 1.0, "avg_util": 0}

        api_data = response.json()
        mem_util_list = api_data.get("memUtil", [])
        
        if not mem_util_list or "data" not in mem_util_list[0]:
            return {"verdict": "Insufficient Data", "p_value": 1.0, "avg_util": 0}

        raw_data = mem_util_list[0]["data"] 
        df = pd.DataFrame(raw_data, columns=['time', 'avg_util'])

        # Mann-Kendall Test
        if len(df) < 10:
             trend, p_value = "Insufficient Data", 1.0
        else:
            mk_result = mk.original_test(df['avg_util'])
            trend, p_value = mk_result.trend, round(mk_result.p, 4)

        verdict = "Increasing" if trend == 'increasing' else ("Decreasing" if trend == 'decreasing' else "Stable")

        return {
            "device_mac": device_mac,
            "p_value": p_value,
            "verdict": verdict,
            "avg_util": float(df['avg_util'].mean()),
            "max_util": float(df['avg_util'].max())
        }
    except Exception as e:
        return {"verdict": "Error", "details": str(e), "avg_util": 0}

# --- 2. Helper: Service Stats ---
def get_service_memory_stats(base_url, token, device_mac, hours=1):
    """Fetches granular memory consumption for specific services."""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=hours)
    fmt = "%Y-%m-%d %H:%M:%S"
    
    headers = {"authorization": token, "accept": "application/json"}
    filter_params = {
        "fromDate": start_dt.strftime(fmt),
        "toDate": end_dt.strftime(fmt),
        "windowSize": "1 hour",
        "deviceAddress": device_mac,
        "activeTab": "system"
    }
    
    try:
        url = f"{base_url}/api/health/mega"
        response = requests.get(url, headers=headers, params={"filter": json.dumps(filter_params)}, verify=False)
        if response.status_code != 200: return []
        
        api_data = response.json()
        results = []
        target_services = ["swss", "bgp", "ones-agent", "syncd", "redis"] # Expanded list
        mem_data_list = api_data.get("memConsump", [])

        for service_entry in mem_data_list:
            service_name = service_entry.get("name", "")
            # Flexible matching
            if any(t in service_name.lower() for t in target_services):
                data_points = service_entry.get("data", [])
                if not data_points: continue

                values = [p[1] for p in data_points]
                growth = values[-1] - values[0]
                
                # Only report services that are actually growing or using significant memory
                if growth > 0 or statistics.mean(values) > 5.0:
                    results.append({
                        "service": service_name,
                        "avg_util": round(statistics.mean(values), 2),
                        "growth_trend": round(growth, 2)
                    })
        return results
    except Exception:
        return []
