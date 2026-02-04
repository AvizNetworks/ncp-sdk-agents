from ncp import tool
import re
import json
import ast

@tool
def create_visualization(traceroute_output: str) -> str:
    """
    Parses traceroute output and generates a High-Fidelity Unicode Topology Map.
    Universal rendering (Web UI + CLI).
    """
    # Defaults
    source_ip = "Unknown"
    target_ip = "Unknown"
    hops = []

    # The raw text we will scan for hops
    raw_text_payload = str(traceroute_output)

    # ---------------------------------------------------------
    # 1. ROBUST DATA PARSING
    # ---------------------------------------------------------
    try:
        data = None
        if isinstance(traceroute_output, dict):
            data = traceroute_output
        else:
            try:
                cleaned = str(traceroute_output).strip()
                data = ast.literal_eval(cleaned)
            except:
                pass

        if isinstance(data, dict):
            if data.get("source_intf"):
                source_ip = data["source_intf"]
            elif data.get("source"):
                source_ip = data["source"]

            if data.get("target"):
                target_ip = data["target"]

            if data.get("raw_output"):
                raw_text_payload = data["raw_output"]
            elif data.get("hops"):
                hops = data["hops"]

    except Exception:
        pass 

    # ---------------------------------------------------------
    # 2. HOP PARSING (Regex)
    # ---------------------------------------------------------
    if not hops:
        lines = raw_text_payload.split('\\n') if '\\n' in raw_text_payload else raw_text_payload.split('\n')
        
        for line in lines:
            match = re.search(r'^\s*(\d+)\s+([\d\.]+)\s+(?:\(([\d\.]+)\)\s+)?([\d\.]+)\s+ms', line)
            if match:
                ip_addr = match.group(3) if match.group(3) else match.group(2)
                hops.append({
                    "hop_number": int(match.group(1)),
                    "ip": ip_addr,
                    "latency": match.group(4)
                })
            
            if target_ip == "Unknown" and "traceroute to" in line:
                tm = re.search(r'traceroute to \S+ \(([\d\.]+)\)', line)
                if tm: target_ip = tm.group(1)

    # ---------------------------------------------------------
    # 3. GENERATE HIGH-FIDELITY UNICODE VISUAL
    # ---------------------------------------------------------
    # This uses box-drawing characters for a "GUI-like" look in text
    
    # Header
    lines = []
    lines.append("```text")  # Use text block to preserve spacing
    lines.append("┌──────────────────────────────────────┐")
    lines.append(f"│  🚀  NETWORK PATH TRACE              │")
    lines.append(f"│      Target: {target_ip:<23} │")
    lines.append("└──────────────────────────────────────┘")
    lines.append("          │")
    
    # Source Node
    src_label = source_ip if source_ip != "Unknown" else "(Initiator)"
    lines.append("          ▼")
    lines.append("┌──────────────────────────────────────┐")
    lines.append("│  🔵  SOURCE                          │")
    lines.append(f"│      IP: {src_label:<27} │")
    lines.append("└──────────────────────────────────────┘")

    # Hops
    if not hops:
        lines.append("          │")
        lines.append("          ▼")
        lines.append("┌──────────────────────────────────────┐")
        lines.append("│  ❌  TRACE FAILED / NO HOPS          │")
        lines.append("└──────────────────────────────────────┘")
    else:
        for i, hop in enumerate(hops):
            ip = hop.get("ip", "N/A")
            latency = hop.get("latency", "N/A")
            
            # Draw Link with Latency
            lines.append("          │")
            if latency != "N/A":
                lines.append(f"          │  ⚡ {latency} ms")
            lines.append("          ▼")
            
            # Determine Node Type
            if ip == target_ip:
                icon = "🟢"
                role = "DESTINATION"
            elif i == 0 and len(hops) > 1:
                icon = "🟡"
                role = "SPINE / GATEWAY"
            else:
                icon = "⚪"
                role = f"HOP {hop.get('hop_number', i+1)}"

            # Draw Node Box
            lines.append("┌──────────────────────────────────────┐")
            lines.append(f"│  {icon}  {role:<27} │")
            lines.append(f"│      IP: {ip:<27} │")
            lines.append("└──────────────────────────────────────┘")

    lines.append("```")
    
    # Add a Markdown Table Summary (Renders nicely in Web UI)
    table = "\n### 📊 Path Summary\n"
    table += "| Hop | Role | IP Address | Latency |\n"
    table += "| :--- | :--- | :--- | :--- |\n"
    table += f"| **Src** | Source | `{src_label}` | - |\n"
    
    for i, hop in enumerate(hops):
        ip = hop.get("ip", "N/A")
        lat = hop.get("latency", "-")
        role = "Hop"
        if ip == target_ip: role = "**Destination**"
        elif i == 0 and len(hops) > 1: role = "Gateway"
        
        table += f"| {hop.get('hop_number', i+1)} | {role} | `{ip}` | **{lat} ms** |\n"

    return "\n".join(lines) + table
