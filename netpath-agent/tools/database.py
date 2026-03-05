# tools/database.py
import sqlite3
import os
from datetime import datetime

# FIX: Use a hardcoded path so both Agent and User can find it
DB_PATH = "/tmp/netpath_data.db"

def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"🔥 [DB ERROR] Connection failed: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    
    # 1. Trace Runs Table
    c.execute('''CREATE TABLE IF NOT EXISTS trace_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target TEXT,
        timestamp DATETIME
    )''')

    # 2. Hops Table
    c.execute('''CREATE TABLE IF NOT EXISTS hops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        hop_index INTEGER,
        ip_address TEXT,
        rtt_ms REAL,
        loss_pct REAL,
        FOREIGN KEY(run_id) REFERENCES trace_runs(id)
    )''')

    # 3. Ping Stats Table (Direct Agent -> Device)
    c.execute('''CREATE TABLE IF NOT EXISTS ping_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target TEXT,
        timestamp DATETIME,
        avg_rtt REAL,
        packet_loss REAL,
        jitter REAL
    )''')

    # 4. Mesh Results Table (Device -> Device Matrix)
    c.execute('''CREATE TABLE IF NOT EXISTS mesh_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        source_device TEXT,
        dest_device TEXT,
        packet_loss REAL,
        rtt_ms REAL
    )''')

    # 5. Remote Traceroute Results Table
    c.execute('''CREATE TABLE IF NOT EXISTS remote_traceroutes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        device_name TEXT,
        device_ip TEXT,
        target TEXT,
        hop_index INTEGER,
        hop_ip TEXT,
        rtt_ms REAL
    )''')
    
    conn.commit()
    conn.close()
    print(f"✅ [DB INIT] Database initialized at: {DB_PATH}")

def save_trace_data(target, hops):
    conn = get_db_connection()
    if not conn: return
    try:
        timestamp = datetime.now().isoformat()
        c = conn.cursor()
        c.execute("INSERT INTO trace_runs (target, timestamp) VALUES (?, ?)", (target, timestamp))
        run_id = c.lastrowid
        
        hop_data = [(run_id, h['index'], h['ip'], h['rtt'], h['loss']) for h in hops]
        c.executemany("INSERT INTO hops (run_id, hop_index, ip_address, rtt_ms, loss_pct) VALUES (?, ?, ?, ?, ?)", hop_data)
        
        conn.commit()
        print(f"💾 [DB] Trace saved for {target}. Run ID: {run_id}")
    except Exception as e:
        print(f"🔥 [DB WRITE ERROR] Trace failed: {e}")
    finally:
        conn.close()

def save_ping_data(target, stats):
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        c.execute("INSERT INTO ping_stats (target, timestamp, avg_rtt, packet_loss, jitter) VALUES (?, ?, ?, ?, ?)",
                  (target, datetime.now().isoformat(), stats['avg_rtt'], stats['loss'], stats['jitter']))
        conn.commit()
        print(f"💾 [DB] Ping stats saved for {target}.")
    except Exception as e:
        print(f"🔥 [DB WRITE ERROR] Ping failed: {e}")
    finally:
        conn.close()

def save_mesh_result(results):
    """
    Saves a batch of mesh ping results (Any-to-Any).
    Expects 'results' to be a list of dicts: 
    {'timestamp':..., 'src':..., 'dst':..., 'loss':..., 'rtt':...}
    """
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        # Convert list of dicts to list of tuples for executemany
        data = [(r['timestamp'], r['src'], r['dst'], r['loss'], r['rtt']) for r in results]
        
        c.executemany("INSERT INTO mesh_results (timestamp, source_device, dest_device, packet_loss, rtt_ms) VALUES (?, ?, ?, ?, ?)", data)
        conn.commit()
        print(f"💾 [DB] Saved {len(results)} mesh results.")
    except Exception as e:
        print(f"🔥 [DB WRITE ERROR] Mesh save failed: {e}")
    finally:
        conn.close()

def fetch_recent_hops(target, limit=5):
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM trace_runs WHERE target = ? ORDER BY id DESC LIMIT ?", (target, limit))
        run_ids = [row[0] for row in c.fetchall()]
        if not run_ids: return []
        
        placeholders = ','.join('?' for _ in run_ids)
        query = f"SELECT run_id, hop_index, ip_address, rtt_ms, loss_pct FROM hops WHERE run_id IN ({placeholders}) ORDER BY run_id, hop_index"
        c.execute(query, run_ids)
        return [dict(row) for row in c.fetchall()]
    except Exception as e:
        print(f"🔥 [DB READ ERROR] {e}")
        return []
    finally:
        conn.close()

def fetch_mesh_data(source_device=None, dest_device=None, latest_only=True, limit=500):
    """
    Fetch mesh ping results for charting.
    Returns a list of dicts with keys: source_device, dest_device, packet_loss, rtt_ms, timestamp.
    If latest_only=True, only returns data from the most recent mesh run.
    """
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        if latest_only:
            c.execute("SELECT MAX(timestamp) FROM mesh_results")
            row = c.fetchone()
            if not row or row[0] is None: return []
            latest_ts = row[0]

            query = "SELECT source_device, dest_device, packet_loss, rtt_ms, timestamp FROM mesh_results WHERE timestamp = ?"
            params = [latest_ts]
        else:
            query = "SELECT source_device, dest_device, packet_loss, rtt_ms, timestamp FROM mesh_results WHERE 1=1"
            params = []

        if source_device:
            query += " AND source_device = ?"
            params.append(source_device)
        if dest_device:
            query += " AND dest_device = ?"
            params.append(dest_device)

        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        c.execute(query, params)
        return [dict(row) for row in c.fetchall()]
    except Exception as e:
        print(f"🔥 [DB READ ERROR] Mesh fetch failed: {e}")
        return []
    finally:
        conn.close()

def save_remote_traceroute(device_name, device_ip, target, hops):
    """Save remote traceroute hop-by-hop results to DB."""
    conn = get_db_connection()
    if not conn: return
    try:
        timestamp = datetime.now().isoformat()
        c = conn.cursor()
        data = [
            (timestamp, device_name, device_ip, target, h['hop'], h['ip'], h['rtt'])
            for h in hops
        ]
        c.executemany(
            "INSERT INTO remote_traceroutes (timestamp, device_name, device_ip, target, hop_index, hop_ip, rtt_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
            data
        )
        conn.commit()
        print(f"💾 [DB] Remote traceroute saved: {device_name} -> {target} ({len(hops)} hops)")
    except Exception as e:
        print(f"🔥 [DB WRITE ERROR] Remote traceroute save failed: {e}")
    finally:
        conn.close()

def fetch_latest_remote_traceroute():
    """Fetch the most recent remote traceroute results from DB."""
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        c.execute("SELECT MAX(timestamp) FROM remote_traceroutes")
        row = c.fetchone()
        if not row or row[0] is None: return []
        latest_ts = row[0]

        c.execute(
            "SELECT device_name, device_ip, target, hop_index, hop_ip, rtt_ms, timestamp "
            "FROM remote_traceroutes WHERE timestamp = ? ORDER BY hop_index",
            (latest_ts,)
        )
        return [dict(r) for r in c.fetchall()]
    except Exception as e:
        print(f"🔥 [DB READ ERROR] Remote traceroute fetch failed: {e}")
        return []
    finally:
        conn.close()

