import os
import re
import io
import json
import logging
from typing import Any, Dict, List, Optional

from ncp import tool

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
except ImportError:
    build = None
    MediaIoBaseDownload = None
    Request = None
    Credentials = None

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from creds_loader import get_ssh_config, get_gdrive_config


try:
    import paramiko
except ImportError:
    paramiko = None

log = logging.getLogger(__name__)

GDRIVE_CREDS = get_gdrive_config()

ssh_config = get_ssh_config("ncp_dump")
ARCHIVE_HOST = ssh_config.get("host", "")
ARCHIVE_USER = ssh_config.get("user", "")
ARCHIVE_BASE_DIR = ssh_config.get("base_dir","")
ARCHIVE_PASSWORD = ssh_config.get("password", "")

# Drive readonly scope
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

DOWNLOAD_DIR = os.getenv("TECH_DUMP_DOWNLOAD_DIR", "/tmp/tech-dumps")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# Google Drive auth helpers
# -----------------------------------------------------------------------------
def _get_drive_creds() -> Optional[Credentials]:
    """
    Build Credentials from config.json gdrive section and refresh if needed.
    No browser flow. If token is invalid and can't be refreshed, returns None.
    """
    if Credentials is None or Request is None:
        log.warning("google-auth / google-api-python-client not installed")
        return None

    if not GDRIVE_CREDS:
        log.error("GRDIVE_CREDS is not configured. Paste your token.json into the script.")
        return None

    try:
        creds = Credentials.from_authorized_user_info(GDRIVE_CREDS, SCOPES)
    except Exception as e:
        log.error(f"Failed to construct Credentials from GDRIVE_CREDS: {e}")
        return None

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            log.info("Refreshing expired Google Drive token")
            try:
                creds.refresh(Request())
            except Exception as e:
                log.error(f"Failed to refresh Google Drive token: {e}")
                return None
        else:
            log.error("Google Drive credentials invalid and cannot be refreshed")
            return None

    return creds


def _get_drive_service():
    if build is None or MediaIoBaseDownload is None:
        log.warning("google-api-python-client not installed; cannot talk to Drive")
        return None

    creds = _get_drive_creds()
    if not creds:
        return None

    return build("drive", "v3", credentials=creds)


# -----------------------------------------------------------------------------
# URL parsing / listing
# -----------------------------------------------------------------------------
def _extract_id_from_url(url: str) -> Dict[str, str]:
    """
    Return {"type": "file"/"folder", "id": "..."} or {} if not recognized.

    Supports:
      - https://drive.google.com/file/d/<ID>/view?...
      - https://drive.google.com/uc?export=download&id=<ID>
      - https://drive.google.com/drive/folders/<ID>
    """
    # /file/d/<ID>/
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return {"type": "file", "id": m.group(1)}

    # ?id=<ID> or &id=<ID>
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return {"type": "file", "id": m.group(1)}

    # /folders/<ID>
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if m:
        return {"type": "folder", "id": m.group(1)}

    return {}


def _list_folder_archives(service, folder_id: str) -> List[Dict[str, Any]]:
    """
    List all .zip/.tar/.tar.gz/.tgz files in a Drive folder (non-recursive).
    """
    q = (
        f"'{folder_id}' in parents and "
        "mimeType != 'application/vnd.google-apps.folder' and "
        "("
        "  name contains '.tar' or "
        "  name contains '.tar.gz' or "
        "  name contains '.tgz' or "
        "  name contains '.zip'"
        ") and trashed = false"
    )

    results: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    while True:
        resp = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, md5Checksum)",
                pageToken=page_token,
            )
            .execute()
        )
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


# -----------------------------------------------------------------------------
# Local cache logic
# -----------------------------------------------------------------------------
def _should_redownload(local_path: str, meta: Dict[str, Any]) -> bool:
    """
    Decide if we should redownload the file from Drive.

    For now:
      - if local file missing -> True
      - if Drive 'size' present and doesn't match local size -> True
      - otherwise -> False (reuse)
    """
    if not os.path.exists(local_path):
        return True

    drive_size: Optional[int] = None
    try:
        if meta.get("size") is not None:
            drive_size = int(meta["size"])
    except Exception:
        drive_size = None

    if drive_size is not None:
        local_size = os.path.getsize(local_path)
        if local_size != drive_size:
            log.info(
                f"Local file size mismatch for {local_path}: "
                f"local={local_size}, drive={drive_size}; will redownload."
            )
            return True

    # If we get here, we trust the cached file
    return False


def _download_file(service, file_id: str, name: str) -> str:
    """
    Download a single Drive file to DOWNLOAD_DIR and return the local path.
    """
    request = service.files().get_media(fileId=file_id)
    local_path = os.path.join(DOWNLOAD_DIR, name)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    fh = io.FileIO(local_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            log.info(f"Download {name}: {int(status.progress() * 100)}%")

    log.info(f"Downloaded Drive file {file_id} -> {local_path}")
    return local_path


# -----------------------------------------------------------------------------
# Remote cache logic
# -----------------------------------------------------------------------------
def _remote_file_exists(
    ticket_id: Optional[int],
    filename: str,
    expected_size: Optional[int],
) -> Optional[str]:
    """
    Check if a file already exists on the archive server with the
    expected size. If it does, return the remote_path. If not, return None.

    Does not upload or modify anything.
    """
    if paramiko is None:
        log.warning("paramiko not installed; cannot check remote file existence")
        return None

    tid = str(ticket_id) if ticket_id is not None else "misc"
    remote_dir = os.path.join(ARCHIVE_BASE_DIR, tid)
    remote_path = os.path.join(remote_dir, filename)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ARCHIVE_HOST,
            username=ARCHIVE_USER,
            password=ARCHIVE_PASSWORD,
            look_for_keys=False,
            allow_agent=False,
        )
        sftp = client.open_sftp()

        try:
            st = sftp.stat(remote_path)
            if expected_size is not None and st.st_size == expected_size:
                log.info(
                    f"Remote cache hit: {remote_path} (size={st.st_size}) "
                    f"matches expected_size={expected_size}"
                )
                sftp.close()
                client.close()
                return remote_path
            else:
                log.info(
                    f"Remote file exists but size mismatch: {remote_path} "
                    f"(remote={getattr(st, 'st_size', 'unknown')}, expected={expected_size})"
                )
        except IOError:
            # Does not exist
            log.info(f"Remote file not found: {remote_path}")

        sftp.close()
        client.close()
    except Exception as e:
        log.error(f"Error checking remote file existence: {e}")
        try:
            client.close()
        except Exception:
            pass

    return None

from typing import Any, Dict, Optional
import os

def _push_to_archive_server(
    local_path: str,
    ticket_id: Optional[int],
    expected_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Copy local_path to ARCHIVE_HOST:/home/ravi/ZenDesk-dumps/<ticket_id>/filename
    using SFTP over SSH.

    If ticket_id is None, files are stored under:
      <ARCHIVE_BASE_DIR>/misc/

    Returns:
      {
        "remote_path": <str|None>,
        "skipped_upload": <bool>
      }
    """
    if paramiko is None:
        log.warning("paramiko not installed; cannot upload to archive server")
        return {"remote_path": None, "skipped_upload": False}

    if not os.path.exists(local_path):
        log.error(f"Local file does not exist: {local_path}")
        return {"remote_path": None, "skipped_upload": False}

    # Optional size sanity check
    if expected_size is not None:
        try:
            local_size = os.path.getsize(local_path)
            if local_size != expected_size:
                log.error(
                    f"Local file size mismatch for {local_path}: "
                    f"expected {expected_size}, got {local_size}"
                )
                return {"remote_path": None, "skipped_upload": False}
        except Exception as e:
            log.error(f"Failed to stat local file {local_path}: {e}")
            return {"remote_path": None, "skipped_upload": False}

    tid = str(ticket_id) if ticket_id is not None else "misc"
    remote_dir = os.path.join(ARCHIVE_BASE_DIR, tid)
    filename = os.path.basename(local_path)
    remote_path = os.path.join(remote_dir, filename)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None

    try:
        client.connect(
            ARCHIVE_HOST,
            username=ARCHIVE_USER,
            password=ARCHIVE_PASSWORD,
            look_for_keys=False,
            allow_agent=False,
        )
        sftp = client.open_sftp()

        # Ensure base + ticket dir exist
        for path in (ARCHIVE_BASE_DIR, remote_dir):
            try:
                sftp.listdir(path)
            except IOError:
                sftp.mkdir(path)
                log.info(f"Created remote directory: {path}")

        # Skip upload if identical file already exists
        try:
            st = sftp.stat(remote_path)
            local_size = os.path.getsize(local_path)
            if st.st_size == local_size:
                log.info(
                    f"Remote file already present with same size ({local_size} bytes): "
                    f"{remote_path}; skipping upload."
                )
                return {"remote_path": remote_path, "skipped_upload": True}
        except IOError:
            pass  # file does not exist

        log.info(f"Uploading {local_path} to {remote_path}")
        sftp.put(local_path, remote_path)
        return {"remote_path": remote_path, "skipped_upload": False}

    except Exception as e:
        log.error(f"Failed to push file to archive server: {e}")
        return {"remote_path": None, "skipped_upload": False}

    finally:
        try:
            if sftp:
                sftp.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Tool entrypoint
# -----------------------------------------------------------------------------
@tool
def download_tech_support_from_gdrive(
    url: str,
    ticket_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Given a Google Drive *file* or *folder* URL (including private links
    the embedded account can access), manage tech-support archives:

      1) Get Drive metadata (id, name, size, md5, modifiedTime)
      2) Check remote server for an existing file with matching size
      3) If not found, check local cache
      4) If needed, download from Drive
      5) Ensure remote copy exists (upload once)

    Remote path:
      ARCHIVE_HOST:ARCHIVE_BASE_DIR/<ticket_id>/

    Returns:
        {
          "success": bool,
          "message": str,
          "files": [
            {
              "local_path": str or null,
              "remote_path": str or null,
              "from_cache": bool,
              "skipped_download": bool,
              "skipped_upload": bool,
            },
            ...
          ]
        }
    """
    info = _extract_id_from_url(url)
    if not info:
        return {
            "success": False,
            "message": "URL does not look like a Google Drive file or folder link.",
            "files": [],
        }

    service = _get_drive_service()
    if not service:
        return {
            "success": False,
            "message": "Google Drive API client not available or auth failed.",
            "files": [],
        }

    results: List[Dict[str, Any]] = []

    try:
        if info["type"] == "file":
            meta = (
                service.files()
                .get(
                    fileId=info["id"],
                    fields="id, name, mimeType, size, modifiedTime, md5Checksum",
                )
                .execute()
            )
            name = meta.get("name", f"{info['id']}.bin")

            # parse size
            size: Optional[int] = None
            try:
                if meta.get("size") is not None:
                    size = int(meta["size"])
            except Exception:
                size = None

            # 1) Remote check first
            remote_path = _remote_file_exists(ticket_id, name, size)
            if remote_path:
                results.append({
                    "ticket_id": ticket_id,
                    "drive_type": info["type"],
                    "drive_id": info["id"],
                    "filename": name,
                    "local_path": None,
                    "remote_path": remote_path,
                    "from_cache": True,
                    "skipped_download": True,
                    "skipped_upload": True,
                })

            else:
                # 2) Local cache check / download if needed
                local_path = os.path.join(DOWNLOAD_DIR, name)
                need_redownload = _should_redownload(local_path, meta)
                if need_redownload:
                    local_path = _download_file(service, info["id"], name)
                    from_cache = False
                    skipped_download = False
                else:
                    log.info(f"Using cached local file for {name}")
                    from_cache = True
                    skipped_download = True

                # 3) Ensure remote copy
                archive = _push_to_archive_server(local_path, ticket_id, size)
                remote_path = archive.get("remote_path")
                archive_skipped = bool(archive.get("skipped_upload"))

                skipped_upload = archive_skipped or (from_cache and skipped_download)
                #skipped_upload = archive_skipped

                


                results.append({
                    "ticket_id": ticket_id,
                    "drive_type": info["type"],
                    "drive_id": info["id"],
                    "filename": name,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "from_cache": from_cache,
                    "skipped_download": skipped_download,
                    "skipped_upload": skipped_upload,
                })


        else:
            # Folder case
            files = _list_folder_archives(service, info["id"])
            if not files:
                return {
                    "success": False,
                    "message": "Folder has no .zip/.tar/.tgz/.tar.gz files.",
                    "files": [],
                }

            for f in files:
                name = f.get("name", f"{f['id']}.bin")

                size: Optional[int] = None
                try:
                    if f.get("size") is not None:
                        size = int(f["size"])
                except Exception:
                    size = None

                # 1) Remote check
                remote_path = _remote_file_exists(ticket_id, name, size)
                if remote_path:
                    results.append({
                        "ticket_id": ticket_id,
                        "drive_type": info["type"],     # "folder"
                        "drive_id": info["id"],         # folder id
                        "filename": name,
                        "local_path": None,
                        "remote_path": remote_path,
                        "from_cache": True,
                        "skipped_download": True,
                        "skipped_upload": True,
                    })

                    continue

                # 2) Local cache / download
                local_path = os.path.join(DOWNLOAD_DIR, name)
                need_redownload = _should_redownload(local_path, f)
                if need_redownload:
                    local_path = _download_file(service, f["id"], name)
                    from_cache = False
                    skipped_download = False
                else:
                    log.info(f"Using cached local file for {name}")
                    from_cache = True
                    skipped_download = True

                # 3) Ensure remote copy
                archive = _push_to_archive_server(local_path, ticket_id, size)
                remote_path = archive.get("remote_path")
                archive_skipped = bool(archive.get("skipped_upload"))
                skipped_upload = archive_skipped or (from_cache and skipped_download)
                #skipped_upload = archive_skipped



                results.append({
                    "ticket_id": ticket_id,
                    "drive_type": info["type"],     # "folder"
                    "drive_id": info["id"],         # folder id
                    "filename": name,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "from_cache": from_cache,
                    "skipped_download": skipped_download,
                    "skipped_upload": skipped_upload,
                })


    except Exception as e:
        log.exception("Error downloading from Google Drive")
        return {
            "success": False,
            "message": f"Download failed: {e}",
            "files": results,
        }

    return {
        "success": True,
        "message": (
            f"Processed {len(results)} file(s): remote-first, then local cache, "
            f"then download; synced to {ARCHIVE_HOST}"
        ),
        "files": results,
    }