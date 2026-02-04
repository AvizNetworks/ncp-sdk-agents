"""Tool for downloading ALL attachments from Zendesk tickets
and archiving them on a remote server."""

from __future__ import annotations

import io
import logging
import os
from typing import Any, Dict, List, Tuple, Optional

import requests
from ncp import tool

from .zd_tools import _get_zendesk_auth, _request

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from creds_loader import get_ssh_config

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION - All settings in one place
# ============================================================================

# Archive server configuration
ssh_config = get_ssh_config("ncp_dump")
ARCHIVE_HOST = ssh_config.get("host", "")
ARCHIVE_USER = ssh_config.get("user", "")
ARCHIVE_BASE_DIR = ssh_config.get("base_dir", "")
ARCHIVE_PASSWORD = ssh_config.get("password", "")

ALLOWED_EXTENSIONS = (
    # Text files
    ".txt", ".log", ".md", ".csv",
    # Archives (tech dumps)
    ".tar.gz", ".tgz", ".tar", ".gz", ".zip",
)

BLOCKED_EXTENSIONS = (
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".ico", ".webp",
    # Videos
    ".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm",
    # Audio
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
    # Documents (binary formats)
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Executables
    ".exe", ".dll", ".so", ".dylib", ".bin",
    # Compressed executables
    ".deb", ".rpm", ".dmg", ".msi",
)

ALLOWED_MIME_TYPES = (
    # Text
    "text/plain", "text/html", "text/css", "text/javascript",
    "text/csv", "text/markdown", "text/x-log",
    # Config/Data
    "application/json", "application/xml", "application/yaml",
    "application/x-yaml", "application/x-sh",
    # Archives
    "application/gzip", "application/x-gzip", 
    "application/x-tar", "application/x-compressed-tar",
    "application/zip", "application/x-zip-compressed",
)

BLOCKED_MIME_TYPES = (
    # Images
    "image/jpeg", "image/png", "image/gif", "image/bmp", 
    "image/svg+xml", "image/webp",
    # Videos
    "video/mp4", "video/mpeg", "video/quicktime", "video/x-msvideo",
    # Audio
    "audio/mpeg", "audio/wav", "audio/ogg",
    # Binary documents
    "application/pdf", 
    "application/msword", "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument",
    # Executables
    "application/x-executable", "application/x-dosexec",
)


MAX_TEXT_FILE_SIZE = 200_000  # 200 KB for text files (will truncate)
MAX_BINARY_FILE_SIZE = 10_000_000_000  # 10 GB for archives (no truncation)
DOWNLOAD_TIMEOUT = 300  # 5 minutes for large files

try:
    import paramiko
except ImportError:
    paramiko = None

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _coerce_int(value: Optional[Any], name: str) -> Optional[int]:
    """Convert value to int or return None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer")


def _coerce_required_int(value: Any, name: str) -> int:
    """Convert value to int or raise error."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer")


def _should_download_attachment(file_name: str, content_type: str) -> Tuple[bool, str]:
    """
    Determine if attachment should be downloaded.
    
    Returns:
        (should_download: bool, reason: str)
    """
    name_lower = (file_name or "").lower()
    mime_lower = (content_type or "").lower()
    
    # Check BLOCKED list first (takes priority)
    for ext in BLOCKED_EXTENSIONS:
        if name_lower.endswith(ext):
            return False, f"Blocked extension: {ext}"
    
    for mime in BLOCKED_MIME_TYPES:
        if mime_lower.startswith(mime) or mime in mime_lower:
            return False, f"Blocked MIME type: {mime}"
    
    # Check ALLOWED list
    for ext in ALLOWED_EXTENSIONS:
        if name_lower.endswith(ext):
            return True, f"Allowed extension: {ext}"
    
    for mime in ALLOWED_MIME_TYPES:
        if mime_lower.startswith(mime) or mime in mime_lower:
            return True, f"Allowed MIME type: {mime}"
    
    # Default: block unknown types
    return False, f"Unknown type (ext: {os.path.splitext(name_lower)[1] or 'none'}, mime: {mime_lower or 'none'})"


def _is_archive_file(file_name: str, content_type: str) -> bool:
    """Check if file is an archive/dump (tar.gz, zip, etc.)."""
    name_lower = (file_name or "").lower()
    mime_lower = (content_type or "").lower()
    
    archive_extensions = (".tar.gz", ".tgz", ".tar", ".gz", ".zip")
    archive_mimes = (
        "application/gzip", "application/x-gzip",
        "application/x-tar", "application/x-compressed-tar",
        "application/zip", "application/x-zip-compressed",
    )
    
    for ext in archive_extensions:
        if name_lower.endswith(ext):
            return True
    
    for mime in archive_mimes:
        if mime in mime_lower:
            return True
    
    return False


def _download_attachment_content(
    url: str,
    max_bytes: int = MAX_TEXT_FILE_SIZE,
) -> Tuple[bytes, str, bool]:
    """
    Download attachment from Zendesk.
    
    Returns:
        (data: bytes, encoding: str, truncated: bool)
    """
    cfg = _get_zendesk_auth()
    
    try:
        resp = requests.get(url, auth=cfg["auth"], timeout=DOWNLOAD_TIMEOUT, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error(f"Failed to download attachment from {url}: {exc}")
        raise
    
    # Download with size limit
    data = bytearray()
    truncated = False
    
    for chunk in resp.iter_content(chunk_size=8192):
        if chunk:
            data.extend(chunk)
            if len(data) > max_bytes:
                data = data[:max_bytes]
                truncated = True
                break
    
    encoding = resp.encoding or "utf-8"
    return bytes(data), encoding, truncated


def _save_attachment_to_archive(
    ticket_id: int,
    file_name: str,
    data: bytes,
) -> Optional[str]:
    """
    Save attachment to remote archive server via SFTP.
    
    Path: ARCHIVE_HOST:ARCHIVE_BASE_DIR/<ticket_id>/<file_name>
    
    Returns:
        remote_path on success, None on failure
    """
    if paramiko is None:
        logger.error("paramiko not installed; cannot upload to archive server")
        return None
    
    if not ARCHIVE_HOST:
        logger.error("ARCHIVE_HOST not configured")
        return None
    
    if not ARCHIVE_PASSWORD:
        logger.error("ARCHIVE_PASSWORD not configured")
        return None
    
    ticket_dir = str(ticket_id)
    remote_dir = os.path.join(ARCHIVE_BASE_DIR, ticket_dir)
    remote_path = os.path.join(remote_dir, file_name)
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        logger.info(f"Connecting to {ARCHIVE_HOST} as {ARCHIVE_USER}")
        client.connect(
            ARCHIVE_HOST,
            username=ARCHIVE_USER,
            password=ARCHIVE_PASSWORD,
            look_for_keys=False,
            allow_agent=False,
            timeout=30,
        )
        
        sftp = client.open_sftp()
        
        # Ensure directories exist
        for path in (ARCHIVE_BASE_DIR, remote_dir):
            try:
                sftp.listdir(path)
                logger.debug(f"Directory exists: {path}")
            except IOError:
                logger.info(f"Creating remote directory: {path}")
                sftp.mkdir(path)
        
        # Upload file
        logger.info(f"Uploading {len(data)} bytes to {remote_path}")
        bio = io.BytesIO(data)
        sftp.putfo(bio, remote_path)
        
        logger.info(f"✓ Successfully uploaded to {ARCHIVE_HOST}:{remote_path}")
        
        sftp.close()
        client.close()
        
        return remote_path
        
    except Exception as e:
        logger.error(f"Failed to upload {file_name} to archive server: {e}")
        try:
            client.close()
        except Exception:
            pass
        return None


# ============================================================================
# MAIN TOOL
# ============================================================================

@tool
def get_zendesk_attachments(
    ticket_id: int,
    attachment_ids: Optional[List[int]] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Download ALL allowed attachments from a Zendesk ticket and archive them.
    
    Downloads text files, config files, logs, and archives (.tar.gz, .zip).
    Blocks images, videos, executables, and other binary formats.
    
    Saves to: ARCHIVE_HOST:ARCHIVE_BASE_DIR/<ticket_id>/<file_name>
    
    Args:
        ticket_id: Zendesk ticket ID
        attachment_ids: Optional list of specific attachment IDs to download
        limit: Maximum number of attachments to download (default: all)
        offset: Number of attachments to skip (default: 0)
    
    Returns:
        Dict with:
          - ticket_id: Ticket ID
          - total_attachments: Total attachments found
          - downloaded: Number successfully downloaded
          - skipped: Number skipped (blocked types)
          - failed: Number failed to download/upload
          - attachments: List of attachment details
          - archive_host: Archive server hostname
          - archive_base_dir: Base directory on archive server
    """
    ticket_id_int = _coerce_required_int(ticket_id, "ticket_id")
    limit_int = _coerce_int(limit, "limit")
    offset_int = _coerce_int(offset, "offset") or 0
    
    # Log configuration
    logger.info(f"Processing attachments for ticket {ticket_id_int}")
    logger.info(f"Archive: {ARCHIVE_USER}@{ARCHIVE_HOST}:{ARCHIVE_BASE_DIR}/{ticket_id_int}/")
    logger.info(f"Paramiko available: {paramiko is not None}")
    logger.info(f"Archive password configured: {bool(ARCHIVE_PASSWORD)}")
    
    # Fetch ticket comments (attachments are in comments)
    comments_resp = _request(f"/tickets/{ticket_id_int}/comments.json")
    comments: List[Dict[str, Any]] = comments_resp.get("comments", []) if comments_resp else []
    
    if not comments:
        logger.warning(f"No comments found for ticket {ticket_id_int}")
        return {
            "ticket_id": ticket_id_int,
            "total_attachments": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "attachments": [],
            "archive_host": ARCHIVE_HOST,
            "archive_base_dir": ARCHIVE_BASE_DIR,
        }
    
    # Collect all attachments
    all_attachments: List[Dict[str, Any]] = []
    attachment_id_set = set(attachment_ids or [])
    
    for comment in comments:
        comment_id = comment.get("id")
        for att in comment.get("attachments", []) or []:
            att_id = att.get("id")
            
            # Filter by attachment_ids if specified
            if attachment_ids and att_id not in attachment_id_set:
                continue
            
            all_attachments.append({
                "comment_id": comment_id,
                "attachment": att,
            })
    
    logger.info(f"Found {len(all_attachments)} total attachments")
    
    # Apply limit and offset
    if attachment_ids:
        # Preserve order if specific IDs requested
        order_map = {aid: idx for idx, aid in enumerate(attachment_ids)}
        all_attachments.sort(
            key=lambda entry: order_map.get(entry["attachment"].get("id"), float("inf"))
        )
    else:
        if limit_int is not None and limit_int < 1:
            limit_int = 1
        if offset_int:
            all_attachments = all_attachments[offset_int:]
        if limit_int is not None:
            all_attachments = all_attachments[:limit_int]
    
    logger.info(f"Processing {len(all_attachments)} attachments after limit/offset")
    
    # Process each attachment
    results: List[Dict[str, Any]] = []
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0
    
    for entry in all_attachments:
        att = entry["attachment"]
        att_id = att.get("id")
        file_name = att.get("file_name") or f"attachment_{att_id}"
        content_type = att.get("content_type") or ""
        content_url = att.get("content_url")
        file_size = att.get("size", 0)
        
        logger.info(f"Processing: {file_name} (ID: {att_id}, Size: {file_size} bytes)")
        
        # Check if we should download this file
        should_download, reason = _should_download_attachment(file_name, content_type)
        
        if not should_download:
            logger.info(f"  ⊘ Skipped: {reason}")
            skipped_count += 1
            results.append({
                "attachment_id": att_id,
                "comment_id": entry["comment_id"],
                "file_name": file_name,
                "content_type": content_type,
                "size": file_size,
                "created_at": att.get("created_at"),
                "status": "skipped",
                "reason": reason,
                "remote_path": None,
            })
            continue
        
        if not content_url:
            logger.warning(f"  ⚠ No content URL for {file_name}")
            failed_count += 1
            results.append({
                "attachment_id": att_id,
                "comment_id": entry["comment_id"],
                "file_name": file_name,
                "content_type": content_type,
                "size": file_size,
                "status": "failed",
                "reason": "No content URL",
                "remote_path": None,
            })
            continue
        
        # Determine if this is an archive file (use larger max size)
        is_archive = _is_archive_file(file_name, content_type)
        max_size = MAX_BINARY_FILE_SIZE if is_archive else MAX_TEXT_FILE_SIZE
        
        try:
            # Download from Zendesk
            logger.info(f"  ↓ Downloading (max {max_size} bytes)...")
            data, encoding, truncated = _download_attachment_content(content_url, max_size)
            logger.info(f"  ✓ Downloaded {len(data)} bytes{' (truncated)' if truncated else ''}")
            
            # Upload to archive server
            remote_path = _save_attachment_to_archive(ticket_id_int, file_name, data)
            
            if remote_path:
                logger.info(f"  ✓ Archived to: {remote_path}")
                downloaded_count += 1
                
                # Decode text content if not an archive
                body = None
                if not is_archive:
                    try:
                        body = data.decode(encoding, errors="replace")
                    except Exception:
                        body = data.decode("utf-8", errors="replace")
                
                results.append({
                    "attachment_id": att_id,
                    "comment_id": entry["comment_id"],
                    "file_name": file_name,
                    "content_type": content_type,
                    "size": file_size,
                    "created_at": att.get("created_at"),
                    "content_url": content_url,
                    "status": "downloaded",
                    "remote_path": remote_path,
                    "is_archive": is_archive,
                    "truncated": truncated,
                    "body": body,  # None for archives, text content for text files
                })
            else:
                logger.error(f"  ✗ Upload failed")
                failed_count += 1
                results.append({
                    "attachment_id": att_id,
                    "comment_id": entry["comment_id"],
                    "file_name": file_name,
                    "content_type": content_type,
                    "size": file_size,
                    "created_at": att.get("created_at"),
                    "status": "failed",
                    "reason": "Upload to archive server failed",
                    "remote_path": None,
                })
        
        except Exception as e:
            logger.exception(f"  ✗ Error processing {file_name}: {e}")
            failed_count += 1
            results.append({
                "attachment_id": att_id,
                "comment_id": entry["comment_id"],
                "file_name": file_name,
                "content_type": content_type,
                "size": file_size,
                "created_at": att.get("created_at"),
                "status": "failed",
                "reason": f"Exception: {str(e)}",
                "remote_path": None,
            })
    
    # Summary
    logger.info(f"Summary: {downloaded_count} downloaded, {skipped_count} skipped, {failed_count} failed")
    
    return {
        "ticket_id": ticket_id_int,
        "total_attachments": len(all_attachments),
        "downloaded": downloaded_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "attachments": results,
        "archive_host": ARCHIVE_HOST,
        "archive_base_dir": ARCHIVE_BASE_DIR,
    }