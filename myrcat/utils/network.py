"""Network utilities for Myrcat.

This module provides a centralized configuration for network operations,
including timeouts, retry logic, and connection parameters.
"""

import logging
import asyncio
import random
from typing import Optional, Callable, Any, Dict


class NetworkConfig:
    """Centralized configuration for network operations."""
    
    def __init__(self, config):
        """Initialize network configuration.
        
        Args:
            config: Configuration parser object
        """
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
        
        # Retry settings
        self.max_retries = self.config.getint(
            "network", "max_retries", fallback=3
        )
        self.retry_delay = self.config.getint(
            "network", "retry_delay", fallback=2
        )
        
        # Additional settings
        self.jitter_factor = self.config.getfloat(
            "network", "jitter_factor", fallback=0.1
        )
        self.backoff_factor = self.config.getfloat(
            "network", "backoff_factor", fallback=2.0
        )
    
    def update_from_config(self):
        """Update settings from configuration."""
        self._load_config()
        logging.debug("🔄 Network configuration updated")
    
    def get_timeouts(self) -> Dict[str, float]:
        """Get timeout settings for HTTP requests.
        
        Returns:
            Dictionary of timeout settings
        """
        return {
            "timeout": self.connection_timeout,
            "sock_connect": self.socket_timeout,
            "sock_read": self.socket_timeout
        }
    
    def get_aiohttp_timeout(self) -> float:
        """Get timeout value for aiohttp requests.
        
        Returns:
            Timeout value in seconds
        """
        return float(self.connection_timeout)
    
    def get_socket_timeout(self) -> float:
        """Get timeout value for socket operations.
        
        Returns:
            Timeout value in seconds
        """
        return float(self.socket_timeout)


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
    """Retry an async function with exponential backoff.
    
    Args:
        func: Async function to retry
        *args: Arguments to pass to the function
        network_config: NetworkConfig object for default settings
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries in seconds
        backoff_factor: Factor to increase delay on each retry
        jitter_factor: Random jitter factor to add to delay
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        Result of the function call
        
    Raises:
        Exception: The last exception raised by the function
    """
    # Use provided values or network config defaults
    if network_config:
        max_retries = max_retries or network_config.max_retries
        retry_delay = retry_delay or network_config.retry_delay
        backoff_factor = backoff_factor or network_config.backoff_factor
        jitter_factor = jitter_factor or network_config.jitter_factor
    else:
        # Fallback defaults if no config provided
        max_retries = max_retries or 3
        retry_delay = retry_delay or 2
        backoff_factor = backoff_factor or 2.0
        jitter_factor = jitter_factor or 0.1
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt < max_retries - 1:
                # Calculate delay with exponential backoff and jitter
                delay = retry_delay * (backoff_factor ** attempt)
                jitter = delay * jitter_factor * random.uniform(-1, 1)
                wait_time = delay + jitter
                
                logging.warning(
                    f"⚠️ Network operation failed (attempt {attempt+1}/{max_retries}): {e}"
                )
                logging.debug(f"⏱️ Retrying in {wait_time:.2f}s")
                
                await asyncio.sleep(wait_time)
            else:
                logging.error(f"💥 Network operation failed after {max_retries} attempts: {e}")
                raise
    
    # This should never happen due to the raise above
    raise last_exception