from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import shlex
import time

from ncp import tool

try:
    import paramiko
except ImportError:
    paramiko = None

log = logging.getLogger(__name__)

import logging
logging.getLogger("paramiko").setLevel(logging.INFO)
# =============================================================================
# config.py
# =============================================================================

@dataclass(frozen=True)
class RemoteConfig:
    host: str = os.getenv("NCP_DUMP_HOST", "")
    user: str = os.getenv("NCP_DUMP_USER", "")
    password: str = os.getenv("NCP_DUMP_PASSWORD", "")
    base_dir: str = os.getenv("NCP_DUMP_BASE_DIR", "")
    recipes_file: str = os.getenv(
        "NCP_DUMP_RECIPES_FILE",
        os.path.join(os.path.dirname(__file__), "dump_recipes.json"),
    )

CFG = RemoteConfig()

# =============================================================================
# ssh.py
# =============================================================================

class SSHError(RuntimeError):
    pass

def get_ssh_client(cfg: RemoteConfig = CFG) -> "paramiko.SSHClient":
    if paramiko is None:
        raise SSHError("paramiko not installed")
    if not cfg.password:
        # If you want key auth later, add it here (pkey, agent, etc).
        raise SSHError("NCP_DUMP_PASSWORD is empty (refusing to connect)")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            cfg.host,
            username=cfg.user,
            password=cfg.password,
            look_for_keys=False,
            allow_agent=False,
        )
        return client
    except Exception as e:
        raise SSHError(f"Failed to connect to {cfg.host} as {cfg.user}: {e}") from e


def ssh_run(
    client: "paramiko.SSHClient",
    cmd: str,
    cwd: Optional[str] = None,
    max_bytes: int = 65536,
    timeout_s: int = 60,
    poll_s: float = 0.02,
    stall_timeout_s: Optional[int] = None,  # e.g. 20 to kill "no-output" hangs
) -> Dict[str, Any]:
    try:
        max_bytes = int(max_bytes)
    except (TypeError, ValueError):
        max_bytes = 65536

    try:
        timeout_s = int(timeout_s)
    except (TypeError, ValueError):
        timeout_s = 60

    bash_cmd = f"bash -lc {shlex.quote(cmd)}"
    full_cmd = f"cd {shlex.quote(cwd)} && {bash_cmd}" if cwd else bash_cmd

    chan = client.get_transport().open_session()

    t0 = time.time()
    log.info("remote cmd: %s", full_cmd)

    chan.exec_command(full_cmd)

    start = time.time()
    last_activity = start

    out_kept = bytearray()
    err_kept = bytearray()
    out_total = 0
    err_total = 0
    timed_out = False
    stalled = False

    def _take(buf: bytearray, chunk: bytes) -> None:
        if len(buf) >= max_bytes:
            return
        n = min(len(chunk), max_bytes - len(buf))
        if n > 0:
            buf.extend(chunk[:n])

    while True:
        now = time.time()

        if (now - start) > timeout_s:
            timed_out = True
            try:
                chan.close()
            except Exception:
                pass
            break

        if stall_timeout_s is not None and (now - last_activity) > stall_timeout_s:
            stalled = True
            try:
                chan.close()
            except Exception:
                pass
            break

        did_io = False

        if chan.recv_ready():
            chunk = chan.recv(4096)
            did_io = True
            out_total += len(chunk)
            _take(out_kept, chunk)

        if chan.recv_stderr_ready():
            chunk = chan.recv_stderr(4096)
            did_io = True
            err_total += len(chunk)
            _take(err_kept, chunk)

        if did_io:
            last_activity = now

        if chan.exit_status_ready():
            while chan.recv_ready():
                chunk = chan.recv(4096)
                out_total += len(chunk)
                _take(out_kept, chunk)
            while chan.recv_stderr_ready():
                chunk = chan.recv_stderr(4096)
                err_total += len(chunk)
                _take(err_kept, chunk)
            break

        time.sleep(poll_s)

    exit_code = None if (timed_out or stalled) else chan.recv_exit_status()
    elapsed_ms = int((time.time() - t0) * 1000)

    def _decode(b: bytearray) -> str:
        return bytes(b).decode(errors="replace")

    result = {
        "cmd": full_cmd,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stalled": stalled,
        "timeout_s": timeout_s,
        "elapsed_ms": elapsed_ms,
        "stdout": _decode(out_kept),
        "stderr": _decode(err_kept),
        "stdout_truncated": out_total > max_bytes,
        "stderr_truncated": err_total > max_bytes,
        "stdout_total_bytes": out_total,
        "stderr_total_bytes": err_total,
    }

    # The log line you asked for (compact and useful)
    log.info(
        "remote done exit=%s timeout=%s stalled=%s out_bytes=%d err_bytes=%d elapsed_ms=%d",
        result["exit_code"],
        result["timed_out"],
        result["stalled"],
        result["stdout_total_bytes"],
        result["stderr_total_bytes"],
        result["elapsed_ms"],
    )

    return result

# =============================================================================
# paths.py
# =============================================================================

def remote_ticket_paths(ticket_id: int, cfg: RemoteConfig = CFG) -> Dict[str, str]:
    tid = str(int(ticket_id))
    ticket_dir = os.path.join(cfg.base_dir, tid)
    extracted_dir = os.path.join(ticket_dir, "extracted")
    return {"ticket_dir": ticket_dir, "extracted_dir": extracted_dir}

# =============================================================================
# recipes.py
# =============================================================================

_RECIPES_CACHE: Optional[Dict[str, Any]] = None

def load_recipes(cfg: RemoteConfig = CFG, force_reload: bool = False) -> Dict[str, Any]:
    global _RECIPES_CACHE
    if _RECIPES_CACHE is not None and not force_reload:
        return _RECIPES_CACHE

    data: Dict[str, Any] = {}
    try:
        with open(cfg.recipes_file, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except FileNotFoundError:
        log.error("recipes file not found: %s", cfg.recipes_file)
    except Exception as e:
        log.error("failed to load recipes file %s: %s", cfg.recipes_file, e)

    data.setdefault("dump_recipes", {})
    data.setdefault("ticket_text_recipes", {})

    _RECIPES_CACHE = data
    return data

def normalize(s: str) -> str:
    return " ".join((s or "").strip().lower().replace("-", " ").replace("_", " ").split())

def list_recipe_keys(product: str, scope: str) -> List[str]:
    data = load_recipes()
    prod = normalize(product)
    scope = normalize(scope)
    if scope in ("dump", "dump_recipes"):
        prod_map = data["dump_recipes"].get(prod, {})
    else:
        prod_map = data["ticket_text_recipes"].get(prod, {})
    #keys = sorted(prod_map.keys())
    keys = [k for k in sorted(prod_map.keys()) if get_recipe_items(product, scope, k)]
    return keys

def get_recipe_items(product: str, scope: str, key: str) -> List[Dict[str, Any]]:
    data = load_recipes()
    prod = normalize(product)
    keyn = normalize(key).replace(" ", "_")
    scope_n = normalize(scope)

    prod_map = (
        data["dump_recipes"].get(prod, {})
        if scope_n in ("dump", "dump_recipes")
        else data["ticket_text_recipes"].get(prod, {})
    )

    def _unwrap(v: Any) -> List[Dict[str, Any]]:
        # Old format: list of steps
        if isinstance(v, list):
            return v
        # New format: {"aliases": [...], "items": [...]}
        if isinstance(v, dict):
            items = v.get("items", [])
            return items if isinstance(items, list) else []
        return []

    if keyn in prod_map:
        return _unwrap(prod_map[keyn])
    if "default" in prod_map:
        return _unwrap(prod_map["default"])
    return []


def search_recipe_keys(product: str, scope: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    q = normalize(query)
    data = load_recipes()
    prod = normalize(product)
    scope_n = normalize(scope)

    # pick the right namespace
    if scope_n in ("dump", "dump_recipes"):
        prod_map: Dict[str, Any] = data.get("dump_recipes", {}).get(prod, {}) or {}
    else:
        prod_map = data.get("ticket_text_recipes", {}).get(prod, {}) or {}

    keys = sorted(prod_map.keys())
    scored: List[Tuple[int, str, str]] = []

    for k in keys:
        raw = prod_map.get(k)

        # aliases only exist in the NEW format
        aliases: List[str] = []
        if isinstance(raw, dict):
            a = raw.get("aliases", [])
            if isinstance(a, list):
                aliases = [str(x) for x in a if x is not None]

        # items come from your schema-tolerant getter
        items = get_recipe_items(product, scope, k)

        blob = " ".join(
            [str(k)]
            + aliases
            + [str(i.get("name", "")) for i in items]
            + [str(i.get("description", "")) for i in items]
            + [str(i.get("files", "")) for i in items]
            + [str(i.get("pattern", "")) for i in items]
        )
        b = normalize(blob)

        score = 0
        # exact-ish key match
        if normalize(k).replace(" ", "_") == q.replace(" ", "_"):
            score += 100
        # substring match anywhere (including aliases)
        if q and q in b:
            score += 50

        q_tokens = set(q.split())
        b_tokens = set(b.split())
        score += 2 * len(q_tokens & b_tokens)

        if score > 0:
            hint = items[0].get("description", "") if items else ""
            scored.append((score, k, str(hint)))

    scored.sort(reverse=True, key=lambda x: x[0])
    limit = max(1, int(limit))
    return [{"key": k, "score": s, "hint": hint} for s, k, hint in scored[:limit]]


# =============================================================================
# dumps.py
# =============================================================================

def find_all_dump_roots(client: "paramiko.SSHClient", extracted_dir: str) -> List[str]:
    res = ssh_run(client, "find . -maxdepth 2 -type d -name 'sonic_dump_*' | sort", cwd=extracted_dir)
    roots: List[str] = []
    for line in res["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("./"):
            line = line[2:]
        roots.append(os.path.join(extracted_dir, line))
    return roots

def list_archives(client: "paramiko.SSHClient", ticket_dir: str) -> List[Dict[str, str]]:
    res = ssh_run(client, "ls -lh | egrep '\\.tar(\\.gz)?$|\\.tgz$|\\.zip$' || true", cwd=ticket_dir)
    archives: List[Dict[str, str]] = []
    for line in res["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 9 and parts[0].startswith("-"):
            archives.append({"name": parts[8], "size": parts[4], "mtime": " ".join(parts[5:8])})
    return archives

def extract_all_archives(client: "paramiko.SSHClient", ticket_dir: str, extracted_dir: str) -> Dict[str, Any]:
    ssh_run(client, f"mkdir -p {extracted_dir}")

    ls_arch = ssh_run(client, "ls -1 *.tar *.tar.gz *.tgz *.zip 2>/dev/null", cwd=ticket_dir)
    archives = [l.strip() for l in ls_arch["stdout"].splitlines() if l.strip()]
    if not archives:
        return {"success": False, "archives": [], "cmds": [], "notes": ["No archives found"]}

    cmds: List[str] = []
    notes: List[str] = []

    for a in archives:
        if a.endswith(".zip"):
            cmd = f"unzip -o {a} -d {extracted_dir}"
        else:
            cmd = f"tar -xf {a} -C {extracted_dir}"
        cmds.append(cmd)
        r = ssh_run(client, cmd, cwd=ticket_dir)
        if r["exit_code"] != 0:
            notes.append(f"extract failed: {a} (exit={r['exit_code']})")
            notes.append(f"stderr: {r['stderr'][:400]}")

    return {"success": True, "archives": archives, "cmds": cmds, "notes": notes}

# =============================================================================
# runner.py
# =============================================================================

def run_recipe_in_dir(
    client: "paramiko.SSHClient",
    cwd: str,
    recipe_items: List[Dict[str, Any]],
    max_bytes: int = 65536,
    timeout_s: int = 60,
    stall_timeout_s: Optional[int] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in recipe_items:
        cmd = item.get("cmd", "")
        if not cmd:
            continue

        # allow per-step override in recipe item if present
        step_timeout = item.get("timeout_s", timeout_s)
        step_stall = item.get("stall_timeout_s", stall_timeout_s)

        r = ssh_run(
            client,
            cmd,
            cwd=cwd,
            max_bytes=max_bytes,
            timeout_s=int(step_timeout) if step_timeout else timeout_s,
            stall_timeout_s=int(step_stall) if step_stall else step_stall,
        )
        r["name"] = item.get("name", "unnamed")
        r["description"] = item.get("description", "")
        r["files"] = item.get("files", "")
        r["pattern"] = item.get("pattern", "")
        out.append(r)
    return out
# =============================================================================
# tools.py (thin wrappers)
# =============================================================================

@tool
def recipes_list(product: str = "sonic", scope: str = "dump") -> Dict[str, Any]:
    """List available recipe keys for a product and scope ('dump' or 'ticket_text')."""
    keys = list_recipe_keys(product, scope)
    return {"success": True, "product": product, "scope": scope, "keys": keys}

@tool
def recipes_search(product: str = "sonic", scope: str = "dump", query: str = "", limit: int = 5) -> Dict[str, Any]:
    """Search recipes by natural language, e.g. 'show version', 'bgp flap', 'oom'."""
    matches = search_recipe_keys(product, scope, query, limit=limit)
    return {"success": True, "product": product, "scope": scope, "query": query, "matches": matches}

@tool
def recipes_get(product: str = "sonic", scope: str = "dump", key: str = "default") -> Dict[str, Any]:
    """Return the recipe items for a given key (or default fallback)."""
    items = get_recipe_items(product, scope, key)
    return {"success": bool(items), "product": product, "scope": scope, "key": key, "items": items}

@tool
def list_remote_ticket_dumps(ticket_id: int) -> Dict[str, Any]:
    """
    List remote Zendesk ticket dump artifacts for a given ticket_id.

    This checks the remote ticket directory, lists archive files (tar/tgz/zip),
    inspects the extracted/ directory, and discovers any extracted SONiC dump roots
    matching 'sonic_dump_*'. It returns paths and lightweight directory listings
    to help the orchestrator decide whether extraction is needed.
    """
    paths = remote_ticket_paths(ticket_id)
    ticket_dir = paths["ticket_dir"]
    extracted_dir = paths["extracted_dir"]
    notes: List[str] = []

    try:
        client = get_ssh_client()
    except Exception as e:
        return {"ticket_id": ticket_id, "success": False, "ticket_dir": ticket_dir, "notes": [str(e)]}

    try:
        check = ssh_run(client, f"ls -ld {ticket_dir} 2>/dev/null || echo '__MISSING__'")
        if "__MISSING__" in check["stdout"]:
            return {"ticket_id": ticket_id, "success": False, "ticket_dir": ticket_dir, "notes": [f"missing: {ticket_dir}"]}

        archives = list_archives(client, ticket_dir)

        ls_ticket = ssh_run(client, "ls -lh", cwd=ticket_dir)
        ls_extracted = ssh_run(client, "ls -lh 2>/dev/null || echo '__EMPTY__'", cwd=extracted_dir)

        dump_roots = find_all_dump_roots(client, extracted_dir)
        extracted_root = dump_roots[0] if dump_roots else ""
        if not dump_roots:
            notes.append("No sonic_dump_* directory found under extracted/")

        top_level: List[str] = []
        if extracted_root:
            ls_root = ssh_run(client, "ls -1 2>/dev/null || true", cwd=extracted_root)
            top_level = [s for s in ls_root["stdout"].splitlines() if s.strip()]

        return {
            "ticket_id": ticket_id,
            "success": True,
            "ticket_dir": ticket_dir,
            "archives": archives,
            "extracted_dir": extracted_dir,
            "extracted_root": extracted_root,
            "all_dump_roots": dump_roots,
            "extracted_top_level": top_level,
            "raw_ls_ticket": ls_ticket["stdout"],
            "raw_ls_extracted": ls_extracted["stdout"],
            "notes": notes,
        }
    finally:
        try:
            client.close()
        except Exception:
            pass

@tool
def extract_remote_ticket_dump(ticket_id: int) -> Dict[str, Any]:
    """
    Extract all dump archives for a given ticket_id into the remote extracted/ directory.

    The tool looks for supported archive formats in the ticket directory (*.tar, *.tar.gz,
    *.tgz, *.zip), extracts them into extracted/, and then scans for any 'sonic_dump_*'
    directories to confirm usable dumps exist after extraction.
    """
    paths = remote_ticket_paths(ticket_id)
    ticket_dir = paths["ticket_dir"]
    extracted_dir = paths["extracted_dir"]
    notes: List[str] = []

    try:
        client = get_ssh_client()
    except Exception as e:
        return {"ticket_id": ticket_id, "success": False, "ticket_dir": ticket_dir, "notes": [str(e)]}

    try:
        check = ssh_run(client, f"ls -ld {ticket_dir} 2>/dev/null || echo '__MISSING__'")
        if "__MISSING__" in check["stdout"]:
            return {"ticket_id": ticket_id, "success": False, "ticket_dir": ticket_dir, "notes": [f"missing: {ticket_dir}"]}

        pre = list_archives(client, ticket_dir)
        ex = extract_all_archives(client, ticket_dir, extracted_dir)
        notes.extend(ex.get("notes", []))

        dump_roots = find_all_dump_roots(client, extracted_dir)
        extracted_root = dump_roots[0] if dump_roots else ""

        if not dump_roots:
            notes.append("Extraction done but no sonic_dump_* found")

        return {
            "ticket_id": ticket_id,
            "success": bool(dump_roots),
            "ticket_dir": ticket_dir,
            "extracted_dir": extracted_dir,
            "archives_used": ex.get("archives", []),
            "extract_cmds": ex.get("cmds", []),
            "pre_extract_archives": pre,
            "all_dump_roots": dump_roots,
            "extracted_root": extracted_root,
            "notes": notes,
        }
    finally:
        try:
            client.close()
        except Exception:
            pass

@tool
def run_remote_dump_recipe_all(
    ticket_id: int,
    product: str = "sonic",
    recipe_key: str = "default",
    max_bytes: int = 65536,
    per_cmd_timeout_s: int = 60,
    stall_timeout_s: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run a dump recipe (by recipe_key) against ALL extracted SONiC dumps under extracted/.

    - Uses get_recipe_items(product, scope='dump', key=recipe_key)
    - Finds all dump roots under extracted/ matching 'sonic_dump_*'
    - Executes each recipe command inside each dump root
    - Returns per-dump command results (stdout/stderr/exit codes, with truncation)

    Note: Use recipes_search() to discover valid recipe keys deterministically.
    """
    max_bytes = int(max_bytes)
    paths = remote_ticket_paths(ticket_id)
    extracted_dir = paths["extracted_dir"]
    notes: List[str] = []

    items = get_recipe_items(product, "dump", recipe_key)
    if not items:
        return {"ticket_id": ticket_id, "success": False, "notes": [f"no dump recipe for {product}:{recipe_key}"]}

    try:
        client = get_ssh_client()
    except Exception as e:
        return {"ticket_id": ticket_id, "success": False, "notes": [str(e)]}

    try:
        dump_roots = find_all_dump_roots(client, extracted_dir)
        if not dump_roots:
            return {"ticket_id": ticket_id, "success": False, "notes": ["no sonic_dump_* under extracted/"]}

        per_dump: List[Dict[str, Any]] = []
        for root in dump_roots:
            cmds = run_recipe_in_dir(
                client,
                root,
                items,
                max_bytes=max_bytes,
                timeout_s=per_cmd_timeout_s,
                stall_timeout_s=stall_timeout_s,
            )
            per_dump.append({
                "dump_root": root,
                "device": os.path.basename(root),
                "success": True,
                "commands": cmds,
                "notes": [],
            })

        return {
            "ticket_id": ticket_id,
            "product": product,
            "recipe_key": recipe_key,
            "success": True,
            "per_dump": per_dump,
            "notes": notes,
        }
    finally:
        try:
            client.close()
        except Exception:
            pass


@tool
def run_remote_ticket_text_recipe(
    ticket_id: int,
    product: str = "sonic",
    recipe_key: str = "default",
    max_bytes: int = 65536,
    per_cmd_timeout_s: int = 60,
    stall_timeout_s: Optional[int] = None,
    ) -> Dict[str, Any]:
    """
    Run a ticket_text recipe (by recipe_key) inside the remote ticket directory.

    - Uses get_recipe_items(product, scope='ticket_text', key=recipe_key)
    - Executes each recipe command in the ticket directory
    - Returns command results (stdout/stderr/exit codes, with truncation)

    Note: Use recipes_search(product, scope='ticket_text', query=...) to discover keys.
    """
    max_bytes = int(max_bytes)
    paths = remote_ticket_paths(ticket_id)
    ticket_dir = paths["ticket_dir"]

    items = get_recipe_items(product, "ticket_text", recipe_key)
    if not items:
        return {"ticket_id": ticket_id, "success": False, "notes": [f"no ticket_text recipe for {product}:{recipe_key}"]}

    try:
        client = get_ssh_client()
    except Exception as e:
        return {"ticket_id": ticket_id, "success": False, "notes": [str(e)]}

    try:
        cmds = run_recipe_in_dir(
            client,
            ticket_dir,
            items,
            max_bytes=max_bytes,
            timeout_s=per_cmd_timeout_s,
            stall_timeout_s=stall_timeout_s,
        )
        return {
            "ticket_id": ticket_id,
            "product": product,
            "recipe_key": recipe_key,
            "success": True,
            "commands": cmds,
            "notes": [],
        }
    finally:
        try:
            client.close()
        except Exception:
            pass
