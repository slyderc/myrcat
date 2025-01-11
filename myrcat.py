#!/usr/bin/env python3
"""
Myrcat - Myriad Playout Cataloging for Now Wave Radio
Author: Clint Dimick
Description: Socket-based service that receives Myriad OCP JSON payloads
Version: 1.0.0
"""

import sys
import asyncio
import configparser
import time
import json
import uuid
import logging
import sqlite3
import shutil
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Social media modules
import pylistenbrainz
from atproto import Client as AtprotoClient
from facebook import GraphAPI
import pylast


@dataclass
class TrackInfo:
    """Track information storage."""

    artist: str
    title: str
    album: Optional[str]
    publisher: Optional[str]
    isrc: Optional[str]
    image: Optional[str]
    starttime: str
    duration: int
    type: str
    media_id: str
    program: Optional[str]
    presenter: Optional[str]
    timestamp: datetime = datetime.now()


class SocialMediaManager:
    """Handles social media platform updates."""

    def __init__(self, config: configparser.ConfigParser):
        self.config = config

        # Check if social media publishing is enabled
        self.publish_enabled = self.config.getboolean(
            "publish_exceptions", "publish_socials", fallback=True
        )

        # Get list of disabled services (comma-separated)
        disabled_str = self.config.get(
            "publish_exceptions", "disable_services", fallback=""
        ).strip()

        if not disabled_str or disabled_str.lower() == "none":
            self.disabled_services = []
        else:
            self.disabled_services = [
                s.strip() for s in disabled_str.split(",") if s.strip()
            ]

        logging.info(
            f"ALL social media publishing {'enabled' if self.publish_enabled else 'disabled'}"
        )
        if self.disabled_services:
            logging.info(
                f"Individual disabled services: {', '.join(self.disabled_services)}"
            )

        # Initialize enabled services
        if self.publish_enabled:
            if "LastFM" not in self.disabled_services:
                self.setup_lastfm()
            if "ListenBrainz" not in self.disabled_services:
                self.setup_listenbrainz()
            if "Bluesky" not in self.disabled_services:
                self.setup_bluesky()
            if "Facebook" not in self.disabled_services:
                self.setup_facebook()

    def setup_lastfm(self):
        """Initialize Last.FM API connection using pylast."""
        try:
            lastfm_config = self.config["lastfm"]
            self.lastfm = pylast.LastFMNetwork(
                api_key=lastfm_config["api_key"],
                api_secret=lastfm_config["api_secret"],
                username=lastfm_config["username"],
                password_hash=lastfm_config[
                    "password"
                ],  # Password is already hashed in config
            )
            logging.debug(f"Last.FM initialized for user: {lastfm_config['username']}")
        except Exception as e:
            logging.error(f"Last.FM setup error: {str(e)}")
            self.lastfm = None

    def setup_listenbrainz(self):
        """Initialize ListenBrainz client."""
        try:
            self.listenbrainz = pylistenbrainz.ListenBrainz()
            self.listenbrainz.set_auth_token(self.config["listenbrainz"]["token"])
            logging.debug(f"Listenbrainz initialized")
        except Exception as e:
            logging.error(f"Listenbrainz setup error: {str(e)}")

    def setup_bluesky(self):
        """Initialize Bluesky client."""
        self.bluesky = AtprotoClient()
        self.bluesky_handle = self.config["bluesky"]["handle"]
        self.bluesky_password = self.config["bluesky"]["app_password"]

    def setup_facebook(self):
        """Initialize Facebook Graph API client."""
        self.facebook = GraphAPI(self.config["facebook"]["access_token"])
        self.fb_page_id = self.config["facebook"]["page_id"]

    async def update_lastfm(self, track: TrackInfo):
        """Update Last.FM with current track."""
        if not hasattr(self, "lastfm"):
            return  # Service not initialized - excluded in config

        lastfm_timestamp = int(datetime.now(timezone.utc).timestamp())
        try:
            self.lastfm.scrobble(
                artist=track.artist, title=track.title, timestamp=lastfm_timestamp
            )
            logging.info(f"Updated Last.FM: {track.artist} - {track.title}")
        except Exception as e:
            logging.error(f"Last.FM update error: {e}")

    async def update_listenbrainz(self, track: TrackInfo):
        """Update ListenBrainz with current track."""
        if not hasattr(self, "listenbrainz"):
            return  # Service not initialized - excluded in config

        try:
            lb_listen = pylistenbrainz.Listen(
                track_name=track.title,
                artist_name=track.artist,
                listened_at=int(time.time()),
            )
            lb_response = self.listenbrainz.submit_single_listen(lb_listen)
            logging.info(f"Updated ListenBrainz: {track.artist} - {track.title}")
        except Exception as error:
            logging.error(f"Listenbrainz update error: {error}")

    async def update_bluesky(self, track: TrackInfo):
        """Update Bluesky with current track."""
        if not hasattr(self, "bluesky"):
            return  # Service not initialized - excluded in config

        try:
            # Login for each update as the session might expire
            client = AtprotoClient()
            client.login(self.bluesky_handle, self.bluesky_password)
            post_text = (
                f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
            )
            if track.album:
                post_text += f"\nFrom the album: {track.album}"

            # Create post (this is synchronous - ATProto handles this internally)
            client.send_post(text=post_text)

            logging.info(f"Updated Bluesky: {track.artist} - {track.title}")
        except Exception as e:
            logging.error(f"Bluesky update error: {e}")

    async def update_facebook(self, track: TrackInfo):
        """Update Facebook page with current track."""
        if not hasattr(self, "facebook"):
            return  # Service not initialized - excluded in config

        try:
            message = f"Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
            if track.album:
                message += f"\nAlbum: {track.album}"
            if track.program:
                message += f"\nProgram: {track.program}"
            if track.presenter:
                message += f"\nPresenter: {track.presenter}"

            self.facebook.put_object(
                parent_object=self.fb_page_id, connection_name="feed", message=message
            )
            logging.info(f"Updated Facebook: {track.artist} - {track.title}")
        except Exception as e:
            logging.error(f"Facebook update error: {e}")

    async def update_all_platforms(self, track: TrackInfo):
        """Update all configured social media platforms with track info."""
        if not self.publish_enabled:
            logging.debug("Social media publishing is disabled!")
            return

        platforms = [
            (self.update_lastfm, "Last.FM"),
            (self.update_listenbrainz, "ListenBrainz"),
            (self.update_bluesky, "Bluesky"),
            (self.update_facebook, "Facebook"),
        ]

        for update_func, platform_name in platforms:
            if platform_name in self.disabled_services:
                logging.debug(f"Skipping {platform_name} - disabled in config!")
                continue
            try:
                await update_func(track)
            except Exception as e:
                logging.error(f"Error updating {platform_name}: {e}")


class DatabaseManager:
    """Manages SQLite database operations for track logging."""

    def __init__(self, db_path: str):
        self.db_path = db_path

        # Register adapter for datetime objects
        sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())

        self.setup_database()

    def setup_database(self):
        """Initialize database schema if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    album TEXT,
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

    async def log_track(self, track: TrackInfo):
        """Log track play to database for SoundExchange reporting."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO playouts (
                        artist, title, album, publisher, isrc,
                        starttime, duration, media_id, program,
                        presenter, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        track.artist,
                        track.title,
                        track.album,
                        track.publisher,
                        track.isrc,
                        track.starttime,
                        track.duration,
                        track.media_id,
                        track.program,
                        track.presenter,
                        track.timestamp,
                    ),
                )
            logging.info(f"Logged track to database: {track.artist} - {track.title}")
        except Exception as e:
            logging.error(f"Database error: {e}")
            # Add more detailed error logging
            if isinstance(e, sqlite3.OperationalError):
                logging.error(f"SQLite operational error details: {str(e)}")


class ArtworkManager:
    """Manages artwork file operations."""

    def __init__(self, incoming_dir: Path, publish_dir: Path):
        self.incoming_dir = incoming_dir
        self.publish_dir = publish_dir
        self.publish_dir.mkdir(parents=True, exist_ok=True)

    async def process_artwork(self, filename: str) -> Optional[str]:
        """Check for artwork file and move it to publish directory."""
        if not filename:
            return None

        incoming_path = self.incoming_dir / filename

        # Wait for up to 5 seconds for the file to appear
        for _ in range(10):
            if incoming_path.exists():
                try:
                    new_filename = f"{uuid.uuid4()}.jpg"
                    publish_path = self.publish_dir / new_filename

                    # Copy file with new name
                    shutil.copy2(str(incoming_path), str(publish_path))
                    incoming_path.unlink()  # Remove original file
                    logging.info(
                        f"Copied artwork to publish directory as: {new_filename}"
                    )
                    return new_filename
                except Exception as e:
                    logging.error(f"Error processing artwork: {e}")
                    return None
            await asyncio.sleep(0.5)

        logging.warning(f"Artwork file not found after waiting: {incoming_path}")
        return None


class PlaylistManager:
    """Manages playlist.json updates and current track information."""

    def __init__(self, playlist_path: Path, artwork_publish_path: Path):
        """Initialize PlaylistManager.

        Args:
            playlist_path: Path to the playlist.json file
        """
        self.playlist_path = playlist_path
        self.artwork_publish_path = artwork_publish_path
        self.current_track: Optional[TrackInfo] = None

        # Ensure parent directory exists
        self.playlist_path.parent.mkdir(parents=True, exist_ok=True)

    async def update_track(self, track: TrackInfo) -> None:
        """Update current track and playlist file.

        Args:
            track: TrackInfo object containing new track information
        """
        try:
            self.current_track = track
            await self.update_playlist_json(track)
            logging.info(f"Updated current track: {track.artist} - {track.title}")
        except Exception as e:
            logging.error(f"Error updating track: {e}")

    async def update_playlist_json(self, track: TrackInfo) -> None:
        """Update the playlist.json file with current track information.

        Args:
            track: TrackInfo object containing track information to write
        """
        try:
            playlist_data = {
                "artist": track.artist,
                "title": track.title,
                "album": track.album,
                "image": f"/player/publish/{track.image}" if track.image else None,
                "program_title": track.program,
                "presenter": track.presenter,
            }

            # Write JSON file with proper indentation for readability
            with open(self.playlist_path, "w") as f:
                json.dump(playlist_data, f, indent=4)

            logging.info("Updated playlist successfully")

            # Now safe to clean up old artwork files
            await self.cleanup_old_artwork()

        except Exception as e:
            logging.error(f"Error updating playlist: {e}")

    async def cleanup_old_artwork(self) -> None:
        """Remove old artwork files from publish directory."""
        try:
            current_image = self.current_track.image if self.current_track else None

            for file in self.artwork_publish_path.glob("*.jpg"):
                # Don't delete the current image file
                if current_image and file.name == current_image:
                    continue
                try:
                    file.unlink()
                    logging.debug(f"Removed old artwork: {file.name}")
                except Exception as e:
                    logging.error(f"Error removing old artwork {file.name}: {e}")

            logging.info("Artwork cleanup completed")
        except Exception as e:
            logging.error(f"Error during artwork cleanup: {e}")


class Myrcat:
    """Main application class for Myriad integration."""

    def __init__(self, config_path: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        # Setup logging
        log_level = getattr(logging, self.config["general"]["log_level"].upper())
        logging.basicConfig(
            filename=self.config["general"]["log_file"],
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        logging.getLogger("pylast").setLevel(logging.WARNING)

        # Load skip lists from files
        skip_artists_file = Path(self.config["publish_exceptions"]["skip_artists_file"])
        skip_titles_file = Path(self.config["publish_exceptions"]["skip_titles_file"])

        self.skip_artists = self.load_skip_list(skip_artists_file)
        self.skip_titles = self.load_skip_list(skip_titles_file)

        # Initialize paths
        self.artwork_incoming = Path(self.config["artwork"]["incoming_directory"])
        self.artwork_publish = Path(self.config["artwork"]["publish_directory"])
        self.playlist_path = Path(self.config["web"]["playlist_path"])

        # Initialize components
        self.db = DatabaseManager(self.config["general"]["database_path"])
        self.playlist = PlaylistManager(self.playlist_path, self.artwork_publish)
        self.artwork = ArtworkManager(self.artwork_incoming, self.artwork_publish)
        self.social = SocialMediaManager(self.config)

    def load_skip_list(self, file_path: Path) -> list:
        """Load skip list from file, ignoring comments and empty lines."""
        if not file_path.exists():
            logging.warning(f"Skip list file not found: {file_path}")
            return []

        try:
            with open(file_path) as f:
                return [
                    line.strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]
        except Exception as e:
            logging.error(f"Error loading skip list {file_path}: {e}")
            return []

    def should_skip_track(self, artist: str, title: str) -> bool:
        """Check if track should be skipped based on artist or title."""
        return any([artist in self.skip_artists, title in self.skip_titles])

    async def process_track_update(self, track_data: Dict[str, Any]):
        """Process a track update from Myriad."""
        try:
            # Check if track should be skipped
            if self.should_skip_track(track_data["artist"], track_data["title"]):
                logging.info(
                    f"Skipping track due to filter: {track_data['artist']} - {track_data['title']}"
                )
                return

            # Convert duration to integer
            duration = int(track_data.get("duration", 0))

            # Create TrackInfo object
            track = TrackInfo(
                artist=track_data["artist"],
                title=track_data["title"],
                album=track_data.get("album"),
                publisher=track_data.get("publisher"),
                isrc=track_data.get("ISRC"),
                image=track_data.get("image"),
                starttime=track_data["starttime"],
                duration=duration,
                type=track_data["type"],
                media_id=track_data["media_id"],
                program=track_data.get("program"),
                presenter=track_data.get("presenter"),
            )

            # Process artwork if provided
            if track.image:
                await self.artwork.process_artwork(track.image)

            # Update playlist
            await self.playlist.update_track(track)

            # Log to database
            await self.db.log_track(track)

            # Update social media
            await self.social.update_all_platforms(track)

            logging.info(f"Processed track update: {track.artist} - {track.title}")
        except Exception as e:
            logging.error(f"Error in track update processing: {e}")

    async def handle_client(self, reader, writer):
        """Handle incoming connection and JSON data."""
        try:
            data = await reader.read()
            if not data:
                return

            # Parse JSON data
            try:
                track_data = json.loads(data.decode())
                await self.process_track_update(track_data)
            except json.JSONDecodeError as e:
                logging.error(f"Invalid JSON received: {e}\n{data}")
            except Exception as e:
                logging.error(f"Error processing data: {e}")

            writer.close()
            await writer.wait_closed()

        except Exception as e:
            logging.error(f"Error handling client connection: {e}")

    async def run_server(self):
        """Start the socket server."""
        server = await asyncio.start_server(
            self.handle_client,
            host=self.config["server"]["host"],
            port=int(self.config["server"]["port"]),
        )

        addr = server.sockets[0].getsockname()
        logging.info(f"Serving on {addr}")

        async with server:
            await server.serve_forever()

    def run(self):
        """Main entry point for running the server."""
        try:
            asyncio.run(self.run_server())
        except KeyboardInterrupt:
            logging.info("Server shutdown requested")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Myrcat - Myriad Cataloger")
    parser.add_argument(
        "-c",
        "--config",
        default="config.ini",
        help="Path to config file (default: ./config.ini)",
    )

    args = parser.parse_args()

    if not Path(args.config).exists():
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    app = Myrcat(args.config)
    try:
        asyncio.run(app.run_server())
    except KeyboardInterrupt:
        logging.info("Server shutdown requested")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
