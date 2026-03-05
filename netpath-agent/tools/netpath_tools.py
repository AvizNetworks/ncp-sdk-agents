# tools/netpath_tools.py
import subprocess
import socket
import re
import paramiko
import sqlite3
import time
from datetime import datetime
from ncp import tool
from .inventory import get_device_details, get_hostname, DEVICE_REGISTRY
from .database import (
    init_db, 
    save_trace_data, 
    save_ping_data, 
    fetch_recent_hops, 
    save_mesh_result, 
    fetch_mesh_data,
    save_remote_traceroute,
    DB_PATH
)

init_db()

# --- HELPER: SSH Connection with Legacy Support ---
def get_ssh_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client

def connect_ssh(client, ip, user, password):
    """
    Connects with enhanced compatibility for older Cisco devices.
    """
    try:
        # Try standard connection first
        client.connect(
            ip, 
            username=user, 
            password=password, 
            timeout=5, 
            look_for_keys=False, 
            allow_agent=False
        )
        return True
    except Exception:
        # Retry with legacy options if standard fails
        try:
            # Note: Specific disabled_algorithms syntax depends on Paramiko version
            # This generic retry often clears transport layer issues
            client.connect(
                ip, 
                username=user, 
                password=password, 
                timeout=10, 
                look_for_keys=False, 
                allow_agent=False,
                disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']}
            )
            return True
        except Exception as e:
            raise e

# --- HELPER: SSH Check ---
def _ssh_check(ip, user, password):
    client = get_ssh_client()
    try:
        connect_ssh(client, ip, user, password)
        client.close()
        return True, "SSH Access Successful"
    except Exception as e:
        return False, str(e)

# --- HELPER: System Traceroute (Agent -> Target) ---
def _run_system_traceroute(target):
    cmd = ["traceroute", "-n", "-w", "1", "-m", "10", target]
    hops = []
    try:
        process = subprocess.run(cmd, capture_output=True, text=True)
        output = process.stdout + "\n" + process.stderr
        for line in output.split('\n'):
            if not line.strip() or line.startswith("traceroute"): continue
            parts = line.split()
            if not parts or not parts[0].isdigit(): continue
            index = int(parts[0])
            ip = "*"
            rtts = []
            for part in parts[1:]:
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", part):
                    ip = part
                    break
            for part in parts:
                try:
                    val = float(part)
                    if val < 1000: rtts.append(val)
                except ValueError: continue
            avg_rtt = sum(rtts) / len(rtts) if rtts else 0
            loss = 100 if ip == "*" else 0
            hops.append({"index": index, "ip": ip, "rtt": avg_rtt, "loss": loss})

    except Exception as e:
        print(f"⚠️ Traceroute command failed: {e}")

    # Fallback for container without permissions or missing binary (0 hops detected)
    if not hops:
        ping_stats = _run_system_ping(target)
        hops.append({
            "index": 1,
            "ip": target,
            "rtt": ping_stats["avg_rtt"] if ping_stats["loss"] < 100 else 0,
            "loss": ping_stats["loss"]
        })

    return hops

# --- HELPER: System Ping (Agent -> Target) ---
def _run_system_ping(target):
    cmd = ["ping", "-c", "3", target]
    stats = {"avg_rtt": 0, "loss": 100, "jitter": 0}
    ping_success = False

    try:
        process = subprocess.run(cmd, capture_output=True, text=True)
        output = process.stdout + "\n" + process.stderr

        if process.returncode == 0 and "100% packet loss" not in output:
            ping_success = True
            loss_match = re.search(r"(\d+)% packet loss", output)
            if loss_match: stats["loss"] = float(loss_match.group(1))
            rtt_match = re.search(r"min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+)", output)
            if rtt_match:
                stats["avg_rtt"] = float(rtt_match.group(2))
                stats["jitter"] = float(rtt_match.group(4))

    except Exception as e:
        print(f"⚠️ Ping command failed: {e}")

    if not ping_success:
        # TCP Fallback if ICMP is dropped, blocked, or missing in containers
        rtts = []
        for _ in range(3):
            start = time.time()
            try:
                with socket.create_connection((target, 22), timeout=1.0):
                    pass
                rtts.append((time.time() - start) * 1000)
            except OSError:
                pass
        if rtts:
            stats["loss"] = (3 - len(rtts)) / 3.0 * 100.0
            stats["avg_rtt"] = round(sum(rtts) / len(rtts), 3)
            stats["jitter"] = round(max(rtts) - min(rtts), 3) if len(rtts) > 1 else 0.0

    return stats

# --- TOOLS ---

@tool
def check_device_health(target_name: str) -> str:
    """Check device health by running ping and SSH connectivity tests."""
    device = get_device_details(target_name)
    if not device: return f"Device '{target_name}' not found."

    ping_stats = _run_system_ping(device['ip'])
    status = f"Health Report for **{device['name']}** ({device['ip']}):\n- Ping Loss: {ping_stats['loss']}%\n"
    
    is_ssh_up, msg = _ssh_check(device['ip'], device['user'], device['pass'])
    status += f"- SSH Access: {'✅ UP' if is_ssh_up else '🔴 DOWN (' + msg + ')'}"
    return status

@tool
def collect_network_data(target: str) -> str:
    """Runs diagnostics and saves to DB."""
    device = get_device_details(target)
    target_ip = device['ip'] if device else target
    
    hops = _run_system_traceroute(target_ip)
    stats = _run_system_ping(target_ip)
    
    save_trace_data(target_ip, hops)
    save_ping_data(target_ip, stats)
    
    details = f"\n**Path Trace to {target} ({target_ip}):**\n"
    if hops:
        details += "| Hop | IP | RTT (ms) | Loss % |\n|---|---|---|---|\n"
        for h in hops:
            details += f"| {h['index']} | {h['ip']} | {h['rtt']:.2f} | {h['loss']} |\n"
    else:
        details += "(No hops recorded - check connection)\n"

    return f"✅ **Collection Complete**\n- **Ping Loss:** {stats['loss']}%\n- **Avg Latency:** {stats['avg_rtt']} ms\n{details}"

@tool
def analyze_path_topology(target: str) -> str:
    """Analyze the network path topology for a target device using stored trace data."""
    device = get_device_details(target)
    target_ip = device['ip'] if device else target
    
    raw = fetch_recent_hops(target_ip)
    if not raw: return "No data found. Please run 'collect_network_data' first."
    
    import networkx as nx
    G = nx.DiGraph()
    runs = {}
    for row in raw:
        run_id = row['run_id']
        if run_id not in runs: runs[run_id] = []
        runs[run_id].append(row)

    for run_id, hops in runs.items():
        hops.sort(key=lambda x: x["hop_index"])
        for i in range(len(hops) - 1):
            src = hops[i]
            dst = hops[i+1]
            if src['ip_address'] == "*" or dst['ip_address'] == "*": continue
            G.add_edge(src['ip_address'], dst['ip_address'], latency=max(0, dst['rtt_ms'] - src['rtt_ms']), loss=dst['loss_pct'])

    issues = []
    for u, v, d in G.edges(data=True):
        if d['loss'] > 0: issues.append(f"❌ Loss {get_hostname(u)}->{get_hostname(v)}")

    return f"📊 Topology: {len(G.nodes)} Nodes. Issues: {', '.join(issues) if issues else 'None'}."

@tool
def list_inventory() -> str:
    """List all devices in the network inventory with their names and IPs."""
    return "\n".join([f"- {d['name']} ({ip})" for ip, d in DEVICE_REGISTRY.items()])

@tool
def show_database_stats() -> str:
    """Show recent ping stats and trace runs from the internal database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        output = ["📊 **Internal Database Dump**"]
        
        rows = cursor.execute("SELECT target, packet_loss, timestamp FROM ping_stats ORDER BY id DESC LIMIT 5").fetchall()
        output.append("\n**Recent Ping Stats:**")
        if rows:
            for r in rows:
                output.append(f"- Target: {r['target']} | Loss: {r['packet_loss']}% | Time: {r['timestamp']}")
        else:
            output.append("(No ping data found)")

        rows = cursor.execute("SELECT id, target, timestamp FROM trace_runs ORDER BY id DESC LIMIT 5").fetchall()
        output.append("\n**Recent Trace Runs:**")
        if rows:
            for r in rows:
                output.append(f"- Run ID: {r['id']} | Target: {r['target']} | Time: {r['timestamp']}")
        else:
            output.append("(No trace data found)")
            
        conn.close()
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Database Error: {e}"

@tool
def run_ping_mesh() -> str:
    """
    Full Mesh Ping Test: Uses the registry to SSH into every device
    and ping every other device. Handles Cisco/Linux syntax diffs.
    """
    results = []
    timestamp = datetime.now().isoformat()
    status_msg = ["🚀 **Starting Multi-Vendor Fabric Ping Mesh...**"]
    
    # Iterate over IPs from registry
    target_ips = list(DEVICE_REGISTRY.keys())

    for src_ip in target_ips:
        src = DEVICE_REGISTRY[src_ip]
        src_name = src['name']
        
        try:
            # 1. SSH into Source using Enhanced Logic
            client = get_ssh_client()
            connect_ssh(client, src_ip, src['user'], src['pass'])
            
            for dst_ip in target_ips:
                if src_ip == dst_ip: continue
                dst_name = DEVICE_REGISTRY[dst_ip]['name']

                # 2. Determine Command based on 'platform'
                platform = src.get('platform', 'linux')
                cmd = f"ping -c 1 -W 1 {dst_ip}" # Default (Linux/Sonic/Arista)
                
                if platform == 'cisco_nxos':
                    cmd = f"ping {dst_ip} count 1"
                elif platform == 'cisco_ios':
                    cmd = f"ping {dst_ip} repeat 1"

                # 3. Execute
                stdin, stdout, stderr = client.exec_command(cmd, timeout=5)
                output = stdout.read().decode()
                
                # 4. Parse Result
                loss = 100.0
                rtt = 0.0
                
                # Linux/EOS pattern
                if "0% packet loss" in output:
                    loss = 0.0
                    match = re.search(r"time=([\d\.]+)", output)
                    if match: rtt = float(match.group(1))
                
                # Cisco pattern (!!!!! or Success rate is 100)
                elif "Success rate is 100 percent" in output or "!!!!!" in output:
                    loss = 0.0
                    match = re.search(r"min/avg/max = \d+/(\d+)/", output)
                    if match: rtt = float(match.group(1))

                results.append({
                    "timestamp": timestamp,
                    "src": src_name,
                    "dst": dst_name,
                    "loss": loss,
                    "rtt": rtt
                })
                
            client.close()
            status_msg.append(f"✅ {src_name} ({src.get('platform', 'linux')}) checks complete.")
            
        except Exception as e:
            status_msg.append(f"❌ Connection failed to {src_name}: {e}")
            for dst_ip in target_ips:
                if src_ip == dst_ip: continue
                results.append({"timestamp": timestamp, "src": src_name, "dst": DEVICE_REGISTRY[dst_ip]['name'], "loss": 100.0, "rtt": 0.0})

            # Capture timestamp at the END of the run so it matches "Last Updated" expectations
    final_timestamp = datetime.now().isoformat()
    # Update timestamps in the results list
    for r in results:
        r['timestamp'] = final_timestamp

    save_mesh_result(results)
    return "\n".join(status_msg) + f"\n\n📊 **Mesh Complete.** Saved {len(results)} records."

@tool
def run_full_network_scan() -> str:
    """
    Auto-Discovery Mode:
    Iterates through the ENTIRE registry and runs 'collect_network_data' on everything.
    If a device fails, it is explicitly recorded as 100% loss so it appears on the Topology.
    """
    results = []
    target_ips = list(DEVICE_REGISTRY.keys())
    results.append(f"🚀 **Starting Full Network Scan on {len(target_ips)} devices...**\n")
    
    for ip in target_ips:
        name = DEVICE_REGISTRY[ip]['name']
        try:
            # Attempt Scan
            hops = _run_system_traceroute(ip)
            stats = _run_system_ping(ip)
            
            # Save Success
            save_trace_data(ip, hops)
            save_ping_data(ip, stats)
            
            # Check if ping actually failed despite no exception
            if stats['loss'] == 100:
                 results.append(f"⚠️ **{name}**: 100% Loss (Unreachable)")
            else:
                 results.append(f"✅ **{name}**: Loss {stats['loss']}% | RTT {stats['avg_rtt']}ms")
            
        except Exception as e:
            # --- THE FIX: Force Record Failure ---
            error_msg = str(e)
            
            # 1. Save 100% Loss Ping
            failed_stats = {"avg_rtt": 0, "loss": 100, "jitter": 0}
            save_ping_data(ip, failed_stats)
            
            # 2. Save "Dummy" Hop (Direct link to target with 100% loss)
            # This ensures the node appears red on the graph
            failed_hops = [{"index": 1, "ip": ip, "rtt": 0, "loss": 100}]
            save_trace_data(ip, failed_hops)
            
            results.append(f"❌ **{name}**: Failed ({error_msg}) - Marked as Down")

    return "\n".join(results) + "\n\n🏁 **Full Scan Complete.** Check Dashboard for Red/Green status."

@tool
def get_ping_mesh_results() -> str:
    """Retrieve the latest ping mesh results from the database with full details including source device, destination device, RTT latency in ms, and packet loss percentage. Use this to get structured mesh data for generating charts and visualizations."""
    data = fetch_mesh_data(latest_only=True)
    if not data:
        return "No mesh data found. Please run a ping mesh first using 'run_ping_mesh'."

    output = ["📊 **Ping Mesh Results (Latest Run)**\n"]
    output.append(f"**Timestamp:** {data[0]['timestamp']}")
    output.append(f"**Total Paths:** {len(data)}\n")
    output.append("| Source Device | Destination Device | RTT (ms) | Packet Loss (%) |")
    output.append("|---|---|---|---|")
    for r in data:
        output.append(f"| {r['source_device']} | {r['dest_device']} | {r['rtt_ms']} | {r['packet_loss']} |")

    reachable = sum(1 for r in data if r['packet_loss'] == 0)
    unreachable = len(data) - reachable
    output.append(f"\n**Summary:** {reachable} reachable, {unreachable} unreachable out of {len(data)} paths.")

    return "\n".join(output)

@tool
def get_ping_mesh_history(source_device: str, dest_device: str) -> str:
    """Retrieve ALL historical ping mesh results for a specific source-to-destination device pair across all past mesh runs. Returns timestamped RTT and packet loss data suitable for plotting line charts and trend analysis. Use this when the user wants to see latency or loss trends over time for a specific path."""
    data = fetch_mesh_data(
        source_device=source_device,
        dest_device=dest_device,
        latest_only=False,
        limit=500,
    )
    if not data:
        return (
            f"No historical mesh data found for {source_device} → {dest_device}. "
            f"Run 'run_ping_mesh' multiple times to build trend data for this path."
        )

    output = [f"📈 **Historical Mesh Data: {source_device} → {dest_device}**\n"]
    output.append(f"**Data Points:** {len(data)}\n")
    output.append("| Timestamp | RTT (ms) | Packet Loss (%) |")
    output.append("|---|---|---|")
    for r in data:
        output.append(f"| {r['timestamp']} | {r['rtt_ms']} | {r['packet_loss']} |")

    return "\n".join(output)

@tool
def run_remote_traceroute(device_name: str, target: str) -> str:
    """
    SSH into a device from the AI Center inventory and run a traceroute to
    a given target (e.g. 8.8.8.8). Returns structured hop-by-hop data
    (hop number, IP address, RTT in ms) suitable for charting.
    Use this when the user wants to trace the route FROM a specific network
    device TO an external or internal destination.
    """
    device = get_device_details(device_name)
    if not device:
        return f"Device '{device_name}' not found in inventory. Use list_inventory to see available devices."

    platform = device.get('platform', 'linux')

    # Build the traceroute command based on platform
    if platform == 'linux':
        cmd = f"traceroute -n -w 2 -m 15 {target}"
    elif platform in ('cisco_nxos', 'cisco_ios', 'arista_eos'):
        cmd = f"traceroute {target}"
    else:
        cmd = f"traceroute -n -w 2 -m 15 {target}"

    try:
        client = get_ssh_client()
        connect_ssh(client, device['ip'], device['user'], device['pass'])

        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        raw_output = stdout.read().decode()
        client.close()
    except Exception as e:
        return f"SSH connection to {device['name']} ({device['ip']}) failed: {e}"

    # Parse the traceroute output into structured hops
    hops = []
    for line in raw_output.split('\n'):
        line = line.strip()
        if not line or line.lower().startswith("traceroute") or line.lower().startswith("type escape"):
            continue
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue

        hop_index = int(parts[0])
        hop_ip = "*"
        rtts = []

        # Extract IP address
        for part in parts[1:]:
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", part):
                hop_ip = part
                break

        # Extract RTT values (numeric values < 1000 that look like ms)
        for part in parts:
            try:
                val = float(part)
                if val < 1000:
                    rtts.append(val)
            except ValueError:
                continue

        avg_rtt = round(sum(rtts) / len(rtts), 2) if rtts else 0.0
        hops.append({"hop": hop_index, "ip": hop_ip, "rtt": avg_rtt})

    if not hops:
        return (
            f"Traceroute from {device['name']} to {target} returned no parseable hops.\n"
            f"Raw output:\n{raw_output}"
        )

    # Save to DB for Streamlit dashboard visualization
    save_remote_traceroute(device['name'], device['ip'], target, hops)

    # Build structured response
    result = [f"Traceroute from {device['name']} ({device['ip']}) to {target}\n"]
    result.append(f"Hops: {len(hops)}\n")
    result.append("| Hop | IP Address | RTT (ms) |")
    result.append("|---|---|---|")
    for h in hops:
        result.append(f"| {h['hop']} | {h['ip']} | {h['rtt']} |")

    # Add a visual path summary
    path_nodes = [device['name']] + [h['ip'] for h in hops]
    result.append(f"\nPath: {' -> '.join(path_nodes)}")

    return "\n".join(result)
