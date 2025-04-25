"""Data decoding utilities for Myrcat."""

import json
import logging
from typing import Dict, Any


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