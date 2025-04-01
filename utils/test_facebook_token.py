#!/usr/bin/env python3
"""
Facebook Token Test Script

A simple script to test the Facebook token management functionality
in the SocialMediaManager class.

Usage:
    python test_facebook_token.py
"""

import os
import sys
import asyncio
import configparser
from pathlib import Path

# Add parent directory to sys.path to import Myrcat modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from myrcat.managers.social_media import SocialMediaManager
from myrcat.managers.database import DatabaseManager
from myrcat.managers.artwork import ArtworkManager


async def main():
    """Test Facebook token management functionality."""
    # Default paths
    config_path = Path("config.ini")
    if not config_path.exists():
        config_path = Path("conf/config.ini")
        if not config_path.exists():
            config_path = Path("conf/config.ini.example")
            if not config_path.exists():
                print("Error: Could not find config.ini file")
                return 1
    
    print(f"Using config file: {config_path}")
    
    # Load config
    config = configparser.ConfigParser()
    config.read(config_path)
    
    # Initialize managers
    db_path = config.get("general", "database_path", fallback="myrcat.db")
    print(f"Using database file: {db_path}")
    
    db_manager = DatabaseManager(db_path)
    
    # ArtworkManager is required by SocialMediaManager
    publish_dir = config.get("artwork", "publish_directory", fallback="publish")
    cache_dir = config.get("artwork", "cache_directory", fallback="ca")
    default_artwork = config.get("artwork", "default_artwork", 
                                fallback="templates/artwork/default_nowplaying.jpg")
    artwork_manager = ArtworkManager(
        publish_dir=publish_dir,
        cache_dir=cache_dir,
        default_artwork=default_artwork
    )
    
    # Initialize social media manager
    social_manager = SocialMediaManager(
        config=config,
        artwork_manager=artwork_manager,
        db_manager=db_manager
    )
    
    # Step 1: Create database table
    print("\n=== Testing Database Table Creation ===")
    with db_manager._get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='facebook_tokens'"
        )
        if cursor.fetchone():
            print("✅ Facebook tokens table exists in database")
        else:
            print("❌ Facebook tokens table not found")
            print("⚠️ Please initialize the database with schema.sql")
            print("⚠️ Run: cat schema.sql | sqlite3 myrcat.db")
            return 1
    
    # Step 2: Check current token status
    print("\n=== Checking Facebook Token Status ===")
    status = await social_manager.get_facebook_token_status()
    if status.get("valid", False):
        print("✅ Token is valid")
        # Display token details
        token_type = status.get("type", "unknown").upper()
        app_id = status.get("app_id", "Unknown")
        print(f"Token type: {token_type}")
        print(f"App ID: {app_id}")
        
        # Display expiration info
        if "expires_at" in status:
            expires_at = status["expires_at"]
            days_remaining = status.get("days_remaining", 0)
            print(f"Expires at: {expires_at}")
            print(f"Days remaining: {days_remaining}")
    else:
        error = status.get("error", "Unknown error")
        print(f"❌ Token is invalid: {error}")
    
    # Step 3: Store a test token
    print("\n=== Testing Token Storage ===")
    if await social_manager._store_facebook_token("test_token_" + str(os.urandom(4).hex()), 3600):
        print("✅ Test token stored successfully")
    else:
        print("❌ Failed to store test token")
    
    # Step 4: Show token history
    print("\n=== Token History ===")
    try:
        with db_manager._get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM facebook_tokens
            """)
            count = cursor.fetchone()[0]
            print(f"Total tokens in database: {count}")
            
            # Get latest token
            cursor = conn.execute("""
                SELECT id, token_type, created_at, expires_at 
                FROM facebook_tokens
                ORDER BY id DESC
                LIMIT 1
            """)
            latest = cursor.fetchone()
            if latest:
                print(f"Latest token ID: {latest[0]}")
                print(f"Token type: {latest[1]}")
                print(f"Created at: {latest[2]}")
                print(f"Expires at: {latest[3] or 'No expiration'}")
    except Exception as e:
        print(f"❌ Error accessing token history: {e}")
    
    # Step 5: Test validation
    print("\n=== Testing Token Validation ===")
    validation_result = await social_manager._validate_facebook_token()
    print(f"Token validation result: {'✅ Valid' if validation_result else '❌ Invalid'}")
    
    return 0


if __name__ == "__main__":
    asyncio.run(main())