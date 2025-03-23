"""Core application logic for Myrcat."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from myrcat.config import Config
from myrcat.models import TrackInfo
from myrcat.utils import load_skip_list, clean_title
from myrcat.server import MyriadServer
from myrcat.managers.database import DatabaseManager
from myrcat.managers.artwork import ArtworkManager
from myrcat.managers.playlist import PlaylistManager
from myrcat.managers.history import HistoryManager
from myrcat.managers.social_media import SocialMediaManager
from myrcat.managers.show import ShowHandler


class Myrcat:
    """Main application class for Myriad integration."""

    def __init__(self, config_path: str):
        """Initialize the Myrcat application.
        
        Args:
            config_path: Path to the configuration file
        """
        # Load configuration
        self.config = Config(config_path)
        self.config_parser = self.config.get_raw_config()
        self.last_processed_track = None

        # Setup logging
        log_level = self.config.get("general", "log_level")
        log_file = self.config.get("general", "log_file")
        
        from myrcat.utils import setup_logging
        setup_logging(log_file, log_level)

        logging.info(f"😺 Starting up!")

        # Load skip lists from files
        skip_artists_file = Path(self.config.get("publish_exceptions", "skip_artists_file"))
        skip_titles_file = Path(self.config.get("publish_exceptions", "skip_titles_file"))

        self.skip_artists = load_skip_list(skip_artists_file)
        self.skip_titles = load_skip_list(skip_titles_file)

        # Initialize paths
        self.artwork_incoming = Path(self.config.get("artwork", "incoming_directory"))
        self.artwork_publish = Path(self.config.get("artwork", "publish_directory"))
        self.playlist_json = Path(self.config.get("web", "playlist_json"))
        self.playlist_txt = Path(self.config.get("web", "playlist_txt"))
        self.history_json = Path(self.config.get("web", "history_json"))
        self.history_max_tracks = self.config.getint("web", "history_max_tracks", fallback=30)

        # Add the hashed artwork directory path
        self.artwork_hash_enabled = self.config.getboolean(
            "artwork_hash", "enabled", fallback=True
        )
        self.artwork_hash_dir = Path(self.config.get("artwork_hash", "directory"))

        if self.artwork_hash_enabled:
            logging.info(
                f"🎨 Artwork hashing enabled - directory: {self.artwork_hash_dir}"
            )

        if self.skip_artists:
            logging.warning(f"⚠️ : Artists are being skipped")
        if self.skip_titles:
            logging.warning(f"⚠️ : Titles are being skipped")

        # Initialize components
        self.db = DatabaseManager(self.config.get("general", "database_path"))
        self.playlist = PlaylistManager(
            self.playlist_json, self.playlist_txt, self.artwork_publish
        )
        self.history = HistoryManager(
            self.history_json, self.history_max_tracks
        )
        self.artwork = ArtworkManager(
            self.artwork_incoming,
            self.artwork_publish,
            self.artwork_hash_dir if self.artwork_hash_enabled else None,
        )
        self.social = SocialMediaManager(self.config_parser)
        self.show_handler = ShowHandler(self.config_parser)
        
        logging.info(f"📋 Track history enabled - max tracks: {self.history_max_tracks}")
        
        # Create server
        self.server = MyriadServer(
            host=self.config.get("server", "host"),
            port=self.config.getint("server", "port"),
            validator=self.validate_track_json,
            processor=self.process_new_track
        )

    def should_skip_track(self, title: str, artist: str) -> bool:
        """Check if track should be skipped based on artist or title.
        
        Args:
            title: Track title
            artist: Track artist
            
        Returns:
            True if track should be skipped, False otherwise
        """
        return any([title in self.skip_titles, artist in self.skip_artists])

    async def process_new_track(self, track_json: Dict[str, Any]):
        """Process new track data from Myriad.
        
        Args:
            track_json: Track data from Myriad
        """
        try:
            duration = int(track_json.get("duration", 0))

            # Create TrackInfo object
            track = TrackInfo(
                artist=track_json.get("artist"),
                title=clean_title(track_json["title"]),
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

            logging.info(f'"{track.title}" [{track.year}] - {track.artist}')

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
                        f"⚠️ Adjusting track duration - ({duration}s) is shorter than publish_delay ({delay_seconds}s)"
                    )
                    delay_seconds = max(
                        2, duration - 5
                    )  # Leave at least 5s before next track
                logging.debug(
                    f"⏱️ Delaying track processing for {delay_seconds} seconds"
                )
                await asyncio.sleep(delay_seconds)

            # Process artwork file on web server
            new_filename = None
            artwork_hash = None

            if track.image:
                new_filename = await self.artwork.process_artwork(track.image)
                track.image = new_filename  # Update track object with the new filename

                # Generate hash for the artwork if enabled
                if self.artwork_hash_enabled and track.artist and track.title:
                    artwork_hash = await self.artwork.create_hashed_artwork(
                        new_filename, track.artist, track.title
                    )
                    logging.debug(f"🔑 Generated artwork hash: {artwork_hash}")
            # Always generate a hash even if there's no image
            elif self.artwork_hash_enabled and track.artist and track.title:
                artwork_hash = self.artwork.generate_hash(track.artist, track.title)
                logging.debug(f"🔑 Generated artwork hash (no image): {artwork_hash}")

            # Update playlist file on web server with the artwork hash
            await self.playlist.update_track(track, artwork_hash)
            
            # Update track history
            await self.history.add_track(track, artwork_hash)
            logging.debug(f"📋 Updated track history with {track.artist} - {track.title}")

            # Check for show transition
            await self.show_handler.check_show_transition(track)

            # Update social media but check if track should be skipped
            if self.should_skip_track(track.title, track.artist):
                logging.info(f"⛔️ Skipping socials - filtered in config!")
                return
            else:
                await self.social.update_social_media(track)

            # Log to database
            await self.db.log_db_playout(track)

            self.last_processed_track = track

            logging.debug(f"✅ Published new playout!")
        except Exception as e:
            logging.error(f"💥 Error in track update processing: {e}")

    def validate_track_json(self, track_json: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate incoming track data JSON.
        
        Args:
            track_json: Track data from Myriad
            
        Returns:
            Tuple of (is_valid, message)
        """
        if not track_json:
            return False, "No JSON track data received!"

        required_keys = {"artist", "title", "starttime", "duration", "media_id"}
        if missing := required_keys - track_json.keys():
            return False, f"Missing required fields: {', '.join(missing)}"

        required_fields = ["artist", "title"]
        for field in required_fields:
            if not track_json.get(field):
                return False, f"Missing {field}!  Skipping."

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

    async def run(self):
        """Start the server and run the application."""
        try:
            await self.server.start()
        except KeyboardInterrupt:
            logging.info("🔪 Killing server!")
        except Exception as e:
            logging.error(f"💥 Unexpected error: {e}")
        finally:
            await self.server.stop()