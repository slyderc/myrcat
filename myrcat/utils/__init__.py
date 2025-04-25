"""Utility module for Myrcat providing common functionality."""

# Import and re-export main utilities for backward compatibility
from .logging import setup_logging
from .decode import decode_json_data
from .file import load_skip_list, ensure_directory, cleanup_files
from .strings import (clean_title, normalize_artist_name, clean_artist_name, 
                    generate_artist_variations, generate_artist_title_hash)
from .image import (wait_for_file, copy_file, generate_uuid_filename, 
                  generate_hash, resize_image, download_image, 
                  PILLOW_AVAILABLE)
from .network import NetworkConfig, retry_async

# Define what's available for "from myrcat.utils import *"
__all__ = [
    # Logging utilities
    'setup_logging',
    
    # Data decoding
    'decode_json_data',
    
    # File operations
    'load_skip_list', 
    'ensure_directory',
    'cleanup_files',
    
    # String processing
    'clean_title',
    'normalize_artist_name',
    'clean_artist_name',
    'generate_artist_variations',
    'generate_artist_title_hash',
    
    # Image processing
    'wait_for_file',
    'copy_file',
    'generate_uuid_filename',
    'generate_hash',
    'resize_image',
    'download_image',
    'PILLOW_AVAILABLE',
    
    # Network utilities
    'NetworkConfig',
    'retry_async',
]