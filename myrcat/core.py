"""Core application logic for Myrcat."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
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
from myrcat.managers.content import ContentGenerator
from myrcat.managers.research import ResearchManager


class Myrcat:
    """Main application class for Myriad integration.

    TODO: Potential improvements:
    - Add health monitoring and status reporting
    - Implement a web dashboard for real-time monitoring
    - Add signal handling for cleaner shutdowns
    - Support configuration hot-reloading through API
    - Add more comprehensive metrics and logging
    - Implement plugin system for extensibility
    """

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

        # Initialize all components using config
        self._initialize_components()

    def _initialize_components(self):
        """Initialize all components using current configuration.

        This method is used both during initialization and when configuration changes.
        It ensures all components are properly configured according to the config file.
        """
        # Load skip lists from files
        skip_artists_file = Path(
            self.config.get("publish_exceptions", "skip_artists_file")
        )
        skip_titles_file = Path(
            self.config.get("publish_exceptions", "skip_titles_file")
        )

        self.skip_artists = load_skip_list(skip_artists_file)
        self.skip_titles = load_skip_list(skip_titles_file)

        # Initialize paths
        self.artwork_incoming = Path(self.config.get("artwork", "incoming_directory"))
        self.artwork_publish = Path(self.config.get("artwork", "publish_directory"))
        self.playlist_json = Path(self.config.get("web", "playlist_json"))
        self.playlist_txt = Path(self.config.get("web", "playlist_txt"))
        self.history_json = Path(self.config.get("web", "history_json"))
        self.history_max_tracks = self.config.getint(
            "web", "history_max_tracks", fallback=30
        )
        self.artwork_cache_dir = Path(self.config.get("artwork", "cache_directory"))

        # Get default artwork path
        default_artwork = self.config.get("artwork", "default_artwork", fallback=None)
        self.default_artwork_path = Path(default_artwork) if default_artwork else None

        # Check if default artwork exists and log appropriate message
        if self.default_artwork_path:
            if self.default_artwork_path.exists():
                logging.debug(
                    f"🎨 Default artwork configured: {self.default_artwork_path}"
                )
            else:
                logging.warning(
                    f"⚠️ Default artwork file not found: {self.default_artwork_path}"
                )
        else:
            logging.warning(f"⚠️ No default artwork configured")

        if self.skip_artists:
            logging.warning(f"⚠️ Artists are being skipped")
        if self.skip_titles:
            logging.warning(f"⚠️ Titles are being skipped")
        logging.info(
            f"📋 Track history enabled - max tracks: {self.history_max_tracks}"
        )

        # Initialize or update components based on whether they already exist
        if not hasattr(self, "db"):
            # First-time initialization of core components
            self.db = DatabaseManager(self.config.get("general", "database_path"))
            self.playlist = PlaylistManager(
                self.playlist_json, self.playlist_txt, self.artwork_publish
            )
            self.history = HistoryManager(self.history_json, self.history_max_tracks)
            self.artwork = ArtworkManager(
                self.artwork_incoming,
                self.artwork_publish,
                self.artwork_cache_dir,
                self.default_artwork_path,
            )

            # Initialize content generator for AI content
            self.content_generator = ContentGenerator(self.config_parser)

            self.social = SocialMediaManager(self.config_parser, self.artwork, self.db)
            self.show_handler = ShowHandler(self.config_parser)

            # Initialize research manager
            self.research = ResearchManager(
                self.config_parser, self.db, self.content_generator
            )

            # Create server
            self.server = MyriadServer(
                host=self.config.get("server", "host"),
                port=self.config.getint("server", "port"),
                validator=self.validate_track_json,
                processor=self.process_new_track,
            )
        else:
            # Update existing components
            # Note: Some components like DatabaseManager can't be updated after creation

            # Update history max tracks setting
            if (
                hasattr(self, "history")
                and self.history.max_tracks != self.history_max_tracks
            ):
                self.history.max_tracks = self.history_max_tracks
                logging.info(
                    f"📋 Updated history max tracks: {self.history_max_tracks}"
                )

            # Update social media manager and its components
            if hasattr(self, "social"):
                self.social.update_from_config()
                logging.debug(f"🔄 Updated social media manager with new configuration")

            # Update show handler
            if hasattr(self, "show_handler"):
                self.show_handler.load_config()
                logging.debug(f"🔄 Updated show handler with new configuration")

            # Update research manager
            if hasattr(self, "research"):
                self.research.load_config()
                logging.debug(f"🔄 Updated research manager with new configuration")

    def _apply_config_changes(self):
        """Apply configuration changes to all components.

        This method is called when the configuration file is reloaded.
        It uses the consolidated _initialize_components method to ensure
        all settings are updated consistently.
        """
        try:
            # Store old default artwork path for comparison
            old_default_artwork = self.default_artwork_path

            # Use the same initialization method for updates to ensure consistency
            self._initialize_components()

            # Check if default artwork path has changed and update ArtworkManager
            if (
                hasattr(self, "artwork")
                and old_default_artwork != self.default_artwork_path
            ):
                # Update the artwork manager with the new default_artwork_path
                self.artwork.default_artwork_path = self.default_artwork_path
                if self.default_artwork_path:
                    log_msg = (
                        f"🎨 Updated default artwork: {self.default_artwork_path}"
                        if self.default_artwork_path.exists()
                        else f"⚠️ Updated default artwork path, but file not found: {self.default_artwork_path}"
                    )
                    logging.info(log_msg)
                else:
                    logging.info("🎨 Default artwork configuration removed")

            logging.info(f"✅ Applied configuration changes to all components")
        except Exception as e:
            logging.error(f"💥 Error applying configuration changes: {e}")

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

            # Normalize type to lowercase and determine if it's a song
            media_type = track_json["type"].lower()
            is_song = media_type == "song"

            # Determine if this is a complete track or needs special handling
            has_artist = bool(track_json.get("artist"))
            has_title = bool(track_json.get("title"))
            is_complete = is_song and has_artist and has_title

            # Get reason for incomplete tracks (for logging)
            reason = None
            if not is_complete:
                if not is_song:
                    reason = f"non-song media type: {track_json['type']}"
                elif not track_json.get("artist"):
                    reason = "missing artist"
                elif not track_json.get("title"):
                    reason = "missing title"
                else:
                    reason = "unknown reason"

                # Use default artwork for incomplete tracks if available
                if self.default_artwork_path and self.default_artwork_path.exists():
                    new_artwork = await self.artwork.use_default_artwork()
                    if new_artwork:
                        logging.debug(f"🎨 Using default artwork due to {reason}")
                        track_json["image"] = new_artwork
                        using_default_artwork = True

            # Safely get values with defaults appropriate for complete/incomplete tracks
            artist = (
                track_json.get("artist", "")
                if is_song
                else (track_json.get("artist") or "")
            )

            # Handle missing title - use a placeholder for empty titles
            raw_title = track_json.get("title", "")
            title = clean_title(raw_title) if raw_title else "[No Title]"

            album = track_json.get("album", "")
            year = int(track_json.get("year", 0)) if track_json.get("year") else None

            # Create TrackInfo object
            track = TrackInfo(
                artist=artist,
                title=title,
                album=album,
                year=year,
                publisher=track_json.get("publisher", ""),
                isrc=track_json.get("ISRC", ""),
                image=track_json.get("image"),
                starttime=track_json["starttime"],
                duration=duration,
                type=track_json["type"],  # Keep original case for display purposes
                is_song=is_song,  # Add normalized boolean flag
                media_id=track_json["media_id"],
                program=track_json.get("program", ""),
                presenter=track_json.get("presenter", ""),
            )

            # Delay publishing to the website to accommodate stream delay
            delay_seconds = self.config.getint("general", "publish_delay", fallback=0)

            # Flag to track if we're using default artwork (set later in the code)
            using_default_artwork = False

            # Check if this is a track that will use default artwork
            if (
                not is_complete
                and self.default_artwork_path
                and self.default_artwork_path.exists()
            ):
                # Reduce delay for tracks with default artwork
                original_delay = delay_seconds

                # Halve the delay, but ensure it's at least 5 seconds
                if delay_seconds > 0:
                    delay_seconds = max(5, delay_seconds // 2)
                    using_default_artwork = True
                    logging.debug(
                        f"⏱️ Reducing publish delay from {original_delay}s to {delay_seconds}s for default artwork"
                    )

            if delay_seconds > 0:
                # Calculate the future timestamp when the track will be published
                now = datetime.now()
                future_time = now + timedelta(seconds=delay_seconds)
                future_timestamp = future_time.strftime("%H:%M:%S")

                logging.info(
                    f'"{track.title}" [{track.year}] - {track.artist}; queued for {future_timestamp}'
                )
            else:
                logging.info(f'"{track.title}" [{track.year}] - {track.artist}')

            # Check for duplicate track, in case we're messing with Myriad OCP
            if (
                self.last_processed_track
                and track.artist == self.last_processed_track.artist
                and track.title == self.last_processed_track.title
            ):
                logging.info(f"⛔️ Skipping - duplicate track!")
                return

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
                    + (
                        " (reduced for default artwork)"
                        if using_default_artwork
                        else ""
                    )
                )
                await asyncio.sleep(delay_seconds)

            # Process artwork and determine further action based on track completeness
            new_filename = None
            artwork_hash = None

            # Process track based on whether it's complete
            if is_complete:
                # Process artwork for complete tracks
                if track.image:
                    # Check if image was already processed (has UUID format)
                    is_processed_image = (
                        isinstance(track.image, str)
                        and len(track.image) > 32
                        and "-" in track.image
                    )

                    if not is_processed_image:
                        new_filename = await self.artwork.process_artwork(track.image)
                        if new_filename:
                            track.image = new_filename
                            # Generate hash for the processed artwork
                            artwork_hash = await self.artwork.create_hashed_artwork(
                                new_filename, track.artist, track.title
                            )
                            logging.debug(f"🔑 Generated artwork hash: {artwork_hash}")
                # Generate hash even without image
                elif track.artist and track.title:
                    artwork_hash = self.artwork.generate_hash(track.artist, track.title)
                    logging.debug(
                        f"🔑 Generated artwork hash (no image): {artwork_hash}"
                    )

                # Full processing for complete tracks
                await self.playlist.update_track(track, artwork_hash)
                await self.history.add_track(track, artwork_hash)
                await self.show_handler.check_show_transition(track)

                # Process artist research
                await self.research.process_track(track)

                # Social media posting (unless skipped)
                if self.should_skip_track(track.title, track.artist):
                    logging.info(f"⛔️ Skipping socials - filtered in config!")
                else:
                    await self.social.update_social_media(track)

                # Database logging
                await self.db.log_db_playout(track)

                logging.debug(
                    f"📋 Updated track history with {track.artist} - {track.title}"
                )
            else:
                # Limited processing for incomplete tracks
                logging.info(f"⚙️ Processing incomplete track ({reason})")

                # Process any provided image if it's not already processed
                if track.image and not (
                    isinstance(track.image, str)
                    and len(track.image) > 32
                    and "-" in track.image
                ):
                    new_filename = await self.artwork.process_artwork(track.image)
                    if new_filename:
                        track.image = new_filename
                        logging.debug(f"🎨 Processed provided image: {new_filename}")

                # Only update playlist files (no hash)
                await self.playlist.update_track(track, None)

                # Still check for show transitions
                await self.show_handler.check_show_transition(track)

                # Log skipped operations
                logging.debug(f"📋 Skipping history update for incomplete track")
                logging.info(f"⛔️ Skipping socials for incomplete track")
                logging.debug(f"💾 Skipping database logging for incomplete track")

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

        # First check if required keys exist (but don't validate content yet)
        basic_required_keys = {"title", "starttime", "duration", "media_id", "type"}
        if missing := basic_required_keys - track_json.keys():
            return False, f"Missing required fields: {', '.join(missing)}"

        # Check if this is a song type
        media_type = track_json.get("type", "").lower()
        is_song = media_type == "song"

        # We'll allow tracks with missing artist or title to be processed
        # with special handling, so we don't validate those fields here anymore

        # However, we'll still warn about missing fields in debug logs
        if is_song and not track_json.get("artist"):
            logging.debug(f"⚠️ Note: Song missing artist - will use special handling")

        if not track_json.get("title"):
            logging.debug(f"⚠️ Note: Track missing title - will use special handling")

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

    async def check_engagement_task(self):
        """Periodic task to check social media engagement."""
        try:
            # Get check frequency from config (in hours)
            check_frequency = self.config.getint(
                "social_analytics", "check_frequency", fallback=6
            )
            check_seconds = check_frequency * 3600  # Convert to seconds

            while True:
                # Wait for the specified interval
                await asyncio.sleep(check_seconds)

                # Check engagement
                try:
                    logging.debug(f"📊 Running scheduled engagement check")
                    await self.social.check_post_engagement()
                except Exception as e:
                    logging.error(f"💥 Error in scheduled engagement check: {e}")
        except asyncio.CancelledError:
            logging.debug("📊 Engagement check task cancelled")
        except Exception as e:
            logging.error(f"💥 Unexpected error in engagement check task: {e}")

    async def check_config_task(self):
        """Periodic task to check for configuration file changes."""
        try:
            # Check every 60 seconds
            check_seconds = 60

            while True:
                # Wait for the interval
                await asyncio.sleep(check_seconds)

                # Check for config changes
                try:
                    if self.config.reload_if_changed():
                        logging.info(f"✅ Configuration reloaded successfully")

                        # Apply configuration changes
                        self._apply_config_changes()
                        logging.debug(
                            f"🔄 Applied configuration changes to all components"
                        )
                except Exception as e:
                    logging.error(f"💥 Error checking for config changes: {e}")
        except asyncio.CancelledError:
            logging.debug("⚙️ Config check task cancelled")
        except Exception as e:
            logging.error(f"💥 Unexpected error in config check task: {e}")

    async def run(self):
        """Start the server and run the application."""
        try:
            # Start engagement check task if analytics is enabled
            analytics_enabled = self.config.getboolean(
                "social_analytics", "enable_analytics", fallback=True
            )

            if analytics_enabled:
                # Start as a background task
                engagement_task = asyncio.create_task(self.check_engagement_task())
                logging.info(f"📊 Social media analytics task started")

            # Start config check task
            config_check_task = asyncio.create_task(self.check_config_task())
            logging.info(f"⚙️ Configuration monitoring task started")

            # Start the server
            await self.server.start()
        except KeyboardInterrupt:
            logging.info("🔪 Killing server!")
        except Exception as e:
            logging.error(f"💥 Unexpected error: {e}")
        finally:
            # Cancel analytics task if it exists
            if "engagement_task" in locals():
                engagement_task.cancel()
                try:
                    await engagement_task
                except asyncio.CancelledError:
                    pass

            # Cancel config check task
            if "config_check_task" in locals():
                config_check_task.cancel()
                try:
                    await config_check_task
                except asyncio.CancelledError:
                    pass

            await self.server.stop()
