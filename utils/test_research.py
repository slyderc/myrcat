#!/usr/bin/env python3
"""
Artist Research Test Script

A simple script to test the artist research functionality in Myrcat.

Usage:
    python test_research.py
"""

import os
import sys
import json
import asyncio
import logging
import configparser
from pathlib import Path
from datetime import datetime

# Add parent directory to sys.path to import Myrcat modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from myrcat.models import TrackInfo
from myrcat.managers.database import DatabaseManager
from myrcat.managers.content import ContentGenerator
from myrcat.managers.research import ResearchManager


async def main():
    """Test artist research functionality."""
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Load test configuration
    config = configparser.ConfigParser()
    config.read("conf/config.ini.example")

    # Override configuration for testing
    config["artist_research"] = {
        "enabled": "true",
        "research_max_age": "90",
        "prompts_directory": "templates/prompts",
        "images_directory": "templates/artwork/artists",
    }

    config["web"] = {"research_json": "test_research.json"}

    # Create test database
    db_path = "test_research.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    # Initialize database with schema
    os.system(f"cat schema.sql | sqlite3 {db_path}")

    # Initialize managers
    db_manager = DatabaseManager(db_path)
    content_generator = ContentGenerator(config)
    research_manager = ResearchManager(config, db_manager, content_generator)

    # Create test track
    track = TrackInfo(
        artist="Pink Floyd",
        title="Wish You Were Here",
        album="Wish You Were Here",
        year="1975",
        publisher="Harvest Records",
        isrc="GBAYE7500123",
        image=None,
        starttime=datetime.now().isoformat(),
        duration=320,
        type="song",
        is_song=True,
        media_id="12345",
        program="Classic Rock Hour",
        presenter="DJ Rock",
    )

    # Process the track
    logging.info(f"🧪 Testing artist research for: {track.artist}")
    await research_manager.process_track(track)

    # Verify database entry
    with db_manager._get_connection() as conn:
        cursor = conn.execute(
            "SELECT research_text, created_at FROM artist_research WHERE artist = ?",
            (track.artist,),
        )
        result = cursor.fetchone()

        if result:
            logging.info("✅ Successfully stored research in database")
            logging.info(f"Research text: {result[0][:200]}...")
            logging.info(f"Created at: {result[1]}")
        else:
            logging.error("❌ No research entry found in database")

    # Verify JSON file
    research_json_path = Path(config.get("web", "research_json"))
    if research_json_path.exists():
        with open(research_json_path) as f:
            data = json.load(f)
            logging.info("✅ Successfully created research JSON file")
            logging.info(f"JSON contents: {json.dumps(data, indent=2)}")
    else:
        logging.error("❌ Research JSON file not created")

    # Clean up
    os.remove(db_path)
    if research_json_path.exists():
        os.remove(research_json_path)

    logging.info("🧪 Test complete")


if __name__ == "__main__":
    asyncio.run(main())
