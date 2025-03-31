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
    python facebook_token_cli.py generate    # Generate a new token (requires user interaction)
"""

import os
import sys
import logging
import argparse
import asyncio
import configparser
import webbrowser
import json
from datetime import datetime, timedelta
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
        
        # Verify that we have the basic Facebook configuration
        if not self.config.has_section("facebook"):
            logging.error("❌ Facebook configuration section missing")
            return False
            
        if not self.config["facebook"].get("app_id") or not self.config["facebook"].get("app_secret"):
            logging.error("❌ Facebook app_id or app_secret missing from configuration")
            return False
            
        # Check if token exists in database
        if not hasattr(self.social_manager, "_fb_access_token") or not self.social_manager._fb_access_token:
            logging.error("❌ No Facebook token found in database")
            logging.info("Use the 'generate' command to create a new token")
            return False
        
        # Validate the token from the database
        token_info = await self.social_manager._validate_facebook_token_info()
        
        if not token_info:
            logging.error("❌ Failed to validate token: Could not retrieve token information")
            return False
            
        is_valid = token_info.get("is_valid", False)
        if not is_valid:
            error = token_info.get("error", {}).get("message", "Unknown error")
            logging.error(f"❌ Token is invalid: {error}")
            return False
            
        logging.info("✅ Token is valid")
        
        # Display token details
        token_type = token_info.get("type", "unknown").upper()
        app_id = token_info.get("app_id", "Unknown")
        logging.info(f"Token type: {token_type}")
        logging.info(f"App ID: {app_id}")
        
        # Display expiration info
        expires_at = token_info.get("expires_at")
        if expires_at:
            expiry_date = datetime.fromtimestamp(expires_at)
            days_remaining = (expiry_date - datetime.now()).days
            
            logging.info(f"Expires at: {expiry_date.isoformat()}")
            logging.info(f"Days remaining: {days_remaining}")
            
            if days_remaining <= 7:
                logging.warning(f"⚠️ Token will expire soon! Only {days_remaining} days remaining")
        
        # Display scopes
        scopes = token_info.get("scopes", [])
        if scopes:
            logging.info(f"Permissions: {', '.join(scopes)}")
        
        # Display data access expiration
        data_access_expires_at = token_info.get("data_access_expires_at")
        if data_access_expires_at:
            data_access_expiry = datetime.fromtimestamp(data_access_expires_at)
            logging.info(f"Data access expires at: {data_access_expiry.isoformat()}")
        
        # Display database storage information
        try:
            with self.db_manager._get_connection() as conn:
                cursor = conn.execute(
                    """SELECT created_at, expires_at
                       FROM facebook_tokens
                       ORDER BY id DESC LIMIT 1"""
                )
                result = cursor.fetchone()
                if result:
                    created_at, db_expires_at = result
                    logging.info(f"Token created on: {created_at}")
                    logging.info(f"Token expires on (in DB): {db_expires_at or 'Unknown'}")
        except Exception as e:
            logging.warning(f"⚠️ Couldn't retrieve token creation date from database: {e}")
                
        return True
    
    async def refresh_token(self, force=False):
        """Refresh the Facebook token.
        
        Args:
            force: Force refresh even if not needed
        """
        logging.info("🔄 Refreshing Facebook token...")
        
        # Ensure we have a token to refresh
        if not hasattr(self.social_manager, "_fb_access_token") or not self.social_manager._fb_access_token:
            logging.error("❌ No Facebook token found to refresh")
            logging.info("Use the 'generate' command to create a new token")
            return False
        
        # Check if app credentials are configured
        if not self.config.has_section("facebook") or not self.config["facebook"].get("app_id") or not self.config["facebook"].get("app_secret"):
            logging.error("❌ Cannot refresh token: Facebook app_id or app_secret missing")
            return False
            
        # Call the social manager's refresh method
        result = await self.social_manager._refresh_facebook_token()
        
        if result:
            logging.info("✅ Token refreshed successfully")
            # Show the updated token status
            await self.check_token_status()
        else:
            logging.error("❌ Failed to refresh token")
        
        return result
    
    async def generate_token(self):
        """Generate a new Facebook token interactively.
        
        This will open a browser window to the Facebook developer site
        and guide the user through the process of generating a token.
        """
        logging.info("🔑 Generating a new Facebook token...")
        
        # Ensure we have app credentials
        if not self.config.has_section("facebook") or not self.config["facebook"].get("app_id") or not self.config["facebook"].get("app_secret"):
            logging.error("❌ Cannot generate token: Facebook app_id or app_secret missing")
            return False
            
        app_id = self.config["facebook"]["app_id"]
        app_secret = self.config["facebook"]["app_secret"]
        page_id = self.config["facebook"].get("page_id", "")
        
        if not page_id:
            logging.warning("⚠️ No page_id configured - you'll need to specify which page to connect")
        
        # Instruct the user on the process
        logging.info("You'll need to authorize your app to manage your Facebook page")
        logging.info("We'll open the Facebook developer console in your browser")
        logging.info("For detailed instructions on generating a token, see the documentation")
        
        # Ask user to open the Facebook Graph API Explorer
        explorer_url = f"https://developers.facebook.com/tools/explorer/?app_id={app_id}"
        logging.info(f"Opening Facebook Graph API Explorer: {explorer_url}")
        
        try:
            webbrowser.open(explorer_url)
        except Exception as e:
            logging.error(f"❌ Couldn't open browser automatically: {e}")
            logging.info(f"Please open this URL manually: {explorer_url}")
        
        # Guide the user through the process
        logging.info("\nFollow these steps:")
        logging.info("1. Click 'Generate Access Token' and authorize the app")
        logging.info("2. Under 'Add a permission', add these permissions:")
        logging.info("   - pages_manage_posts")
        logging.info("   - pages_read_engagement")
        logging.info("   - pages_show_list")
        logging.info("3. Click 'Generate Access Token' again")
        logging.info("4. Select your page when prompted")
        logging.info("5. Copy the generated token\n")
        
        # Get the token from the user
        try:
            import getpass
            token = getpass.getpass("Enter the generated token: ")
            if not token:
                logging.error("❌ No token entered")
                return False
                
            # Validate the token
            logging.info("Validating token...")
            
            # First update the manager with the token
            # This is needed for validation to work
            self.social_manager.facebook = GraphAPI(token)
            self.social_manager._fb_access_token = token
            
            token_info = await self.social_manager._validate_facebook_token_info(token)
            
            if not token_info or not token_info.get("is_valid", False):
                logging.error("❌ Invalid token provided")
                return False
                
            # Store the token in the database only (not in config)
            logging.info("Storing token in database...")
            result = await self.social_manager._store_facebook_token(
                token, 
                expires_in=token_info.get("expires_at", 0) - int(datetime.now().timestamp()) if token_info.get("expires_at") else None
            )
            
            if result:
                logging.info("✅ Token generated and stored successfully")
                # Show the new token status
                await self.check_token_status()
                return True
            else:
                logging.error("❌ Failed to store token")
                return False
                
        except KeyboardInterrupt:
            logging.info("\nToken generation cancelled")
            return False
        except Exception as e:
            logging.error(f"❌ Error during token generation: {e}")
            return False
    
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
                
                # Get token entries
                cursor = conn.execute("""
                    SELECT id, access_token, created_at, expires_at, metadata
                    FROM facebook_tokens
                    ORDER BY id DESC
                """)
                tokens = cursor.fetchall()
                
                if not tokens:
                    logging.info("No tokens found in database")
                    return True
                
                logging.info(f"Found {len(tokens)} token entries in database")
                logging.info("=== Token History ===")
                
                for token in tokens:
                    token_id = token[0]
                    # Show only first/last few characters of the token for security
                    token_value = token[1]
                    if token_value and len(token_value) > 10:
                        token_preview = f"{token_value[:6]}...{token_value[-4:]}"
                    else:
                        token_preview = "[Invalid token]"
                        
                    created_at = token[2]
                    expires_at = token[3] or "No expiration"
                    metadata = token[4] or "{}"
                    
                    # Parse metadata if it's valid JSON
                    try:
                        metadata_dict = json.loads(metadata)
                        metadata_str = ", ".join([f"{k}: {v}" for k, v in metadata_dict.items()])
                    except:
                        metadata_str = metadata
                    
                    logging.info(f"ID: {token_id}")
                    logging.info(f"Token: {token_preview}")
                    logging.info(f"Created: {created_at}")
                    logging.info(f"Expires: {expires_at}")
                    if metadata_str:
                        logging.info(f"Metadata: {metadata_str}")
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
    
    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate a new token interactively')
    generate_parser.add_argument('--config', help='Path to config file', default="config.ini")
    
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
    
    elif args.command == 'generate':
        if await cli.generate_token():
            return 0
        return 1
    
    elif args.command == 'history':
        if await cli.show_token_history():
            return 0
        return 1


if __name__ == '__main__':
    # Import this here to avoid circular imports
    from facebook import GraphAPI
    asyncio.run(main())