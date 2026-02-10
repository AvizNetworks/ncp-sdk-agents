"""Drift detection and comparison tools for Intent Drift Detector.

This module provides tools for:
1. Comparing intent vs running configuration
2. Generating drift reports in Markdown format
"""

from typing import Dict, Any, List


def compare_intent_vs_running(
    intent_data: Dict[str, Any],
    running_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare parsed intent against running fabric state and identify drifts.
    
    Args:
        intent_data: Parsed intent from parse_intent_yaml
        running_data: Running state from get_complete_fabric_state (NDFC) 
                     or aggregated running configs (ONES FM)
    
    Returns:
        Drift report with mismatches categorized by severity.
    """
    drifts = []
    summary = {
        "total_checks": 0,
        "passed": 0,
        "critical_drifts": 0,
        "major_drifts": 0,
        "minor_drifts": 0
    }
    
    # 1. Check devices
    intended_devices = intent_data.get("device_map", {})
    running_switches = {sw.get("hostName"): sw for sw in running_data.get("switches", [])}
    
    for hostname, intent_device in intended_devices.items():
        summary["total_checks"] += 1
        if hostname not in running_switches:
            drifts.append({
                "type": "device",
                "severity": "critical",
                "device": hostname,
                "field": "existence",
                "intended": "present",
                "running": "missing",
                "message": f"Device {hostname} not found in fabric"
            })
            summary["critical_drifts"] += 1
        else:
            summary["passed"] += 1
            running_sw = running_switches[hostname]
            
            # Check role
            if intent_device.get("role"):
                summary["total_checks"] += 1
                if intent_device["role"].lower() != running_sw.get("switchRole", "").lower():
                    drifts.append({
                        "type": "device",
                        "severity": "major",
                        "device": hostname,
                        "field": "role",
                        "intended": intent_device["role"],
                        "running": running_sw.get("switchRole"),
                        "message": f"Device role mismatch"
                    })
                    summary["major_drifts"] += 1
                else:
                    summary["passed"] += 1
    
    # 2. Check interfaces
    running_interfaces = running_data.get("interfaces_by_switch", {})
    intended_interfaces = intent_data.get("interface_map", {})
    
    for device, interfaces in intended_interfaces.items():
        device_running_intfs = {i.get("ifName"): i for i in running_interfaces.get(device, [])}
        
        for intf_name, intent_intf in interfaces.items():
            summary["total_checks"] += 1
            
            if intf_name not in device_running_intfs:
                drifts.append({
                    "type": "interface",
                    "severity": "major",
                    "device": device,
                    "interface": intf_name,
                    "field": "existence",
                    "intended": "configured",
                    "running": "not found",
                    "message": f"Interface {intf_name} not found on {device}"
                })
                summary["major_drifts"] += 1
                continue
            
            running_intf = device_running_intfs[intf_name]
            summary["passed"] += 1
            
            # Check admin state
            if intent_intf.get("admin_state"):
                summary["total_checks"] += 1
                if intent_intf["admin_state"].lower() != running_intf.get("adminStatusStr", "").lower():
                    drifts.append({
                        "type": "interface",
                        "severity": "critical",
                        "device": device,
                        "interface": intf_name,
                        "field": "admin_state",
                        "intended": intent_intf["admin_state"],
                        "running": running_intf.get("adminStatusStr"),
                        "message": f"Admin state mismatch on {device} {intf_name}"
                    })
                    summary["critical_drifts"] += 1
                else:
                    summary["passed"] += 1
            
            # Check MTU
            if intent_intf.get("mtu"):
                summary["total_checks"] += 1
                if intent_intf["mtu"] != running_intf.get("mtu"):
                    drifts.append({
                        "type": "interface",
                        "severity": "major",
                        "device": device,
                        "interface": intf_name,
                        "field": "mtu",
                        "intended": intent_intf["mtu"],
                        "running": running_intf.get("mtu"),
                        "message": f"MTU mismatch on {device} {intf_name}"
                    })
                    summary["major_drifts"] += 1
                else:
                    summary["passed"] += 1
            
            # Check mode
            if intent_intf.get("mode"):
                summary["total_checks"] += 1
                running_mode = running_intf.get("mode") or ""
                if intent_intf["mode"].lower() != running_mode.lower():
                    drifts.append({
                        "type": "interface",
                        "severity": "major",
                        "device": device,
                        "interface": intf_name,
                        "field": "mode",
                        "intended": intent_intf["mode"],
                        "running": running_mode or "unknown",
                        "message": f"Interface mode mismatch on {device} {intf_name}"
                    })
                    summary["major_drifts"] += 1
                else:
                    summary["passed"] += 1
            
            # Check IP address
            if intent_intf.get("ip_address"):
                summary["total_checks"] += 1
                if intent_intf["ip_address"] != running_intf.get("ipAddress"):
                    drifts.append({
                        "type": "interface",
                        "severity": "critical",
                        "device": device,
                        "interface": intf_name,
                        "field": "ip_address",
                        "intended": intent_intf["ip_address"],
                        "running": running_intf.get("ipAddress"),
                        "message": f"IP address mismatch on {device} {intf_name}"
                    })
                    summary["critical_drifts"] += 1
                else:
                    summary["passed"] += 1
    
    # Calculate compliance percentage
    if summary["total_checks"] > 0:
        summary["compliance_percentage"] = round(
            (summary["passed"] / summary["total_checks"]) * 100, 2
        )
    else:
        summary["compliance_percentage"] = 100.0
    
    return {
        "success": True,
        "summary": summary,
        "drifts": drifts,
        "drift_count": len(drifts)
    }


def generate_drift_report_markdown(drift_result: Dict[str, Any]) -> str:
    """
    Generate a formatted Markdown drift report from comparison results.
    
    Args:
        drift_result: Result from compare_intent_vs_running
    
    Returns:
        Formatted Markdown report string.
    """
    summary = drift_result.get("summary", {})
    drifts = drift_result.get("drifts", [])
    
    report = []
    report.append("# Intent Drift Detection Report")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append("| Metric | Value |")
    report.append("|--------|-------|")
    report.append(f"| Total Checks | {summary.get('total_checks', 0)} |")
    report.append(f"| Passed | {summary.get('passed', 0)} |")
    report.append(f"| Critical Drifts | {summary.get('critical_drifts', 0)} |")
    report.append(f"| Major Drifts | {summary.get('major_drifts', 0)} |")
    report.append(f"| Minor Drifts | {summary.get('minor_drifts', 0)} |")
    report.append(f"| **Compliance** | **{summary.get('compliance_percentage', 0)}%** |")
    report.append("")
    
    if not drifts:
        report.append("## ✅ No Drifts Detected")
        report.append("")
        report.append("All intended configurations match the running state.")
    else:
        report.append("## ❌ Drifts Detected")
        report.append("")
        
        # Group by severity
        critical = [d for d in drifts if d.get("severity") == "critical"]
        major = [d for d in drifts if d.get("severity") == "major"]
        minor = [d for d in drifts if d.get("severity") == "minor"]
        
        if critical:
            report.append("### 🔴 Critical Drifts")
            report.append("")
            report.append("| Device | Type | Field | Intended | Running |")
            report.append("|--------|------|-------|----------|---------|")
            for d in critical:
                device = d.get("device", "")
                intf = d.get("interface", "")
                location = f"{device}/{intf}" if intf else device
                report.append(
                    f"| {location} | {d.get('type')} | {d.get('field')} | "
                    f"`{d.get('intended')}` | `{d.get('running')}` |"
                )
            report.append("")
        
        if major:
            report.append("### 🟠 Major Drifts")
            report.append("")
            report.append("| Device | Type | Field | Intended | Running |")
            report.append("|--------|------|-------|----------|---------|")
            for d in major:
                device = d.get("device", "")
                intf = d.get("interface", "")
                location = f"{device}/{intf}" if intf else device
                report.append(
                    f"| {location} | {d.get('type')} | {d.get('field')} | "
                    f"`{d.get('intended')}` | `{d.get('running')}` |"
                )
            report.append("")
        
        if minor:
            report.append("### 🟡 Minor Drifts")
            report.append("")
            report.append("| Device | Type | Field | Intended | Running |")
            report.append("|--------|------|-------|----------|---------|")
            for d in minor:
                device = d.get("device", "")
                intf = d.get("interface", "")
                location = f"{device}/{intf}" if intf else device
                report.append(
                    f"| {location} | {d.get('type')} | {d.get('field')} | "
                    f"`{d.get('intended')}` | `{d.get('running')}` |"
                )
            report.append("")
    
    report.append("---")
    report.append("*Report generated by Intent Drift Detector*")
    
    return "\n".join(report)
