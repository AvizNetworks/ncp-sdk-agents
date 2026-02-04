import os
import re
import shlex
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Deque
from collections import deque
from pathlib import PurePosixPath

try:
    import paramiko
except ImportError:
    paramiko = None

from ncp import tool

# Setup Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# =============================================================================
# 1. CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class SonicConfig:
    host: str = os.getenv("NCP_DUMP_HOST", "")
    user: str = os.getenv("NCP_DUMP_USER", "")
    password: str = os.getenv("NCP_DUMP_PASSWORD", "")
    port: int = int(os.getenv("NCP_DUMP_PORT", "22"))
    key_filename: str = os.getenv("NCP_DUMP_KEY", "")
    base_dir: str = os.getenv("NCP_DUMP_BASE_DIR", "")
    evidence_dir: str = os.getenv("NCP_EVIDENCE_DIR", "")

CFG = SonicConfig()

# =============================================================================
# 2. HELPER CLASSES (Security & storage)
# =============================================================================

class UnsafeCommandError(RuntimeError): pass

class PipelineValidator:
    """
    Enforces strict safety rules on shell commands.
    """
    ALLOWED_BINS = {
        "ls", "find", "grep", "rg", "cat", "zcat", 
        "wc", "stat", "head", "tail", "cut", "sort", "uniq"
    }
    FORBIDDEN_TOKENS = {";", "&&", "||", ">", ">>", "<", "<<", "|&", "$(", "`", "\\"}

    @staticmethod
    def validate(cmd: str, dump_root: str) -> None:
        if not cmd.strip():
            raise UnsafeCommandError("Empty command")

        if any(bad in cmd for bad in PipelineValidator.FORBIDDEN_TOKENS):
             raise UnsafeCommandError("Command contains forbidden shell characters")

        try:
            tokens = shlex.split(cmd)
        except ValueError as e:
            raise UnsafeCommandError(f"Shell parsing error: {e}")

        # Split pipeline
        stages: List[List[str]] = []
        current: List[str] = []
        for t in tokens:
            if t == "|":
                if not current: raise UnsafeCommandError("Empty pipe stage")
                stages.append(current)
                current = []
            else:
                current.append(t)
        if current: stages.append(current)

        if len(stages) > 4:
            raise UnsafeCommandError("Pipeline too long (max 4 stages)")

        # Validate stages
        for stage in stages:
            binary = stage[0]
            if binary not in PipelineValidator.ALLOWED_BINS:
                raise UnsafeCommandError(f"Binary '{binary}' not allowed")
            PipelineValidator._enforce_paths(stage, dump_root)

        # Enforce Output Limit (Head/Tail) on final stage
        last_stage = stages[-1]
        if last_stage[0] not in ("head", "tail"):
            raise UnsafeCommandError("Pipeline must end with 'head' or 'tail' to limit output")
        if "-n" not in last_stage:
             raise UnsafeCommandError("Final stage must use '-n' flag")

    @staticmethod
    def _enforce_paths(tokens: List[str], dump_root: str):
        for token in tokens[1:]:
            if token.startswith("-"): continue
            if token.startswith("/"):
                raise UnsafeCommandError("Absolute paths forbidden. Use relative paths.")
            if ".." in token:
                raise UnsafeCommandError("Directory traversal (..) forbidden.")

class Streamer:
    """Streams output to disk and keeps a small memory buffer for preview."""
    def __init__(self, local_path: str):
        self.file = open(local_path, "wb")
        self.preview_buffer: Deque[str] = deque(maxlen=20)
        self.line_buffer = b""

    def write_chunk(self, data: bytes):
        self.file.write(data)
        self.line_buffer += data
        while b'\n' in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split(b'\n', 1)
            try:
                self.preview_buffer.append(line.decode('utf-8', errors='replace'))
            except: pass

    def close(self):
        self.file.close()
    
    def get_preview(self) -> str:
        return "\n".join(self.preview_buffer)

# =============================================================================
# 3. GLOBAL SSH MANAGER (Persistent Connection)
# =============================================================================

class GlobalSSHManager:
    """Singleton to maintain one SSH connection across multiple tool calls."""
    _client: Optional["paramiko.SSHClient"] = None
    _dump_root_cache: Optional[str] = None
    _current_ticket: Optional[str] = None

    @classmethod
    def get_session(cls, ticket_id: str) -> Tuple["paramiko.SSHClient", str]:
        if paramiko is None:
            raise RuntimeError("Paramiko not installed")

        # Context Switch
        if cls._current_ticket != str(ticket_id):
            cls.close()
            cls._current_ticket = str(ticket_id)

        # Connect
        if cls._client is None or not cls._is_active():
            cls._connect()

        # Locate Dump
        if cls._dump_root_cache is None:
            cls._dump_root_cache = cls._find_dump_root(ticket_id)
            log.info(f"Dump root cached: {cls._dump_root_cache}")

        return cls._client, cls._dump_root_cache

    @classmethod
    def _connect(cls):
        log.info(f"Connecting to {CFG.host}...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": CFG.host, "port": CFG.port, "username": CFG.user,
            "look_for_keys": False, "allow_agent": False, "timeout": 10
        }
        if CFG.key_filename:
            kwargs["key_filename"] = CFG.key_filename
            kwargs["look_for_keys"] = True
        if CFG.password:
            kwargs["password"] = CFG.password
        
        try:
            client.connect(**kwargs)
            cls._client = client
        except Exception as e:
            raise RuntimeError(f"SSH Connect Failed: {e}")

    @classmethod
    def _is_active(cls):
        try: return cls._client.get_transport().is_active()
        except: return False

    @classmethod
    def close(cls):
        if cls._client:
            try: cls._client.close()
            except: pass
        cls._client = None
        cls._dump_root_cache = None

    @classmethod
    def _find_dump_root(cls, ticket_id: str) -> str:
        ticket_dir = os.path.join(CFG.base_dir, str(ticket_id), "extracted")
        # Raw command to find the directory
        cmd = "find . -maxdepth 2 -type d -name 'sonic_dump_*' | head -n 1"
        full_cmd = f"cd {shlex.quote(ticket_dir)} && bash -c {shlex.quote(cmd)}"
        
        stdin, stdout, stderr = cls._client.exec_command(full_cmd)
        path = stdout.read().decode().strip().replace("./", "")
        
        if not path:
            raise FileNotFoundError(f"No sonic_dump_* found in {ticket_dir}")
        return os.path.join(ticket_dir, path)

# =============================================================================
# 4. EXECUTOR (The Logic)
# =============================================================================

def _run_remote_tool(ticket_id: int, cmd: str, label: str, raw_mode: bool = False) -> Dict[str, Any]:
    """
    Internal helper to run commands via SSH, save output locally, and return preview.
    """
    t_id = str(ticket_id)
    evidence_path = os.path.join(CFG.evidence_dir, t_id)
    os.makedirs(evidence_path, exist_ok=True)

    try:
        client, root = GlobalSSHManager.get_session(t_id)

        # 1. Validation
        if raw_mode:
            try:
                PipelineValidator.validate(cmd, root)
            except UnsafeCommandError as e:
                return {"success": False, "error": f"Security Block: {e}"}

        # 2. Local File Setup
        timestamp = int(time.time())
        filename = f"{timestamp}_{label}.txt"
        local_filepath = os.path.join(evidence_path, filename)

        # 3. Execution
        full_cmd = f"cd {shlex.quote(root)} && bash -c {shlex.quote(cmd)}"
        stdin, stdout, stderr = client.exec_command(full_cmd, get_pty=False)
        
        streamer = Streamer(local_filepath)
        err_accum = []
        start_time = time.time()

        TIMEOUT_SECONDS = 300

        while True:
            if time.time() - start_time > TIMEOUT_SECONDS: 
                try: client.close()
                except: pass
                return {
                    "success": False, 
                    "error": f"Command timed out after {TIMEOUT_SECONDS}s. CMD: {cmd}"
                }

            if stdout.channel.exit_status_ready():
                while stdout.channel.recv_ready():
                    streamer.write_chunk(stdout.channel.recv(4096))
                break
            
            if stdout.channel.recv_ready():
                streamer.write_chunk(stdout.channel.recv(4096))
            
            if stderr.channel.recv_stderr_ready():
                chunk = stderr.channel.recv_stderr(4096)
                err_accum.append(chunk.decode(errors='replace'))
            
            time.sleep(0.01)

        exit_code = stdout.channel.recv_exit_status()
        streamer.close()

        if exit_code != 0:
            return {
                "success": False, 
                "exit_code": exit_code,
                "error": "".join(err_accum)
            }

        return {
            "success": True,
            "preview": streamer.get_preview(),
            "full_log_path": local_filepath,
            "total_lines_approx": "Available in file"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

# =============================================================================
# 5. THE TOOLS (Exposed to SDK)
# =============================================================================

@tool
def sonic_dump_list_files(ticket_id: int, directory: str = ".") -> Dict[str, Any]:
    """
    List files in the SONiC dump directory to understand the layout.
    
    Args:
        ticket_id: The Ticket ID.
        directory: Subdirectory to list (default is root ".").
    
    Returns:
        Dict with 'preview' (file list) and 'full_log_path'.
    """
    cmd = f"ls -F {shlex.quote(directory)}"
    return _run_remote_tool(ticket_id, cmd, "ls", raw_mode=False)

@tool
def sonic_dump_read_file(ticket_id: int, filepath: str, lines: int = 100) -> Dict[str, Any]:
    """
    Read the LAST N lines (tail) of a specific log file.
    
    Args:
        ticket_id: The Ticket ID.
        filepath: Relative path to the file (e.g. 'log/syslog').
        lines: Number of lines to read (max 500).
    """
    n = min(int(lines), 500)
    if ".." in filepath or filepath.startswith("/"):
        return {"success": False, "error": "Path must be relative and inside dump"}
    
    cmd = f"tail -n {n} {shlex.quote(filepath)}"
    return _run_remote_tool(ticket_id, cmd, "read_file", raw_mode=False)

@tool
def sonic_dump_search_logs(ticket_id: int, pattern: str, file_glob: str = "*.log") -> Dict[str, Any]:
    """
    Search for a text pattern or regex in log files.
    
    Args:
        ticket_id: The Ticket ID.
        pattern: The text/regex to find (e.g. "BGP", "Ethernet4 down").
        file_glob: Filename pattern to search (default "*.log").
    """
    # Pipeline: rg -> head (Safety enforced implicitly by tool logic)
    pat = shlex.quote(pattern)
    glob = shlex.quote(file_glob)
    # limit to 1000 matches, head 500 for safety
    cmd = f"rg -z -a -n --no-heading -m 1000 {pat} -g {glob} | head -n 500"
    
    safe_label = re.sub(r'[^a-zA-Z0-9]', '', pattern)[:10]
    return _run_remote_tool(ticket_id, cmd, f"search_{safe_label}", raw_mode=False)

@tool
def sonic_dump_run_custom_cmd(ticket_id: int, cmd: str) -> Dict[str, Any]:
    """
    Run a custom shell command/pipeline for advanced filtering.
    STRICTLY VALIDATED:
    - Must use allowable binaries (grep, cat, awk, etc.)
    - Must end with 'head -n' or 'tail -n'.
    - No redirects or dangerous operators.
    
    Example: "grep 'BGP' log/syslog | grep 'Error' | head -n 20"
    """
    return _run_remote_tool(ticket_id, cmd, "custom_cmd", raw_mode=True)