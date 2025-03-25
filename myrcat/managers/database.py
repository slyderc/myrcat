"""Database manager for Myrcat."""

import logging
import sqlite3
from datetime import datetime
from typing import Optional

from myrcat.models import TrackInfo
from myrcat.exceptions import DatabaseError


class DatabaseManager:
    """Manages SQLite database operations for track logging."""

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
        """Initialize database schema if not exists."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS playouts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        artist TEXT NOT NULL,
                        title TEXT NOT NULL,
                        album TEXT,
                        year INTEGER,
                        publisher TEXT,
                        isrc TEXT,
                        starttime TEXT,
                        duration INTEGER,
                        media_id TEXT,
                        program TEXT,
                        presenter TEXT,
                        timestamp DATETIME NOT NULL
                    )
                """
                )
        except sqlite3.Error as e:
            logging.error(f"💥 Database setup error: {e}")
            raise DatabaseError(f"Failed to setup database: {e}")

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