#!/usr/bin/env python3
"""
Myrcat - Myriad Playout Cataloging for Now Wave Radio
Author: Clint Dimick
Description: Socket-based service that receives Myriad OCP JSON payloads
Version: 1.0.0
"""

import re
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
import pylast
import pylistenbrainz
from atproto import Client as AtprotoClient
from facebook import GraphAPI


@dataclass
class TrackInfo:
    """Track information storage."""

    artist: str
    title: str
    album: Optional[str]
    year: Optional[str]
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
            f"{'✅' if self.publish_enabled else '⛔️'} Social media publishing {'enabled' if self.publish_enabled else 'disabled'}"
        )

        if self.disabled_services and self.publish_enabled:
            logging.info(f"⚠️ Disabling services: {', '.join(self.disabled_services)}")

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
            logging.error(f"💥 Last.FM setup error: {str(e)}")
            self.lastfm = None

    def setup_listenbrainz(self):
        """Initialize ListenBrainz client."""
        try:
            self.listenbrainz = pylistenbrainz.ListenBrainz()
            self.listenbrainz.set_auth_token(self.config["listenbrainz"]["token"])
            logging.debug(f"Listenbrainz initialized")
        except Exception as e:
            logging.error(f"💥 Listenbrainz setup error: {str(e)}")

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
            logging.debug(f"📒 Updated Last.FM")
        except Exception as e:
            logging.error(f"💥 Last.FM update error: {e}")

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
            logging.debug(f"📒 Updated ListenBrainz")
        except Exception as error:
            logging.error(f"💥 Listenbrainz update error: {error}")

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

            logging.debug(f"📒 Updated Bluesky")
        except Exception as e:
            logging.error(f"💥 Bluesky update error: {e}")

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
            logging.debug(f"📒 Updated Facebook")
        except Exception as e:
            logging.error(f"💥 Facebook update error: {e}")

    async def update_all_platforms(self, track: TrackInfo):
        """Update all configured social media platforms with track debug."""
        if not self.publish_enabled:
            logging.debug("⚠️ Social media publishing is disabled!")
            return

        updates = {
            "Last.FM": self.update_lastfm,
            "ListenBrainz": self.update_listenbrainz,
            "Bluesky": self.update_bluesky,
            "Facebook": self.update_facebook,
        }

        for platform, update_func in updates.items():
            if platform not in self.disabled_services:
                try:
                    await update_func(track)
                except Exception as e:
                    logging.error(f"💥 Error updating {platform}: {e}")


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

    async def log_track(self, track: TrackInfo):
        """Log track play to database for SoundExchange reporting."""
        try:
            query = """
                INSERT INTO playouts (
                    artist, title, album, publisher, year, isrc,
                    starttime, duration, media_id, program,
                    presenter, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """
            with sqlite3.connect(self.db_path) as conn:
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
                logging.error(f"💥 SQLite operational error details: {str(e)}")


class ArtworkManager:
    """Manages artwork file operations."""

    def __init__(self, incoming_dir: Path, publish_dir: Path):
        self.incoming_dir = incoming_dir
        self.publish_dir = publish_dir
        self.current_image: Optional[str] = None
        self.publish_dir.mkdir(parents=True, exist_ok=True)

    async def process_artwork(self, filename: str) -> Optional[str]:
        """Process artwork file with unique name and clean up old files."""
        if not filename:
            return None

        incoming_path = self.incoming_dir / filename

        # Wait for up to 5 seconds for the file to appear
        for _ in range(10):
            if incoming_path.exists():
                try:
                    # Generate unique filename
                    new_filename = f"{uuid.uuid4()}.jpg"
                    publish_path = self.publish_dir / new_filename

                    # Copy file with new name and remove original
                    shutil.copy2(str(incoming_path), str(publish_path))
                    incoming_path.unlink()

                    # Update current image and clean up old files
                    self.current_image = new_filename
                    await self.cleanup_old_artwork()

                    logging.debug(f"🎨 Artwork published: {new_filename}")
                    return new_filename
                except Exception as e:
                    logging.error(f"💥 Error processing artwork: {e}")
                    return None
            await asyncio.sleep(0.5)

        logging.warning(f"⚠️ Artwork missing after waiting: {incoming_path}")
        return None

    async def cleanup_old_artwork(self) -> None:
        """Remove old artwork files from publish directory."""
        try:
            for file in self.publish_dir.glob("*.jpg"):
                # Don't delete the current image file
                if self.current_image and file.name == self.current_image:
                    continue
                try:
                    file.unlink()
                    logging.debug(f"🧹 Removed old artwork: {file.name}")
                except Exception as e:
                    logging.error(f"Error removing old artwork {file.name}: {e}")
        except Exception as e:
            logging.error(f"💥 Error during artwork cleanup: {e}")


class PlaylistManager:
    """Manages playlist.json updates and current track debugrmation."""

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
        except Exception as e:
            logging.error(f"💥 Error updating track: {e}")

    async def update_playlist_json(self, track: TrackInfo) -> None:
        """Update the playlist.json file with current track information."""
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

            logging.debug("💾 Saved new playlist file")
        except Exception as e:
            logging.error(f"💥 Error updating playlist: {e}")


class Myrcat:
    """Main application class for Myriad integration."""

    def __init__(self, config_path: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.last_processed_track = None

        # Setup logging
        log_level = getattr(logging, self.config["general"]["log_level"].upper())

        # Disable logging for some external modules; we'll do the error handling/reporting
        for logger_name in [
            "pylast",
            "urllib3",
            "urllib3.util",
            "urllib3.util.retry",
            "urllib3.connection",
            "urllib3.response",
            "urllib3.connectionpool",
            "urllib3.poolmanager",
            "requests",
            "httpx",
            "httpcore",
            "httpcore.http11",
            "httpcore.connection",
            "httpcore.proxy",
            "charset_normalizer",
            "pylistenbrainz",
        ]:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.CRITICAL)  # really mute them!
            logger.disabled = True
            logger.propagate = False
            while logger.hasHandlers():
                logger.removeHandler(logger.handlers[0])

        logging.basicConfig(
            filename=self.config["general"]["log_file"],
            level=log_level,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        logging.info(f"😺 Starting up!")

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
            logging.warning(f"⚠️ Skip list file not found: {file_path}")
            return []

        try:
            with open(file_path) as f:
                return [
                    line.strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]
        except Exception as e:
            logging.error(f"💥 Error loading skip list {file_path}: {e}")
            return []

    def should_skip_track(self, title: str, artist: str) -> bool:
        """Check if track should be skipped based on artist or title."""
        return any([artist in self.skip_artists, title in self.skip_titles])

    async def process_new_track(self, track_json: Dict[str, Any]):
        """We come here after validating the JSON data."""
        try:
            duration = int(track_json.get("duration", 0))

            # Create TrackInfo object
            track = TrackInfo(
                artist=track_json.get("artist"),
                title=re.split(r"[\(\[\<]", track_json["title"])[0].strip(),
                album=track_json.get("album"),
                year=int(track_json.get("year", 0)) if track_json.get("year") else None,
                publisher=track_json.get("publisher"),
                isrc=track_json.get("ISRC"),
                image=track_json.get("image"),
                starttime=track_json["starttime"],
                duration=duration,
                type=track_json["type"],
                media_id=track_json["media_id"],
                program=track_json.get("program"),
                presenter=track_json.get("presenter"),
            )

            logging.info(f"🎹 {track.title} [{track.year}] - 👨‍🎤 {track.artist}")

            # Check if track should be skipped
            if self.should_skip_track(track.title, track.artist):
                logging.debug(f"⛔️ Skipping - filted in config!")
                return

            # Check for duplicate track, in case we're messing with Myriad OCP
            if (
                self.last_processed_track
                and track.artist == self.last_processed_track.artist
                and track.title == self.last_processed_track.title
            ):
                logging.info(f"⛔️ Skipping - duplicate track!")
                return

            # Delay publishing to the website to accommodate stream delay
            delay_seconds = self.config.getint("general", "publish_delay", fallback=0)

            if delay_seconds > 0:
                # Make sure we don't delay longer than track duration
                if duration and duration < delay_seconds:
                    logging.warning(
                        f"⚠️ Adjusting track duration ({duration}s) is shorter than publish_delay ({delay_seconds}s)"
                    )
                    delay_seconds = max(
                        1, duration - 5
                    )  # Leave at least 5s before next track
                logging.debug(
                    f"⏱️ Delaying track processing for {delay_seconds} seconds"
                )
                await asyncio.sleep(delay_seconds)

            # Process artwork file on web server
            if track.image:
                new_filename = await self.artwork.process_artwork(track.image)
                track.image = new_filename  # Update track object with the new filename

            # Update playlist file on web server
            await self.playlist.update_track(track)

            # Log to database
            await self.db.log_track(track)

            # Update social media
            await self.social.update_all_platforms(track)

            self.last_processed_track = track

            logging.debug(f"✅ Published new playout!")
        except Exception as e:
            logging.error(f"💥 Error in track update processing: {e}")

    def validate_track_json(self, track_json: Dict[str, Any]) -> tuple[bool, str]:
        """Validate incoming track data JSON."""

        # Check required fields exist
        required_fields = ["artist", "title", "starttime", "duration", "media_id"]
        if missing := required_fields - track_json.keys():
            return False, f"⛔️ Missing required fields: {', '.join(missing)}"

        # Skip empty/non-music content
        if not track_json.get("artist"):
            return False, "⛔️ Missing artist data!"

        if not track_json.get("title"):
            return False, "⛔️ Missing title data!"

        # Numeric validations
        try:
            if (duration := int(track_json.get("duration", 0))) < 0:
                return False, f"⚠️ Invalid duration: {duration}"
            if (media_id := int(track_json.get("media_id", 0))) < 0:
                return False, f"⚠️ Invalid media_id: {media_id}"
        except ValueError as e:
            return False, f"💥 Non-numeric value error: {e}"

        # Check string lengths are reasonable
        max_lens = {
            "artist": 256,
            "title": 256,
            "album": 256,
            "publisher": 256,
            "ISRC": 16,
            "program": 128,
            "presenter": 128,
        }

        if oversized := [
            f
            for f, max_len in max_lens.items()
            if track_json.get(f) and len(str(track_json[f])) > max_len
        ]:
            return False, f"Fields exceed max length: {', '.join(oversized)}"

            return True, "Valid track data"  # DEBUG message for logging as 2nd arg.

    async def myriad_connected(self, reader, writer):
        """Handle incoming connections and JSON data."""
        try:
            data = await reader.read()
            if not data:
                return

            # Parse JSON data
            try:
                try:
                    decoded_data = data.decode("utf-8")
                except UnicodeDecodeError:
                    # Specifically handle Windows-1252 encoding
                    decoded_data = data.decode("cp1252")  # Windows-1252 encoding

                # Clean up Windows-style paths in the JSON
                cleaned_data = data.decode().replace("\\", "/")
                track_data = json.loads(cleaned_data)

                # Validate track data
                is_valid, message = self.validate_track_data(track_data)
                if not is_valid:
                    logging.debug(f"Invalid track metadata: {message}")
                    return

                await self.process_track_update(track_data)
            except json.JSONDecodeError as e:
                logging.error(f"💥 Invalid JSON received: {e}\n{data}")
            except Exception as e:
                logging.error(f"💥 Error processing data: {e}")

            writer.close()
            await writer.wait_closed()

        except Exception as e:
            logging.error(f"💥 Error handling client connection: {e}")

    async def start_server(self):
        """Start the socket server."""
        server = await asyncio.start_server(
            self.myriad_connected,
            host=self.config["server"]["host"],
            port=int(self.config["server"]["port"]),
        )

        addr = server.sockets[0].getsockname()
        logging.info(f"🟢 Listening for Myriad on {addr}")

        async with server:
            await server.serve_forever()

    def run(self):
        """Main entry point for running the server."""
        try:
            asyncio.run(self.start_server())
        except KeyboardInterrupt:
            logging.info("🔪 Killing server!")
        except Exception as e:
            logging.error(f"💥 Unexpected error: {e}")


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
        asyncio.run(app.start_server())
    except KeyboardInterrupt:
        logging.info("🔴 Shutting down!")
    except Exception as e:
        logging.error(f"💥 Unexpected error: {e}")
