"""Utility functions for Myrcat.

This module is maintained for backward compatibility.
Please use the new utility modules in the utils/ package for new code.
"""

import warnings

# Import from new module structure for backward compatibility
from myrcat.utils.logging import setup_logging
from myrcat.utils.decode import decode_json_data
from myrcat.utils.file import load_skip_list
from myrcat.utils.strings import clean_title, normalize_artist_name, clean_artist_name
from myrcat.utils.image import (
    generate_hash, PILLOW_AVAILABLE
)

# Display deprecation warning
warnings.warn(
    "Direct usage of myrcat.utils is deprecated. Please use the new module structure: "
    "from myrcat.utils.module import function",
    DeprecationWarning,
    stacklevel=2
)