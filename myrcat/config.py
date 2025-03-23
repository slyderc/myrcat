"""Configuration handling for Myrcat."""

import configparser
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from myrcat.exceptions import ConfigurationError


class Config:
    """Configuration handler for Myrcat."""
    
    def __init__(self, config_path: str):
        """Initialize configuration.
        
        Args:
            config_path: Path to the configuration file
            
        Raises:
            ConfigurationError: If the configuration file is not found or invalid
        """
        self.config_parser = configparser.ConfigParser()
        
        config_file = Path(config_path)
        if not config_file.exists():
            raise ConfigurationError(f"Config file not found: {config_path}")
            
        try:
            self.config_parser.read(config_path)
            self._validate_config()
            self._setup_defaults()
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration: {e}")
    
    def _validate_config(self) -> None:
        """Validate the configuration file has necessary sections and options."""
        required_sections = ["general", "server", "artwork", "web"]
        for section in required_sections:
            if not self.config_parser.has_section(section):
                raise ConfigurationError(f"Missing required section: {section}")
    
    def _setup_defaults(self) -> None:
        """Set up default values for optional configuration."""
        # Add default section for artwork hash if it doesn't exist
        if not self.config_parser.has_section("artwork_hash"):
            self.config_parser.add_section("artwork_hash")
            self.config_parser.set("artwork_hash", "enabled", "true")
            self.config_parser.set(
                "artwork_hash",
                "directory",
                str(Path(self.config_parser["artwork"]["publish_directory"]).parent / "ca"),
            )
            logging.info("🆕 Added default artwork hash configuration")
            
    def get(self, section: str, option: str, fallback: Optional[str] = None) -> str:
        """Get a string configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            fallback: Default value if the option is not found
            
        Returns:
            Configuration value as string
        """
        return self.config_parser.get(section, option, fallback=fallback)
    
    def getint(self, section: str, option: str, fallback: Optional[int] = None) -> int:
        """Get an integer configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            fallback: Default value if the option is not found
            
        Returns:
            Configuration value as integer
        """
        return self.config_parser.getint(section, option, fallback=fallback)
    
    def getboolean(self, section: str, option: str, fallback: Optional[bool] = None) -> bool:
        """Get a boolean configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            fallback: Default value if the option is not found
            
        Returns:
            Configuration value as boolean
        """
        return self.config_parser.getboolean(section, option, fallback=fallback)
    
    def get_path(self, section: str, option: str) -> Path:
        """Get a path configuration value.
        
        Args:
            section: Configuration section
            option: Configuration option
            
        Returns:
            Configuration value as Path object
        """
        return Path(self.get(section, option))
    
    def has_section(self, section: str) -> bool:
        """Check if a section exists in the configuration.
        
        Args:
            section: Configuration section
            
        Returns:
            True if the section exists, False otherwise
        """
        return self.config_parser.has_section(section)
    
    def get_section(self, section: str) -> Dict[str, str]:
        """Get all options from a section.
        
        Args:
            section: Configuration section
            
        Returns:
            Dictionary of options in the section
        """
        if not self.config_parser.has_section(section):
            return {}
        return dict(self.config_parser[section])
    
    def get_raw_config(self) -> configparser.ConfigParser:
        """Get the raw ConfigParser object.
        
        Returns:
            ConfigParser object
        """
        return self.config_parser