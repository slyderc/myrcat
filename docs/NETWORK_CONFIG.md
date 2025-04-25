# Network Configuration Implementation

This document details the implementation of network configuration settings in Myrcat. These changes provide configurable network timeouts, retries, and connection parameters throughout the application.

## Overview

The implementation consisted of:

1. A new `[network]` section in configuration files
2. A `NetworkConfig` class to centralize network settings
3. A `retry_async` utility function for standardized retry logic
4. Updates to network-heavy components to use these configurations

## Configuration Settings

The following settings have been added to the configuration file:

```ini
[network]
# Network operation settings
connection_timeout = 10      # Seconds to wait for connections
socket_timeout = 5           # Seconds to wait for socket operations
max_retries = 3              # Default maximum retry count
retry_delay = 2              # Seconds between retries
jitter_factor = 0.1          # Random jitter factor to add to delay (0.0-1.0)
backoff_factor = 2.0         # Exponential backoff multiplier
```

## Implementation Details

### NetworkConfig Class

A new `NetworkConfig` class in `myrcat/utils/network.py` centralizes all network-related settings:

```python
class NetworkConfig:
    """Centralized configuration for network operations."""
    
    def __init__(self, config):
        """Initialize network configuration."""
        self.config = config
        self._load_config()
    
    def _load_config(self):
        """Load network configuration settings."""
        # Connection timeouts
        self.connection_timeout = self.config.getint(
            "network", "connection_timeout", fallback=10
        )
        self.socket_timeout = self.config.getint(
            "network", "socket_timeout", fallback=5
        )
        # ... other settings ...
```

This class provides methods for obtaining timeouts and other settings.

### retry_async Function

The `retry_async` function provides a standardized way to implement retry logic for async operations:

```python
async def retry_async(
    func: Callable, 
    *args, 
    network_config: Optional[NetworkConfig] = None,
    max_retries: Optional[int] = None,
    retry_delay: Optional[int] = None,
    backoff_factor: Optional[float] = None,
    jitter_factor: Optional[float] = None,
    **kwargs
) -> Any:
    """Retry an async function with exponential backoff."""
    # ... implementation ...
```

### Modified Components

The following components were updated to use the network configuration:

1. **MyriadServer**
   - Added socket timeouts to read operations
   - Implemented configurable retry logic for connection errors

2. **ContentGenerator**
   - Added timeouts to Claude API calls
   - Improved error handling for network timeouts

3. **ResearchManager**
   - Added timeouts to Last.fm API calls
   - Implemented retry logic for web scraping operations

4. **SocialMediaManager**
   - Updated Facebook API retry logic to use network settings
   - Improved error handling for timeouts

## Usage Examples

### Configuring Timeouts

```python
# Get timeout from network config or use default
timeout = (
    self.network_config.get_aiohttp_timeout() 
    if self.network_config 
    else 10.0
)

# Use with aiohttp
async with session.get(url, timeout=timeout) as response:
    # ...
```

### Using Retry Logic

```python
from myrcat.utils.network import retry_async

# Simple usage with default settings
result = await retry_async(self._scrape_lastfm_artist_search, artist_name)

# Custom settings
result = await retry_async(
    self._scrape_lastfm_artist_search,
    artist_name,
    max_retries=5,
    retry_delay=1
)
```

## Benefits

These changes provide:

1. **Configurability**: Network parameters can be changed without code modifications
2. **Consistency**: Standard retry and timeout behavior across the application
3. **Resilience**: Better handling of temporary network issues
4. **Tuning**: Ability to optimize network behavior for different environments

## Future Improvements

Potential future enhancements include:

1. **Advanced Retry Policies**: Different retry strategies for different types of errors
2. **Circuit Breakers**: Stop attempts after consistent failures
3. **Network Metrics**: Track network operation success rates and performance
4. **Context-Sensitive Timeouts**: Different timeouts for different operations