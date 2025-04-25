"""Logging configuration for Myrcat."""

import logging


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