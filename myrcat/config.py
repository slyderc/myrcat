"""Configuration handling for Myrcat."""

import configparser
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from myrcat.exceptions import ConfigurationError


class Config:
    """Configuration handler for Myrcat.
    
    TODO: Potential improvements:
    - Add schema validation for configuration files
    - Support for environment variable overrides
    - Implement configuration profiles (dev, prod, test)
    - Add automatic backup of configuration files
    - Support for remote configuration sources
    - Add configuration change notifications
    """
    
    def __init__(self, config_path: str):
        """Initialize configuration.
        
        Args:
            config_path: Path to the configuration file
            
        Raises:
            ConfigurationError: If the configuration file is not found or invalid
        """
        self.config_parser = configparser.ConfigParser()
        self.config_path = Path(config_path)
        
        if not self.config_path.exists():
            raise ConfigurationError(f"Config file not found: {config_path}")
            
        # Store the file modification time
        self.last_modified_time = self.config_path.stat().st_mtime
        
        try:
            self._load_config()
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration: {e}")
    
    def _load_config(self) -> None:
        """Load the configuration file and apply validations and defaults."""
        self.config_parser.read(self.config_path)
        self._validate_config()
        self._setup_defaults()
    
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
        
    def check_for_changes(self) -> bool:
        """Check if the config file has been modified since last read.
        
        Returns:
            True if the file has been modified, False otherwise
        """
        if not self.config_path.exists():
            logging.warning(f"⚠️ Config file no longer exists: {self.config_path}")
            return False
            
        try:
            # Force stat refresh to get current mtime
            current_mtime = self.config_path.stat().st_mtime
            
            if current_mtime > self.last_modified_time:
                logging.info(f"🔄 Config file has been modified: {self.config_path}")
                return True
                
            return False
        except Exception as e:
            logging.error(f"💥 Error checking config file modification: {e}")
            return False
            
    def reload_if_changed(self) -> bool:
        """Reload the configuration file if it has been modified.
        
        Returns:
            True if the config was reloaded, False otherwise
        """
        if not self.check_for_changes():
            return False
            
        try:
            # Save old config for comparison
            old_config = dict([(section, dict(self.config_parser[section])) 
                              for section in self.config_parser.sections()])
            
            # Reload the config
            self._load_config()
            
            # Update the modification time
            self.last_modified_time = self.config_path.stat().st_mtime
            
            # Log which sections were modified
            self._log_config_changes(old_config)
            
            return True
        except Exception as e:
            logging.error(f"💥 Error reloading config file: {e}")
            return False
            
    def _log_config_changes(self, old_config: Dict[str, Dict[str, str]]) -> None:
        """Log which sections and options were changed in the config.
        
        Args:
            old_config: Dictionary of old configuration values
        """
        # Check for new or modified sections
        for section in self.config_parser.sections():
            if section not in old_config:
                logging.info(f"🆕 New config section added: [{section}]")
                continue
                
            # Check for new or modified options in this section
            for option, value in self.config_parser[section].items():
                if option not in old_config[section]:
                    logging.info(f"🆕 New config option added: [{section}] {option}")
                elif old_config[section][option] != value:
                    logging.info(f"🔄 Config option changed: [{section}] {option}")
                    
        # Check for removed sections
        for section in old_config:
            if not self.config_parser.has_section(section):
                logging.info(f"🗑️ Config section removed: [{section}]")