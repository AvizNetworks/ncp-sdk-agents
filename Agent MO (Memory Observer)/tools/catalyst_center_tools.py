from typing import Optional
from ncp import tool, Metrics
from datetime import datetime, date

@tool
def get_catalyst_center_devices(dataconnector_type: Optional[str] = "Catalyst Center"):
    """
    Fetches devices that are part of Catalyst Center from Metrics.
    """
    metrics = Metrics()

    def json_safe(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return obj

    try:
        kwargs = {}
        if dataconnector_type:
            kwargs["dataconnector_type"] = dataconnector_type

        devices = metrics.get_devices(**kwargs)

        # Make every device JSON-safe
        safe_devices = [
            {k: json_safe(v) for k, v in device.items()}
            for device in devices
        ]

        return {
            "devices": safe_devices,
            "total_count": len(safe_devices)
        }
    finally:
        metrics.close()



@tool
def memory_leak_analysis_and_detection_for_catalyst_center_devices(hostname: Optional[str] = None):
    """
    Analyzes memory leak trends for devices in Catalyst Center.
    """
    import pandas as pd
    from datetime import datetime, date
    import pymannkendall as mk

    metrics = Metrics()

    try:
        if not hostname:
            # Fetch all Catalyst Center devices
            devices_resp = get_catalyst_center_devices(dataconnector_type="Catalyst Center")
            devices = devices_resp.get("devices", [])

        else:
            devices = [{"hostname": hostname}]

        leaking_devices = []
        for device in devices:
            hostname = device.get("hostname")
            if not hostname:
                continue

            try:
                mem_stats = metrics.get_memory_utilization(
                    hostname=hostname,
                    hours=24
                )

                if not mem_stats or len(mem_stats) < 10:
                    continue

                df = pd.DataFrame(mem_stats)

                # Ensure numeric + JSON-safe timestamps
                df["avg_util"] = pd.to_numeric(df["avg_util"], errors="coerce")
                if "ts" in df.columns:
                    df["ts"] = df["ts"].astype(str)

                df = df.dropna(subset=["avg_util"])
                if len(df) < 10:
                    continue

                mk_result = mk.original_test(df["avg_util"])

                if mk_result.trend == "increasing":
                    leaking_devices.append({
                        "hostname": hostname,
                        "p_value": round(float(mk_result.p), 4),
                        "avg_util": round(float(df["avg_util"].mean()), 2),
                        "max_util": round(float(df["avg_util"].max()), 2)
                    })

            except Exception:
                continue

        return {
            "scan_time": datetime.now().isoformat(),
            "devices_scanned": len(devices),
            "leaks_detected": len(leaking_devices),
            "details": leaking_devices
        }
    finally:
        metrics.close()


@tool
def get_memory_utilization_for_catalyst_center_devices(hostname: Optional[str] = None):
    """
    Fetches memory utilization data for Catalyst Center devices.
    """
    import pandas as pd
    from datetime import datetime, date

    metrics = Metrics()

    try:
        if not hostname:
            # Fetch all Catalyst Center devices
            devices_resp = get_catalyst_center_devices(dataconnector_type="Catalyst Center")
            devices = devices_resp.get("devices", [])

        else:
            devices = [{"hostname": hostname}]

        utilization_data = []
        for device in devices:
            hostname = device.get("hostname")
            if not hostname:
                continue

            try:
                mem_stats = metrics.get_memory_utilization(
                    hostname=hostname,
                    hours=24
                )

                if not mem_stats:
                    continue

                df = pd.DataFrame(mem_stats)

                # Ensure numeric + JSON-safe timestamps
                df["avg_util"] = pd.to_numeric(df["avg_util"], errors="coerce")
                if "ts" in df.columns:
                    df["ts"] = df["ts"].astype(str)

                df = df.dropna(subset=["avg_util"])
                if df.empty:
                    continue

                utilization_data.append({
                    "hostname": hostname,
                    "memory_utilization": df.to_dict(orient="records")
                })

            except Exception:
                continue

        return {
            "scan_time": datetime.now().isoformat(),
            "devices_scanned": len(devices),
            "utilization_data": utilization_data
        }
    finally:
        metrics.close()
       
