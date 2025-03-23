"""Social media manager for Myrcat."""

import logging
import configparser
import time
from datetime import datetime, timezone
from typing import Dict, Callable, Coroutine, Any

import pylast
import pylistenbrainz
from atproto import Client as AtprotoClient
from facebook import GraphAPI

from myrcat.models import TrackInfo
from myrcat.exceptions import SocialMediaError


class SocialMediaManager:
    """Handles social media platform updates."""

    def __init__(self, config: configparser.ConfigParser):
        """Initialize the social media manager.
        
        Args:
            config: ConfigParser object with configuration
        """
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
        """Update Last.FM with current track.
        
        Args:
            track: TrackInfo object containing track information
        """
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
        """Update ListenBrainz with current track.
        
        Args:
            track: TrackInfo object containing track information
        """
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
        """Update Bluesky with current track.
        
        Args:
            track: TrackInfo object containing track information
        """
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
        """Update Facebook page with current track.
        
        Args:
            track: TrackInfo object containing track information
        """
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

    async def update_social_media(self, track: TrackInfo):
        """Update all configured social media platforms with track debug.
        
        Args:
            track: TrackInfo object containing track information
        """
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