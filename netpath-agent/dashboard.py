import streamlit as st
import sqlite3
import pandas as pd
import networkx as nx
import streamlit.components.v1 as components
from pyvis.network import Network
import os

# POINT TO THE SHARED DB
DB_PATH = "/tmp/netpath_data.db"
st.set_page_config(layout="wide", page_title="NetPath Intelligence")

def get_data():
    if not os.path.exists(DB_PATH):
        return None, None, None, None
    
    try:
        conn = sqlite3.connect(DB_PATH)
        # 1. TRACES: Fetch last 100 runs
        runs = pd.read_sql("SELECT * FROM trace_runs ORDER BY id DESC LIMIT 100", conn)
        
        # 2. HOPS: Fetch hops associated with those runs
        hops = pd.read_sql("SELECT * FROM hops WHERE run_id IN (SELECT id FROM trace_runs ORDER BY id DESC LIMIT 100)", conn)
        
        # 3. PINGS: Recent stats
        pings = pd.read_sql("SELECT * FROM ping_stats ORDER BY id DESC LIMIT 100", conn)
        
        # 4. MESH: Fetch plenty of records (5000) to ensure we get the full latest scan
        mesh = pd.read_sql("SELECT * FROM mesh_results ORDER BY id DESC LIMIT 5000", conn)
        
        conn.close()
        return runs, hops, pings, mesh
    except Exception as e:
        st.error(f"Error reading database: {e}")
        return None, None, None, None

st.title("🕸️ NetPath Live Topology & Matrix")

if st.button('🔄 Refresh Data'):
    st.rerun()

runs, hops, pings, mesh = get_data()

# --- TAB LAYOUT ---
tab1, tab2, tab3 = st.tabs(["🗺️ Unified Topology Map", "🧮 Fabric Heatmap", "🛤️ Traceroute Path"])

# --- TAB 1: UNIFIED TOPOLOGY GRAPH ---
with tab1:
    st.subheader("Composite Network Graph")
    
    if hops is not None and not hops.empty and runs is not None:
        G = nx.DiGraph()
        
        # Iterate through distinct runs to build the graph
        for _, run in runs.iterrows():
            run_id = run['id']
            run_hops = hops[hops['run_id'] == run_id].sort_values('hop_index')
            if run_hops.empty: continue
            
            # Scenario A: Single Hop (Direct)
            if len(run_hops) == 1:
                hop = run_hops.iloc[0]
                target_ip = hop['ip_address']
                loss = hop['loss_pct']
                rtt = hop['rtt_ms']
                
                # Logic: If loss is 100%, draw RED edge. Else GREEN.
                if loss == 100:
                    color = "#ff4b4b" # Red
                    title = "Unreachable (100% Loss)"
                    node_color = "#ff4b4b"
                else:
                    color = "#00ff00" # Green
                    title = f"Direct | {rtt}ms"
                    node_color = "#2b7ce9" # Blue for healthy device
                
                G.add_edge("NCP-Agent", target_ip, title=title, color=color, width=2)
                G.add_node("NCP-Agent", label="NCP-Agent", color="#ffa500", shape="box", title="The Agent")
                G.add_node(target_ip, label=target_ip, color=node_color, title=f"{target_ip}\nLoss: {loss}%")

            # Scenario B: Multi-Hop
            else:
                for i in range(len(run_hops) - 1):
                    src = run_hops.iloc[i]['ip_address']
                    dst = run_hops.iloc[i+1]['ip_address']
                    loss = run_hops.iloc[i+1]['loss_pct']
                    rtt = run_hops.iloc[i+1]['rtt_ms']
                    
                    if src == "*" or dst == "*": continue
                    
                    color = "#ff4b4b" if loss > 0 else "#00ff00"
                    G.add_edge(src, dst, title=f"RTT: {rtt}ms | Loss: {loss}%", color=color)
                    G.add_node(src, label=src, color="#2b7ce9", title=src)
                    G.add_node(dst, label=dst, color="#2b7ce9", title=dst)

        if len(G.nodes) > 0:
            net = Network(height="600px", width="100%", bgcolor="#0e1117", font_color="white", directed=True)
            net.from_nx(G)
            net.set_options("""
            var options = {
              "physics": { "forceAtlas2Based": { "gravitationalConstant": -50, "springLength": 100 }, "solver": "forceAtlas2Based" }
            }
            """)
            net.save_graph("graph.html")
            with open("graph.html", 'r', encoding='utf-8') as f:
                components.html(f.read(), height=620)
        else:
            st.info("No connections found yet.")
    else:
        st.warning("No Topology Data Found. Run scans on multiple devices to build the map.")

# --- TAB 2: ADVANCED MATRIX ---
with tab2:
    st.header("Fabric Connectivity Heatmap")
    
    if mesh is not None and not mesh.empty:
        # 1. Get the most recent timestamp
        latest_time = mesh['timestamp'].max()
        
        # 2. Filter data for ONLY that timestamp
        latest_mesh = mesh[mesh['timestamp'] == latest_time].copy()
        
        # --- THE FIX: REMOVE DUPLICATES ---
        # Keep the first occurrence of any (source, dest) pair to prevent pivot errors
        latest_mesh = latest_mesh.drop_duplicates(subset=['source_device', 'dest_device'])
        
        metric = st.radio("Select Metric:", ["Packet Loss (%)", "Latency (ms)"], horizontal=True)
        
        if metric == "Packet Loss (%)":
            val_col = 'packet_loss'
            fmt = "{:.0f}%"
        else:
            val_col = 'rtt_ms'
            fmt = "{:.2f} ms"

        try:
            # 3. Safe Pivot
            matrix = latest_mesh.pivot(index='source_device', columns='dest_device', values=val_col)
            
            def color_coding(val):
                if pd.isna(val): return ''
                if metric == "Packet Loss (%)":
                    # Green=0, Red=100
                    if val == 0: return 'background-color: #28a745; color: white'
                    if val >= 100: return 'background-color: #dc3545; color: white'
                    return 'background-color: #ffc107; color: black'
                else:
                    # Latency: Green<1ms, Yellow<10ms, Red>10ms
                    if val == 0: return ''
                    if val < 1.0: return 'background-color: #20c997; color: black'
                    if val < 10.0: return 'background-color: #ffc107; color: black'
                    return 'background-color: #dc3545; color: white'

            st.caption(f"Last Mesh Run: {latest_time}")
            st.dataframe(matrix.style.map(color_coding).format(fmt), use_container_width=True)
            
        except ValueError as e:
            st.error(f"Data Pivot Error: {e}")
            st.write("Debug Data:", latest_mesh.head())
            
    else:
        st.info("No Mesh Data found. Ask the Agent to 'Run a Ping Mesh'.")

# --- TAB 3: TRACEROUTE PATH VISUALIZATION ---
with tab3:
    st.header("Remote Traceroute Path Diagram")
    st.caption("Shows the hop-by-hop path from a source device to a target destination.")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        tr_data = pd.read_sql(
            "SELECT device_name, device_ip, target, hop_index, hop_ip, rtt_ms, timestamp "
            "FROM remote_traceroutes ORDER BY timestamp DESC LIMIT 500", conn
        )
        conn.close()
    except Exception:
        tr_data = pd.DataFrame()

    if not tr_data.empty:
        # Get unique traceroute runs (by timestamp)
        timestamps = tr_data['timestamp'].unique()
        latest_ts = timestamps[0]
        latest_tr = tr_data[tr_data['timestamp'] == latest_ts].sort_values('hop_index')

        device_name = latest_tr.iloc[0]['device_name']
        device_ip = latest_tr.iloc[0]['device_ip']
        target = latest_tr.iloc[0]['target']

        st.markdown(f"**Latest Run:** `{device_name}` ({device_ip}) → `{target}` at {latest_ts}")

        # Build vis.js path graph
        G_tr = nx.DiGraph()

        # Source node
        src_label = f"{device_name}\n({device_ip})"
        G_tr.add_node(src_label, label=src_label, color="#ffa500", shape="box",
                      title=f"Source: {device_name}\nIP: {device_ip}", size=20)

        prev_node = src_label
        for _, hop in latest_tr.iterrows():
            hop_ip = hop['hop_ip']
            rtt = hop['rtt_ms']
            hop_idx = hop['hop_index']

            # Node styling
            if hop_ip == "*":
                node_label = f"Hop {hop_idx}\n* (timeout)"
                node_color = "#6c757d"  # Gray
                node_title = f"Hop {hop_idx}: Timeout"
            else:
                node_label = f"Hop {hop_idx}\n{hop_ip}"
                node_title = f"Hop {hop_idx}: {hop_ip}\nRTT: {rtt} ms"
                if rtt <= 0:
                    node_color = "#6c757d"   # Gray for no response
                elif rtt < 10:
                    node_color = "#28a745"    # Green - fast
                elif rtt < 50:
                    node_color = "#ffc107"    # Yellow - moderate
                else:
                    node_color = "#dc3545"    # Red - slow

            G_tr.add_node(node_label, label=node_label, color=node_color,
                          shape="dot", title=node_title, size=15)

            # Edge styling
            edge_label = f"{rtt} ms" if hop_ip != "*" else "timeout"
            edge_color = node_color
            G_tr.add_edge(prev_node, node_label, title=edge_label, label=edge_label,
                          color=edge_color, width=2, arrows="to")
            prev_node = node_label

        # Target node (final destination)
        target_label = f"Target\n{target}"
        G_tr.add_node(target_label, label=target_label, color="#2b7ce9", shape="star",
                      title=f"Destination: {target}", size=20)
        if prev_node != src_label:
            G_tr.add_edge(prev_node, target_label, title="destination", label="",
                          color="#2b7ce9", width=2, arrows="to")

        # Render with pyvis
        net_tr = Network(height="500px", width="100%", bgcolor="#0e1117",
                         font_color="white", directed=True)
        net_tr.from_nx(G_tr)
        net_tr.set_options("""
        var options = {
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "LR",
              "sortMethod": "directed",
              "nodeSpacing": 150,
              "levelSeparation": 200
            }
          },
          "physics": { "enabled": false },
          "edges": {
            "font": { "size": 12, "color": "#cccccc", "align": "top" },
            "smooth": { "type": "cubicBezier" }
          },
          "nodes": {
            "font": { "size": 12 }
          }
        }
        """)
        net_tr.save_graph("traceroute_graph.html")
        with open("traceroute_graph.html", 'r', encoding='utf-8') as f:
            components.html(f.read(), height=520)

        # Summary stats
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        total_hops = len(latest_tr)
        non_timeout_hops = latest_tr[latest_tr['hop_ip'] != '*']
        timeout_hops = latest_tr[latest_tr['hop_ip'] == '*']

        col1.metric("Total Hops", total_hops)
        if not non_timeout_hops.empty:
            slowest = non_timeout_hops.loc[non_timeout_hops['rtt_ms'].idxmax()]
            col2.metric("Slowest Hop", f"{slowest['rtt_ms']} ms", delta=slowest['hop_ip'])
            col3.metric("End-to-End RTT", f"{non_timeout_hops['rtt_ms'].iloc[-1]} ms")
        else:
            col2.metric("Slowest Hop", "N/A")
            col3.metric("End-to-End RTT", "N/A")
        col4.metric("Timeouts", len(timeout_hops))

        # Hop data table
        st.subheader("Hop Details")
        st.dataframe(latest_tr[['hop_index', 'hop_ip', 'rtt_ms']].rename(
            columns={'hop_index': 'Hop', 'hop_ip': 'IP Address', 'rtt_ms': 'RTT (ms)'}
        ), use_container_width=True)
    else:
        st.info("No Traceroute Data found. Ask the Agent to 'Run a remote traceroute from [device] to [target]'.")
