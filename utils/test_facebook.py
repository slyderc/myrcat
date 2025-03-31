#!/usr/bin/env python3
"""Test script for Facebook integration in Myrcat.

This script helps test Facebook integration by:
1. Creating a test TrackInfo object
2. Initializing the SocialMediaManager
3. Testing Facebook posting
4. Checking engagement metrics

Usage:
    python utils/test_facebook.py [--config /path/to/config.ini]
"""

import os
import sys
import argparse
import asyncio
import logging
import configparser
from datetime import datetime
from pathlib import Path

# Add parent directory to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from myrcat.models import TrackInfo
from myrcat.managers.social_media import SocialMediaManager
from myrcat.managers.artwork import ArtworkManager
from myrcat.managers.database import DatabaseManager


def create_test_track():
    """Create a test track for Facebook posting."""
    
    # Create a test track with comprehensive information
    track = TrackInfo(
        id="123",
        artist="Test Artist",
        title="Facebook Integration Test",
        album="Test Album",
        year="2025",
        program="Test Program",
        presenter="Test DJ",
        # Use an example image from the temp directory if available
        image=None  
    )
    
    # Look for sample images in the temp directory
    temp_dir = Path(__file__).parent.parent / "temp"
    if temp_dir.exists():
        for img_file in temp_dir.glob("*.jpg"):
            track.image = img_file.name
            logging.info(f"Using image for test: {img_file}")
            break
    
    return track


async def main():
    """Run Facebook integration test."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test Facebook integration")
    parser.add_argument(
        "--config", 
        help="Path to config file", 
        default=str(Path(__file__).parent / "testprompt.ini.example")
    )
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read(args.config)
    
    # Override configuration for testing
    config["publish_exceptions"]["publish_socials"] = "true"
    
    # Make sure Facebook is enabled
    if "facebook" not in config:
        config["facebook"] = {}
    config["facebook"]["enabled"] = "true"
    config["facebook"]["testing_mode"] = "true"  # Enable testing mode to bypass frequency limits
    
    # Enable AI for testing
    if "ai_content" not in config:
        config["ai_content"] = {}
    config["ai_content"]["testing_mode"] = "true"  # Force AI content for testing
    
    # Enable analytics
    if "social_analytics" not in config:
        config["social_analytics"] = {}
    config["social_analytics"]["enabled"] = "true"
    
    # Setup directories
    base_dir = Path(__file__).parent.parent
    artwork_dir = base_dir / "publish"
    artwork_dir.mkdir(exist_ok=True)
    
    incoming_dir = base_dir / "incoming"
    incoming_dir.mkdir(exist_ok=True)
    
    # Create test DB file
    db_path = base_dir / "test_facebook.db"
    if db_path.exists():
        os.remove(db_path)
    
    logging.info(f"🧪 Starting Facebook integration test using config: {args.config}")
    
    # Initialize managers
    db_manager = DatabaseManager(config, db_path=db_path)
    artwork_manager = ArtworkManager(
        incoming_dir=incoming_dir,
        publish_dir=artwork_dir,
    )
    
    # Create social media manager
    social_manager = SocialMediaManager(
        config=config,
        artwork_manager=artwork_manager,
        db_manager=db_manager
    )
    
    # Create test track
    track = create_test_track()
    logging.info(f"🎵 Created test track: {track.artist} - {track.title}")
    
    # Test Facebook validation
    if social_manager.facebook_credentials_valid():
        logging.info("✅ Facebook credentials valid")
        
        # Test token info
        token_status = await social_manager.get_facebook_token_status()
        if token_status.get("valid"):
            logging.info("✅ Facebook token is valid")
            if "expires_at" in token_status:
                logging.info(f"   Token expires: {token_status['expires_at']}")
                logging.info(f"   Days remaining: {token_status.get('days_remaining', 'unknown')}")
        else:
            logging.error(f"❌ Facebook token invalid: {token_status.get('error', 'Unknown error')}")
    else:
        logging.error("❌ Facebook credentials invalid or incomplete")
        logging.info("Ensure your config has valid Facebook credentials")
        return
    
    # Post to Facebook
    logging.info("📘 Posting test track to Facebook...")
    success = await social_manager.update_facebook(track)
    
    if success:
        logging.info("✅ Successfully posted to Facebook!")
        
        # Check engagement metrics
        logging.info("📊 Checking engagement metrics...")
        await social_manager.check_post_engagement()
        
        # Get social analytics
        analytics = await social_manager.get_social_analytics(days=1)
        if analytics and analytics.get("enabled"):
            if "platforms" in analytics and "Facebook" in analytics["platforms"]:
                fb_stats = analytics["platforms"]["Facebook"]
                logging.info(f"📈 Facebook stats: Posts: {fb_stats.get('total_posts', 0)}, Engagement: {fb_stats.get('engagement_rate', '0%')}")
    else:
        logging.error("❌ Failed to post to Facebook")
    
    logging.info("🧪 Facebook integration test complete")


if __name__ == "__main__":
    asyncio.run(main())