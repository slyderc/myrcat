"""Utility functions for Myrcat.

TODO: Potential improvements:
- Add more comprehensive logging with rotation
- Implement performance metrics for monitoring
- Add utility functions for common operations
- Create helper functions for error handling
- Implement more robust JSON handling
- Add data validation utilities
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List


def setup_logging(log_file: str, log_level: str) -> None:
    """Configure logging for the application.
    
    Args:
        log_file: Path to the log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level_obj = getattr(logging, log_level.upper())
    
    # Disable logging for some external modules
    for logger_name in [
        "pylast",
        "urllib3",
        "urllib3.util",
        "urllib3.util.retry",
        "urllib3.connection",
        "urllib3.response",
        "urllib3.connectionpool",
        "urllib3.poolmanager",
        "requests",
        "httpx",
        "httpcore",
        "httpcore.http11",
        "httpcore.connection",
        "httpcore.proxy",
        "charset_normalizer",
        "pylistenbrainz",
    ]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.disabled = True
        logger.propagate = False
        while logger.hasHandlers():
            logger.removeHandler(logger.handlers[0])

    # Clear any existing handlers (in case logging was already configured)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Setup basic configuration with file handler only
    logging.basicConfig(
        filename=log_file,
        level=log_level_obj,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    logging.debug(f"Logging initialized at {log_level} level")


def decode_json_data(data: bytes) -> Dict[str, Any]:
    """Decode and parse JSON track data.
    
    Args:
        data: Raw bytes data
        
    Returns:
        Parsed JSON as a dictionary
        
    Raises:
        json.JSONDecodeError: If JSON parsing fails
    """
    try:
        decoded_data = data.decode("utf-8")
    except UnicodeDecodeError as utf8_error:
        logging.debug(f"UTF-8 decode failed: {utf8_error}, trying cp1252...")
        try:
            decoded_data = data.decode("cp1252")
        except UnicodeDecodeError as cp1252_error:
            logging.debug(
                f"💥 UTF-8 and CP1252 decoding failed: {utf8_error} -- {cp1252_error}"
            )
            decoded_data = data.decode(
                "utf-8", errors="replace"
            )  # Replace invalid characters
            logging.debug("Invalid characters replaced with placeholders.")

    # Perform additional clean-up: strip ctrl-chars except space and replace backslashes
    decoded = "".join(
        char for char in decoded_data if char >= " " or char in ["\n"]
    )
    decoded = decoded.replace("\\", "/")

    try:
        return json.loads(decoded)
    except json.JSONDecodeError as e:
        logging.error(f"💥 JSON parsing failed: {e}\nJSON is: {decoded}")
        # Log the problematic data for debugging
        logging.debug(f"Problematic JSON: {decoded}")
        raise


def load_skip_list(file_path: Path) -> List[str]:
    """Load skip list from file, ignoring comments and empty lines.
    
    Args:
        file_path: Path to the skip list file
        
    Returns:
        List of items to skip
    """
    if not file_path.exists():
        logging.warning(f"⚠️ Skip list file not found: {file_path}")
        return []
    try:
        with open(file_path) as f:
            return [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
    except Exception as e:
        logging.error(f"💥 Error loading skip list {file_path}: {e}")
        return []


def clean_title(title: str) -> str:
    """Clean track title by removing text in parentheses, brackets, etc.
    
    Args:
        title: Original track title
        
    Returns:
        Cleaned track title
    """
    return re.split(r"[\(\[\<]", title)[0].strip()