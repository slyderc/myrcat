"""Database manager for Myrcat."""

import logging
import sqlite3
from datetime import datetime
from typing import Optional

from myrcat.models import TrackInfo
from myrcat.exceptions import DatabaseError


class DatabaseManager:
    """Manages SQLite database operations for track logging.
    
    TODO: Potential improvements:
    - Implement database versioning and migrations
    - Add data cleanup/retention policies for old records
    - Add functions to export data for reporting (CSV, JSON)
    - Implement query caching for frequently accessed data
    - Add database connection pooling for performance
    """

    def __init__(self, db_path: str):
        """Initialize the database manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path

        # Register adapter for datetime objects
        sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())

        self.setup_database()

    def setup_database(self):
        """Verify database schema is compatible with current version."""
        try:
            # Expected schema version - update this when schema.sql changes
            EXPECTED_VERSION = 1
            
            with self._get_connection() as conn:
                # Check if version table exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'"
                )
                if not cursor.fetchone():
                    logging.warning("⚠️ Database schema version table not found!")
                    logging.warning("⚠️ Please initialize the database with schema.sql")
                    raise DatabaseError("Database schema not initialized correctly. Run: cat schema.sql | sqlite3 myrcat.db")
                
                # Check version
                cursor = conn.execute("SELECT version FROM db_version WHERE id = 1")
                result = cursor.fetchone()
                if not result:
                    logging.warning("⚠️ Database version record not found!")
                    raise DatabaseError("Database version information missing. Run: cat schema.sql | sqlite3 myrcat.db")
                
                db_version = result[0]
                if db_version != EXPECTED_VERSION:
                    logging.error(f"💥 Database schema version mismatch! Expected: {EXPECTED_VERSION}, Found: {db_version}")
                    logging.error("💥 Please update your database schema with the latest schema.sql file")
                    raise DatabaseError(f"Database schema version mismatch. Expected v{EXPECTED_VERSION}, found v{db_version}")
                
                logging.debug(f"✅ Database schema version {db_version} verified")
                
        except sqlite3.Error as e:
            logging.error(f"💥 Database setup error: {e}")
            raise DatabaseError(f"Failed to verify database schema: {e}")

    def _get_connection(self):
        """Get a SQLite database connection.
        
        Returns:
            SQLite connection object
            
        Raises:
            DatabaseError: If connection fails
        """
        try:
            # Enable foreign keys
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Enable row factory for dict-like access
            conn.row_factory = sqlite3.Row
            
            return conn
        except sqlite3.Error as e:
            logging.error(f"💥 Database connection error: {e}")
            raise DatabaseError(f"Failed to connect to database: {e}")
            
    def get_last_post_time(self, platform: str) -> Optional[datetime]:
        """Get the timestamp of the most recent post for a specific platform.
        
        Args:
            platform: Social media platform name (e.g., 'Bluesky', 'Facebook')
            
        Returns:
            datetime object of the most recent post, or None if no posts found
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT posted_at FROM social_media_posts
                    WHERE platform = ?
                    ORDER BY posted_at DESC
                    LIMIT 1
                    """,
                    (platform,)
                )
                result = cursor.fetchone()
                
                if result and result[0]:
                    # Try to parse the ISO format datetime string
                    try:
                        return datetime.fromisoformat(result[0])
                    except ValueError:
                        logging.error(f"💥 Error parsing datetime from database: {result[0]}")
                        return None
                return None
        except Exception as e:
            logging.error(f"💥 Error getting last post time for {platform}: {e}")
            return None

    async def log_db_playout(self, track: TrackInfo):
        """Log track play to database for SoundExchange reporting.
        
        Args:
            track: TrackInfo object to log
            
        Raises:
            DatabaseError: If database operation fails
        """
        try:
            query = """
                INSERT INTO playouts (
                    artist, title, album, publisher, year, isrc,
                    starttime, duration, media_id, program,
                    presenter, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """
            with self._get_connection() as conn:
                conn.execute(
                    query,
                    (
                        track.artist,
                        track.title,
                        track.album,
                        track.publisher,
                        track.year,
                        track.isrc,
                        track.starttime,
                        track.duration,
                        track.media_id,
                        track.program,
                        track.presenter,
                    ),
                )
                logging.debug(f"📈 Logged to database")
        except Exception as e:
            logging.error(f"💥 Database error: {e}")
            # Add more detailed error logging
            if isinstance(e, sqlite3.OperationalError):
                logging.error(f"💥 SQLite DB error details: {str(e)}")
            raise DatabaseError(f"Failed to log track to database: {e}")