"""
Configuration loader module for NCP Zendesk Analysis Agent.

This module provides a centralized way to load configuration from config.json
with fallback to environment variables.
"""
import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

_CONFIG_CACHE: Dict[str, Any] = None


def get_config_path() -> str:
    """Get the absolute path to creds.json.

    Look for creds.json in the same directory as this file
    (ZendeskAnalysisAgent/creds.json).
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "creds.json")
    return config_path


def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.json with fallback to environment variables.
    
    Returns:
        Dictionary containing all configuration values.
    """
    global _CONFIG_CACHE
    
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    
    config_path = get_config_path()
    
    # Try to load from config.json
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
            _CONFIG_CACHE = config
            return config
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
    
    # Fallback: create default config structure with environment variables
    logger.warning(f"Config file not found at {config_path}, using environment variables as fallback")
    
    config = {
        "zendesk": {
            "subdomain": os.getenv("ZENDESK_SUBDOMAIN", ""),
            "email": os.getenv("ZENDESK_EMAIL", ""),
            "api_token": os.getenv("ZENDESK_API_TOKEN", "")
        },
        "ssh": {
            "ncp_dump": {
                "host": os.getenv("NCP_DUMP_SSH_HOST", ""),
                "user": os.getenv("NCP_DUMP_SSH_USER", ""),
                "password": os.getenv("NCP_DUMP_SSH_PASSWORD", ""),
                "base_dir": os.getenv("NCP_DUMP_BASE_DIR", "")
            },
            "archive": {
                "host": os.getenv("ARCHIVE_HOST", ""),
                "user": os.getenv("ARCHIVE_USER", ""),
                "password": os.getenv("ARCHIVE_PASSWORD", ""),
                "base_dir": os.getenv("ARCHIVE_BASE_DIR", "")
            }
        },
        "kb": {
            "dir": os.getenv("KB_DIR", "")
        },
        "gdrive": {
            "token": os.getenv("GDRIVE_TOKEN", ""),
            "refresh_token": os.getenv("GDRIVE_REFRESH_TOKEN", ""),
            "token_uri": os.getenv("GDRIVE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
            "client_id": os.getenv("GDRIVE_CLIENT_ID", ""),
            "client_secret": os.getenv("GDRIVE_CLIENT_SECRET", ""),
            "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": os.getenv("GDRIVE_EXPIRY", "")
        }
    }
    
    
    _CONFIG_CACHE = config
    return config


def get_zendesk_config() -> Dict[str, str]:
    """Get Zendesk configuration."""
    config = load_config()
    return config.get("zendesk", {})


def get_ssh_config(config_key: str = "ncp_dump") -> Dict[str, str]:
    """
    Get SSH configuration for a specific service.
    
    Args:
        config_key: Either 'ncp_dump' or 'archive'
    
    Returns:
        Dictionary with host, user, password, base_dir
    """
    config = load_config()
    ssh_config = config.get("ssh", {}).get(config_key, {})
    return ssh_config


def get_kb_config() -> Dict[str, str]:
    """Get KB configuration."""
    config = load_config()
    return config.get("kb", {})


def get_gdrive_config() -> Dict[str, Any]:
    """Get Google Drive configuration."""
    config = load_config()
    return config.get("gdrive", {})
