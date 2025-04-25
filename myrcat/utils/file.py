"""File utilities for Myrcat."""

import logging
from pathlib import Path
from typing import List


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


def ensure_directory(directory_path: Path) -> bool:
    """Ensure a directory exists, creating it if needed.
    
    Args:
        directory_path: Path to the directory
        
    Returns:
        True if directory exists or was created, False on error
    """
    try:
        directory_path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"💥 Error creating directory {directory_path}: {e}")
        return False


def cleanup_files(directory: Path, pattern: str, 
                 exclude_filenames: List[str] = None) -> int:
    """Clean up files matching pattern in a directory.
    
    Args:
        directory: Directory to clean
        pattern: Glob pattern for files to remove
        exclude_filenames: Optional list of filenames to keep
    
    Returns:
        Number of files removed
    """
    if exclude_filenames is None:
        exclude_filenames = []
        
    try:
        count = 0
        for file_path in directory.glob(pattern):
            if file_path.name not in exclude_filenames:
                try:
                    file_path.unlink()
                    count += 1
                    logging.debug(f"🧹 Removed file: {file_path.name}")
                except Exception as e:
                    logging.error(f"💥 Error removing file {file_path}: {e}")
        
        return count
    except Exception as e:
        logging.error(f"💥 Error during cleanup: {e}")
        return 0