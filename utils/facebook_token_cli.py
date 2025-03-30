#!/usr/bin/env python3
"""
Facebook Token CLI for Myrcat

A command-line interface for managing Facebook tokens within Myrcat.
This is integrated with the main Myrcat application and uses the
SocialMediaManager's token management functionality.

Usage:
    python facebook_token_cli.py status      # Check current token status
    python facebook_token_cli.py refresh     # Force refresh token
    python facebook_token_cli.py history     # Show token history
"""

import os
import sys
import logging
import argparse
import asyncio
import configparser
from datetime import datetime
from pathlib import Path

# Add parent directory to sys.path to import Myrcat modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from myrcat.managers.social_media import SocialMediaManager
from myrcat.managers.database import DatabaseManager
from myrcat.managers.artwork import ArtworkManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

class FacebookTokenCLI:
    """CLI tool for managing Facebook tokens within Myrcat."""
    
    def __init__(self, config_path="config.ini"):
        """Initialize with config path.
        
        Args:
            config_path: Path to Myrcat config file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Initialize required managers
        db_path = self.config.get("general", "database_path", fallback="myrcat.db")
        self.db_manager = DatabaseManager(db_path)
        
        # ArtworkManager is required by SocialMediaManager
        publish_dir = self.config.get("artwork", "publish_directory", fallback="publish")
        cache_dir = self.config.get("artwork", "cache_directory", fallback="ca")
        default_artwork = self.config.get("artwork", "default_artwork", 
                                          fallback="templates/artwork/default_nowplaying.jpg")
        self.artwork_manager = ArtworkManager(
            publish_dir=publish_dir,
            cache_dir=cache_dir,
            default_artwork=default_artwork
        )
        
        # Initialize social media manager
        self.social_manager = SocialMediaManager(
            config=self.config,
            artwork_manager=self.artwork_manager,
            db_manager=self.db_manager
        )
        
        # Override the behavior of validation to avoid RuntimeWarning
        # We'll explicitly validate when needed instead
    
    def _load_config(self):
        """Load the configuration file."""
        if not self.config_path.exists():
            logging.error(f"Config file not found: {self.config_path}")
            sys.exit(1)
            
        config = configparser.ConfigParser()
        config.read(self.config_path)
        return config
    
    async def check_token_status(self):
        """Check and display the current Facebook token status."""
        logging.info("Checking Facebook token status...")
        status = await self.social_manager.get_facebook_token_status()
        
        if not status.get("valid", False):
            error = status.get("error", "Unknown error")
            logging.error(f"❌ Token is invalid: {error}")
            return False
            
        logging.info("✅ Token is valid")
        
        # Display token details
        token_type = status.get("type", "unknown").upper()
        app_id = status.get("app_id", "Unknown")
        logging.info(f"Token type: {token_type}")
        logging.info(f"App ID: {app_id}")
        
        # Display expiration info
        if "expires_at" in status:
            expires_at = status["expires_at"]
            days_remaining = status.get("days_remaining", 0)
            
            logging.info(f"Expires at: {expires_at}")
            logging.info(f"Days remaining: {days_remaining}")
            
            if days_remaining <= 7:
                logging.warning(f"⚠️ Token will expire soon! Only {days_remaining} days remaining")
        
        # Display scopes
        scopes = status.get("scopes", [])
        if scopes:
            logging.info(f"Permissions: {', '.join(scopes)}")
        
        # Display data access expiration
        if "data_access_expires_at" in status:
            logging.info(f"Data access expires at: {status['data_access_expires_at']}")
        
        # Display stored token info
        if "stored_tokens" in status:
            logging.info(f"Stored tokens in database: {status['stored_tokens']}")
            
            if "latest_stored" in status:
                latest = status["latest_stored"]
                logging.info(f"Latest token created at: {latest['created_at']}")
                logging.info(f"Latest token expires at: {latest['expires_at']}")
                
        return True
    
    async def refresh_token(self, force=False):
        """Refresh the Facebook token.
        
        Args:
            force: Force refresh even if not needed
        """
        logging.info("🔄 Refreshing Facebook token...")
        result = await self.social_manager._refresh_facebook_token()
        
        if result:
            logging.info("✅ Token refreshed successfully")
            await self.check_token_status()
        else:
            logging.error("❌ Failed to refresh token")
        
        return result
    
    async def show_token_history(self):
        """Show history of Facebook tokens from the database."""
        if not hasattr(self.social_manager, "db_manager") or not self.social_manager.db_manager:
            logging.error("❌ Database manager not available")
            return False
            
        try:
            with self.db_manager._get_connection() as conn:
                # Check if table exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='facebook_tokens'"
                )
                if not cursor.fetchone():
                    logging.error("❌ No Facebook tokens table found in database")
                    return False
                
                # Get token history
                cursor = conn.execute("""
                    SELECT id, token_type, created_at, expires_at, metadata
                    FROM facebook_tokens
                    ORDER BY id DESC
                """)
                tokens = cursor.fetchall()
                
                if not tokens:
                    logging.info("No token history found")
                    return True
                
                logging.info(f"Found {len(tokens)} tokens in history")
                logging.info("=== Token History ===")
                
                for token in tokens:
                    token_id = token[0]
                    token_type = token[1]
                    created_at = token[2]
                    expires_at = token[3] or "No expiration"
                    metadata = token[4] or "{}"
                    
                    logging.info(f"ID: {token_id}")
                    logging.info(f"Type: {token_type}")
                    logging.info(f"Created: {created_at}")
                    logging.info(f"Expires: {expires_at}")
                    logging.info(f"Metadata: {metadata}")
                    logging.info("-" * 30)
                
            return True
        except Exception as e:
            logging.error(f"❌ Error retrieving token history: {e}")
            return False


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Facebook Token CLI for Myrcat')
    
    # Command subparsers
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check current token status')
    status_parser.add_argument('--config', help='Path to config file', default="config.ini")
    
    # Refresh command
    refresh_parser = subparsers.add_parser('refresh', help='Refresh the token')
    refresh_parser.add_argument('--force', action='store_true', help='Force refresh even if not needed')
    refresh_parser.add_argument('--config', help='Path to config file', default="config.ini")
    
    # History command
    history_parser = subparsers.add_parser('history', help='Show token history')
    history_parser.add_argument('--config', help='Path to config file', default="config.ini")
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    if not args.command:
        print("No command specified. Use --help for usage information.")
        return 1
    
    # Initialize CLI
    cli = FacebookTokenCLI(config_path=args.config)
    
    if args.command == 'status':
        if await cli.check_token_status():
            return 0
        return 1
    
    elif args.command == 'refresh':
        if await cli.refresh_token(force=getattr(args, 'force', False)):
            return 0
        return 1
    
    elif args.command == 'history':
        if await cli.show_token_history():
            return 0
        return 1


if __name__ == '__main__':
    asyncio.run(main())