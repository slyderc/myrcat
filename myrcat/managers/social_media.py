"""Social media manager for Myrcat."""

import logging
import configparser
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Callable, Coroutine, Any, Optional

import pylast
import pylistenbrainz
from atproto import Client as AtprotoClient
from facebook import GraphAPI

from myrcat.models import TrackInfo
from myrcat.exceptions import SocialMediaError
from myrcat.managers.content import ContentGenerator
from myrcat.managers.analytics import SocialMediaAnalytics
from myrcat.managers.artwork import ArtworkManager
from myrcat.managers.database import DatabaseManager


class SocialMediaManager:
    """Handles social media platform updates."""

    def __init__(self, config: configparser.ConfigParser, artwork_manager: ArtworkManager, db_manager: DatabaseManager):
        """Initialize the social media manager.
        
        Args:
            config: ConfigParser object with configuration
            artwork_manager: ArtworkManager instance for handling artwork
            db_manager: DatabaseManager instance for data persistence
        """
        self.config = config
        self.artwork_manager = artwork_manager
        self.db_manager = db_manager
        
        # Track last post time for frequency limiting
        self.last_post_times = {}

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

        # Initialize new components
        self.content_generator = ContentGenerator(config)
        
        # Initialize analytics
        self.analytics = SocialMediaAnalytics(config, db_manager)

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
        self.bluesky_enable_images = self.config.getboolean("bluesky", "enable_images", fallback=True)
        self.bluesky_enable_ai = self.config.getboolean("bluesky", "enable_ai_content", fallback=True)
        self.bluesky_post_frequency = self.config.getint("bluesky", "post_frequency", fallback=1)
        self.bluesky_testing_mode = self.config.getboolean("bluesky", "testing_mode", fallback=False)
        
        if self.bluesky_testing_mode:
            logging.warning(f"🧪 TESTING MODE ENABLED: Bluesky frequency limits disabled - every track will be posted")
        
        logging.debug(f"Bluesky initialized for: {self.bluesky_handle} (images: {'enabled' if self.bluesky_enable_images else 'disabled'}, AI: {'enabled' if self.bluesky_enable_ai else 'disabled'})")

    def setup_facebook(self):
        """Initialize Facebook Graph API client."""
        self.facebook = GraphAPI(self.config["facebook"]["access_token"])
        self.fb_page_id = self.config["facebook"]["page_id"]

    def bluesky_credentials_valid(self) -> bool:
        """Check if Bluesky credentials are valid and complete.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        if not hasattr(self, "bluesky"):
            return False
            
        return (
            hasattr(self, "bluesky_handle") and 
            self.bluesky_handle and 
            hasattr(self, "bluesky_password") and 
            self.bluesky_password
        )

    def _should_post_now(self, platform: str) -> bool:
        """Check if enough time has passed since the last post on this platform.
        
        Args:
            platform: Social media platform name
            
        Returns:
            True if posting is allowed, False otherwise
        """
        # Check for testing mode (bypass frequency limits)
        if platform == "Bluesky" and hasattr(self, "bluesky_testing_mode") and self.bluesky_testing_mode:
            logging.debug(f"🧪 Testing mode: Bypassing frequency limits for {platform}")
            # Still update the timestamp for tracking
            self.last_post_times[platform] = datetime.now()
            return True
            
        # Get platform-specific frequency settings
        frequency_hours = 1  # Default
        
        if platform == "Bluesky" and hasattr(self, "bluesky_post_frequency"):
            frequency_hours = self.bluesky_post_frequency
        
        # Calculate time since last post
        if platform in self.last_post_times:
            hours_since_last = (datetime.now() - self.last_post_times[platform]).total_seconds() / 3600
            if hours_since_last < frequency_hours:
                logging.debug(f"⏱️ Skipping {platform} post (posted {hours_since_last:.1f}h ago, limit is {frequency_hours}h)")
                return False
                
        # Update last post time and allow posting
        self.last_post_times[platform] = datetime.now()
        return True

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
            
        Returns:
            True if post was successful, False otherwise
        """
        if not hasattr(self, "bluesky"):
            return False  # Service not initialized - excluded in config
            
        # Check posting frequency
        if not self._should_post_now("Bluesky"):
            return False
            
        if not self.bluesky_credentials_valid():
            logging.error("💥 Bluesky credentials missing or invalid")
            return False
            
        try:
            # Login for each update as the session might expire
            client = AtprotoClient()
            client.login(self.bluesky_handle, self.bluesky_password)
            
            # Generate post text based on track info
            if self.bluesky_enable_ai:
                post_text = await self.content_generator.generate_track_description(track)
            else:
                # Use standard text if AI is disabled
                post_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
                if track.album:
                    post_text += f"\nFrom the album: {track.album}"
            
            # Create embed with image if available
            embed = None
            
            if self.bluesky_enable_images:
                # Use existing artwork only
                image_path = None
                if track.image:
                    # Get full path to processed artwork
                    artwork_path = self.artwork_manager.publish_dir / track.image
                    if artwork_path.exists():
                        image_path = artwork_path
                
                # Upload image to Bluesky if available
                if image_path and image_path.exists():
                    try:
                        # Upload the image to Bluesky
                        with open(image_path, 'rb') as f:
                            image_data = f.read()
                        blob = client.com.atproto.repo.upload_blob(image_data)
                        
                        # Create image embed
                        embed = {
                            "$type": "app.bsky.embed.images",
                            "images": [{
                                "alt": f"Album artwork for {track.title} by {track.artist}",
                                "image": blob.blob
                            }]
                        }
                    except Exception as img_err:
                        logging.error(f"💥 Error uploading image to Bluesky: {img_err}")
            
            # Generate system hashtags
            sys_hashtags = self.content_generator.generate_hashtags(track)
            
            # Add show name as final hashtag if it exists and isn't already included
            if track.program and track.program.strip():
                # Create proper show hashtag
                show_hashtag = "#" + "".join(word.capitalize() for word in track.program.strip().split())
                # Only add if not already in hashtags
                if show_hashtag not in sys_hashtags:
                    sys_hashtags = sys_hashtags + " " + show_hashtag
            
            # Check if post already has hashtags from AI generation
            if "\n\n#" in post_text:
                # Split post into content and AI hashtags
                main_content, ai_hashtags = post_text.split("\n\n#", 1)
                # Combine AI hashtags with system hashtags
                combined_hashtags = "#" + ai_hashtags.strip() + " " + sys_hashtags
                # Rebuild the post
                post_text = main_content.strip() + f"\n\n{combined_hashtags}"
            else:
                # No AI hashtags, just add system hashtags
                post_text = post_text.strip()
                post_text += f"\n\n{sys_hashtags}"
                
            # Check post length for Bluesky's 300 character limit
            if len(post_text) > 300:
                logging.warning(f"⚠️ Post too long ({len(post_text)} characters) - Bluesky has a 300 character limit")
                # Trim hashtags first if needed
                if "\n\n" in post_text:
                    main_content, hashtags = post_text.split("\n\n", 1)
                    if len(main_content) <= 290:
                        # Keep main content and just the first hashtag
                        first_hashtag = hashtags.split(" ")[0] if " " in hashtags else hashtags
                        post_text = f"{main_content}\n\n{first_hashtag}"
                        logging.debug(f"⚠️ Trimmed hashtags to fit character limit: {post_text}")
                    else:
                        # Content itself is too long, fallback to a simpler message
                        post_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
                        logging.debug(f"⚠️ Using fallback simple message: {post_text}")
                else:
                    # No hashtags to trim, use fallback
                    post_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
                    logging.debug(f"⚠️ Using fallback simple message: {post_text}")
            
            # Log the complete post text for debugging
            logging.debug(f"🔵 Bluesky post content ({len(post_text)} chars): {post_text}")
            logging.debug(f"🔵 Bluesky post has image: {'Yes' if embed else 'No'}")
            
            # Create post with embed
            response = client.com.atproto.repo.create_record({
                "repo": client.me.did,
                "collection": "app.bsky.feed.post",
                "record": {
                    "$type": "app.bsky.feed.post",
                    "text": post_text,
                    "createdAt": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    "embed": embed
                }
            })
            
            # Track post in analytics
            if hasattr(self, "analytics") and hasattr(response, "uri"):
                post_id = response.uri.split("/")[-1]
                await self.analytics.record_post("Bluesky", post_id, track, post_text)
                logging.debug(f"🔵 Recorded Bluesky post to analytics - ID: {post_id}")
            
            logging.debug(f"📒 Updated Bluesky with {'AI' if self.bluesky_enable_ai else 'standard'} content and {'image' if embed else 'no image'}")
            return True
            
        except Exception as e:
            logging.error(f"💥 Bluesky update error: {e}")
            return False

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
                    
    async def check_post_engagement(self):
        """Check engagement metrics for recent posts and update analytics.
        
        This should be called periodically to update engagement metrics.
        """
        if not hasattr(self, "analytics") or not self.analytics.enabled:
            return
            
        try:
            # For now, we'll implement Bluesky engagement checking
            if "Bluesky" not in self.disabled_services and self.bluesky_credentials_valid():
                await self._check_bluesky_engagement()
                
            # Clean up old data
            await self.analytics.cleanup_old_data()
        except Exception as e:
            logging.error(f"💥 Error checking post engagement: {e}")
            
    async def _check_bluesky_engagement(self):
        """Check engagement metrics for recent Bluesky posts."""
        try:
            # Login to Bluesky
            client = AtprotoClient()
            client.login(self.bluesky_handle, self.bluesky_password)
            
            # Get recent posts from analytics
            cutoff_date = (datetime.now() - timedelta(days=7)).isoformat()
            
            with self.db_manager._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT post_id FROM social_media_posts WHERE platform = ? AND posted_at > ?",
                    ("Bluesky", cutoff_date)
                )
                post_ids = [row[0] for row in cursor.fetchall()]
                
            # Check engagement for each post
            for post_id in post_ids:
                try:
                    # Construct post URI
                    post_uri = f"at://{client.me.did}/app.bsky.feed.post/{post_id}"
                    
                    # Get post info including like count
                    post_info = client.app.bsky.feed.get_post_thread({"uri": post_uri})
                    
                    if post_info and post_info.thread and post_info.thread.post:
                        post = post_info.thread.post
                        
                        # Extract engagement metrics
                        likes = getattr(post, "like_count", 0) or 0
                        reposts = getattr(post, "repost_count", 0) or 0
                        replies = len(getattr(post_info.thread, "replies", [])) or 0
                        
                        # Update analytics
                        await self.analytics.update_engagement(
                            "Bluesky", 
                            post_id,
                            {
                                "likes": likes,
                                "shares": reposts,
                                "comments": replies,
                                "clicks": 0  # Bluesky doesn't provide click tracking
                            }
                        )
                except Exception as post_error:
                    logging.warning(f"⚠️ Error checking Bluesky post {post_id}: {post_error}")
        except Exception as e:
            logging.error(f"💥 Error checking Bluesky engagement: {e}")
            
    async def get_social_analytics(self, days: int = 30):
        """Get social media analytics report.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary with analytics data
        """
        if not hasattr(self, "analytics") or not self.analytics.enabled:
            return {"enabled": False}
            
        try:
            # Get top tracks
            top_tracks = await self.analytics.get_top_tracks(days=days, limit=10)
            
            # Get platform stats
            platform_stats = {}
            for platform in ["Bluesky", "Facebook"]:
                if platform not in self.disabled_services:
                    platform_stats[platform] = await self.analytics.get_platform_stats(platform, days=days)
            
            return {
                "enabled": True,
                "days": days,
                "top_tracks": top_tracks,
                "platforms": platform_stats
            }
        except Exception as e:
            logging.error(f"💥 Error getting social analytics: {e}")
            return {
                "enabled": True,
                "error": str(e)
            }