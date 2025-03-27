"""Social media manager for Myrcat."""

import logging
import configparser
import time
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple

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

    def __init__(
        self,
        config: configparser.ConfigParser,
        artwork_manager: ArtworkManager,
        db_manager: DatabaseManager,
    ):
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

        # Get artist repost window setting (in minutes)
        self.artist_repost_window = config.getint(
            "social_analytics", "artist_repost_window", fallback=60
        )

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
        self.bluesky_enable_images = self.config.getboolean(
            "bluesky", "enable_images", fallback=True
        )
        self.bluesky_enable_ai = self.config.getboolean(
            "bluesky", "enable_ai_content", fallback=True
        )
        self.bluesky_post_frequency = self.config.getint(
            "bluesky", "post_frequency", fallback=1
        )
        self.bluesky_testing_mode = self.config.getboolean(
            "bluesky", "testing_mode", fallback=False
        )

        # Get image dimensions from config with fallbacks to 600x600
        self.bluesky_image_width = self.config.getint(
            "bluesky", "image_width", fallback=600
        )
        self.bluesky_image_height = self.config.getint(
            "bluesky", "image_height", fallback=600
        )

        if self.bluesky_testing_mode:
            logging.warning(
                f"🧪 TESTING MODE ENABLED: Bluesky frequency limits disabled - every track will be posted"
            )

        logging.debug(
            f"Bluesky initialized for: {self.bluesky_handle} (images: {'enabled' if self.bluesky_enable_images else 'disabled'}, AI: {'enabled' if self.bluesky_enable_ai else 'disabled'}, image size: {self.bluesky_image_width}x{self.bluesky_image_height})"
        )

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
            hasattr(self, "bluesky_handle")
            and self.bluesky_handle
            and hasattr(self, "bluesky_password")
            and self.bluesky_password
        )

    def _extract_hashtags_for_bluesky(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Extract hashtags from text and create Bluesky facets for them.

        This properly formats hashtags as rich text facets according to Bluesky's API.
        Bluesky has specific requirements for hashtags:
        - Must start with # followed by a non-digit character
        - Can contain alphanumeric characters, underscores and hyphens
        - Limited to 64 characters in length
        - Cannot be numeric-only after the # symbol

        Args:
            text: The post text containing hashtags

        Returns:
            Tuple of (text without special formatting, list of facet objects for the API)
        """
        # Regular expression to find hashtags (similar to Bluesky's regex)
        # This matches hashtags starting with # and followed by non-digit, non-space characters
        hashtag_pattern = r"(^|\s)(#[^\d\s]\S*)"
        facets = []

        # Find all hashtags in the text
        for match in re.finditer(hashtag_pattern, text):
            full_match = match.group(
                0
            )  # The entire match including preceding space if any
            hashtag = match.group(2)  # Just the hashtag itself (#example)

            # Get byte positions (required by Bluesky API)
            # We need to convert character positions to byte positions for UTF-8
            start_pos = match.start(2)  # Character position of hashtag start
            end_pos = match.end(2)  # Character position of hashtag end

            # Convert to byte positions
            start_index = len(text[:start_pos].encode("utf-8"))
            end_index = len(text[:end_pos].encode("utf-8"))

            # Remove trailing punctuation from hashtag (following Bluesky's rules)
            clean_tag = re.sub(r"[.,;:!?]+$", "", hashtag)

            # Only use tags that aren't too long (Bluesky has a 64-char limit)
            if len(clean_tag) <= 64:
                # Create a facet for this hashtag
                facet = {
                    "index": {"byteStart": start_index, "byteEnd": end_index},
                    "features": [
                        {
                            "$type": "app.bsky.richtext.facet#tag",
                            "tag": clean_tag[1:],  # Remove the # prefix
                        }
                    ],
                }
                facets.append(facet)

        # Return the original text (Bluesky needs the hashtags in the text) and the facets
        return text, facets

    def _should_post_now(self, platform: str) -> bool:
        """Check if enough time has passed since the last post on this platform.

        Args:
            platform: Social media platform name

        Returns:
            True if posting is allowed, False otherwise
        """
        # Check for testing mode (bypass frequency limits)
        if (
            platform == "Bluesky"
            and hasattr(self, "bluesky_testing_mode")
            and self.bluesky_testing_mode
        ):
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
            hours_since_last = (
                datetime.now() - self.last_post_times[platform]
            ).total_seconds() / 3600
            if hours_since_last < frequency_hours:
                logging.debug(
                    f"⏱️ Skipping {platform} post (posted {hours_since_last:.1f}h ago, limit is {frequency_hours}h)"
                )
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
            
        TODO: Potential improvements:
        - Refactor into smaller, more testable functions
        - Better handle rate limiting and API failures
        - Implement exponential backoff for retries
        - Add support for post threads/replies
        - Extract image handling to separate method
        - Support alternative post formats (polls, links)
        """
        if not hasattr(self, "bluesky"):
            return False  # Service not initialized - excluded in config

        # Check posting frequency
        if not self._should_post_now("Bluesky"):
            return False

        # Check if the same artist was recently posted
        if await self._is_artist_recently_posted("Bluesky", track.artist):
            return False

        if not self.bluesky_credentials_valid():
            logging.error("💥 Bluesky credentials missing or invalid")
            return False

        try:
            # Login for each update as the session might expire
            client = AtprotoClient()
            client.login(self.bluesky_handle, self.bluesky_password)

            # Generate post text based on track info
            content_source = "standard"
            source_details = "basic"

            if self.bluesky_enable_ai:
                post_text, content_metadata = (
                    await self.content_generator.generate_track_description(track)
                )
                content_source = content_metadata.get("source_type", "unknown")
                if content_source == "ai":
                    source_details = content_metadata.get("prompt_name", "unknown")
                else:
                    source_details = content_metadata.get("template_name", "unknown")
            else:
                # Use standard text if AI is disabled
                post_text = (
                    f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
                )
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
                        # Resize image for social media using configured dimensions
                        temp_resized, dimensions = (
                            await self.artwork_manager.resize_for_social(
                                image_path,
                                size=(
                                    self.bluesky_image_width,
                                    self.bluesky_image_height,
                                ),
                            )
                        )
                        upload_path = temp_resized if temp_resized else image_path
                        img_width, img_height = dimensions

                        # Upload the image to Bluesky
                        with open(upload_path, "rb") as f:
                            image_data = f.read()
                        blob = client.com.atproto.repo.upload_blob(image_data)

                        # Clean up temp file if it exists
                        if temp_resized and temp_resized.exists():
                            try:
                                temp_resized.unlink()
                                logging.debug(
                                    f"🧹 Removed temporary resized image: {temp_resized}"
                                )
                            except Exception as clean_err:
                                logging.warning(
                                    f"⚠️ Failed to remove temporary image: {clean_err}"
                                )

                        # Create image embed with width and height dimensions
                        # We're using 600x600 as our standard size for consistency
                        embed = {
                            "$type": "app.bsky.embed.images",
                            "images": [
                                {
                                    "alt": f"Album artwork for {track.title} by {track.artist}",
                                    "image": blob.blob,
                                    "aspectRatio": {
                                        "width": img_width,
                                        "height": img_height,
                                    },
                                }
                            ],
                        }
                    except Exception as img_err:
                        logging.error(f"💥 Error uploading image to Bluesky: {img_err}")

            # Generate system hashtags - pass content source info
            is_ai_content = content_source == "ai"
            sys_hashtags = self.content_generator.generate_hashtags(
                track, is_ai_content=is_ai_content
            )

            # Add show name as final hashtag if it exists and isn't already included
            if track.program and track.program.strip():
                # Create proper show hashtag
                show_hashtag = "#" + "".join(
                    word.capitalize() for word in track.program.strip().split()
                )
                # Only add if not already in hashtags
                if show_hashtag not in sys_hashtags:
                    sys_hashtags = sys_hashtags + " " + show_hashtag

            # Helper function to remove duplicate hashtags while preserving order
            def deduplicate_hashtags(hashtag_str: str) -> str:
                if not hashtag_str.strip():
                    return ""

                # Split by spaces, keeping only unique hashtags (preserving order)
                seen = set()
                unique_hashtags = []

                for tag in hashtag_str.split():
                    # Skip empty tags
                    if not tag.strip():
                        continue

                    # Normalize the tag to lowercase for comparison
                    tag_lower = tag.lower()

                    # Only add if we haven't seen this tag before
                    if tag_lower not in seen:
                        seen.add(tag_lower)
                        unique_hashtags.append(tag)

                # Return space-separated hashtags
                return " ".join(unique_hashtags)

            # For AI content, leave any hashtags that the AI generated (after deduplication)
            # For non-AI content, add our system-generated hashtags (after deduplication)
            if is_ai_content:
                # If AI content has "\n\n#" pattern, deduplicate the hashtags
                if "\n\n#" in post_text:
                    main_content, ai_hashtags = post_text.split("\n\n#", 1)
                    deduplicated_hashtags = deduplicate_hashtags(
                        "#" + ai_hashtags.strip()
                    )
                    if deduplicated_hashtags:
                        post_text = (
                            main_content.strip() + f"\n\n{deduplicated_hashtags}"
                        )
                    else:
                        post_text = main_content.strip()
                else:
                    # Ensure the post text is properly trimmed
                    post_text = post_text.strip()
            else:
                # Not AI-generated content - add system hashtags
                if "\n\n#" in post_text:
                    # Split post into content and existing hashtags
                    main_content, existing_hashtags = post_text.split("\n\n#", 1)
                    # Combine existing hashtags with system hashtags and deduplicate
                    combined_hashtags = deduplicate_hashtags(
                        "#" + existing_hashtags.strip() + " " + sys_hashtags
                    )
                    # Rebuild the post
                    post_text = main_content.strip() + f"\n\n{combined_hashtags}"
                else:
                    # No existing hashtags, add system hashtags if we have any (already deduplicated)
                    post_text = post_text.strip()
                    if sys_hashtags:
                        post_text += f"\n\n{sys_hashtags}"

            # Check post length for Bluesky's 300 character limit
            if len(post_text) > 300:
                logging.warning(
                    f"⚠️ Post too long ({len(post_text)} of 300 chars) Trimming hashtags."
                )
                # Trim hashtags first if needed
                if "\n\n" in post_text:
                    main_content, hashtags = post_text.split("\n\n", 1)
                    if len(main_content) <= 290:
                        # Keep main content and just the first hashtag
                        first_hashtag = (
                            hashtags.split(" ")[0] if " " in hashtags else hashtags
                        )
                        post_text = f"{main_content}\n\n{first_hashtag}"
                        logging.debug(
                            f"⚠️ Trimmed hashtags to fit character limit: {post_text}"
                        )
                    else:
                        # Content itself is too long, fallback to a simpler message
                        post_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
                        logging.debug(f"⚠️ Using fallback simple message: {post_text}")
                else:
                    # No hashtags to trim, use fallback
                    post_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
                    logging.debug(f"⚠️ Using fallback simple message: {post_text}")

            # Log the complete post text for debugging
            logging.debug(
                f"🔵 Bluesky post content ({len(post_text)} chars): {post_text}"
            )
            logging.debug(f"🔵 Bluesky post has image: {'Yes' if embed else 'No'}")

            # Process the text to extract hashtags and create facets
            final_text, facets = self._extract_hashtags_for_bluesky(post_text)

            # Log the facets for debugging
            if facets:
                logging.debug(
                    f"🔵 Created {len(facets)} hashtag facets for Bluesky post"
                )

            # Create record with rich text facets for hashtags
            post_record = {
                "$type": "app.bsky.feed.post",
                "text": final_text,
                "createdAt": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }

            # Add embed if we have one
            if embed:
                post_record["embed"] = embed

            # Add facets if we found any hashtags
            if facets:
                post_record["facets"] = facets

            # Send the post
            response = client.com.atproto.repo.create_record(
                {
                    "repo": client.me.did,
                    "collection": "app.bsky.feed.post",
                    "record": post_record,
                }
            )

            # Track post in analytics
            if hasattr(self, "analytics") and hasattr(response, "uri"):
                post_id = response.uri.split("/")[-1]
                await self.analytics.record_post("Bluesky", post_id, track, post_text)
                logging.debug(f"🔵 Recorded Bluesky post to analytics - ID: {post_id}")

            # Add detail about content source to log
            if content_source == "ai":
                source_log = f"AI content (prompt: {source_details})"
            else:
                source_log = f"template content (template: {source_details})"

            # Log at INFO level for operational monitoring
            if embed:
                image_info = f"image ({img_width}x{img_height})"
            else:
                image_info = "no image"

            logging.info(
                f"🔵 Bluesky post created using {source_log} with {image_info}"
            )

            logging.debug(
                f"📒 Updated Bluesky with {'AI' if self.bluesky_enable_ai else 'standard'} content and {'image' if embed else 'no image'}"
            )
            return True

        except Exception as e:
            logging.error(f"💥 Bluesky update error: {e}")
            return False

    async def update_facebook(self, track: TrackInfo):
        """Update Facebook page with current track.

        Args:
            track: TrackInfo object containing track information

        Returns:
            True if post was successful, False otherwise
        """
        if not hasattr(self, "facebook"):
            return False  # Service not initialized - excluded in config

        # Check if the same artist was recently posted
        if await self._is_artist_recently_posted("Facebook", track.artist):
            return False

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

            # Track post success in analytics
            if hasattr(self, "analytics"):
                post_id = f"fb_{datetime.now().strftime('%Y%m%d%H%M%S')}"  # Generate a tracking ID
                await self.analytics.record_post("Facebook", post_id, track, message)

            return True
        except Exception as e:
            logging.error(f"💥 Facebook update error: {e}")
            return False

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

    def update_from_config(self):
        """Update manager settings from current configuration.
        
        This method should be called whenever the configuration is reloaded.
        """
        # Update artist repost window setting
        self.artist_repost_window = self.config.getint(
            "social_analytics", "artist_repost_window", fallback=60
        )
        
        # Update social media publishing settings
        self.publish_enabled = self.config.getboolean(
            "publish_exceptions", "publish_socials", fallback=True
        )
        
        # Update disabled services
        disabled_str = self.config.get(
            "publish_exceptions", "disable_services", fallback=""
        ).strip()
        
        if not disabled_str or disabled_str.lower() == "none":
            self.disabled_services = []
        else:
            self.disabled_services = [
                s.strip() for s in disabled_str.split(",") if s.strip()
            ]
        
        # Update analytics settings
        if hasattr(self, "analytics"):
            self.analytics.load_config()
            
        # Update content generator settings
        if hasattr(self, "content_generator"):
            self.content_generator.load_config()
            logging.debug(f"🔄 Updated content generator with new configuration")
    
    async def check_post_engagement(self):
        """Check engagement metrics for recent posts and update analytics.

        This should be called periodically to update engagement metrics.
        """
        if not hasattr(self, "analytics") or not self.analytics.enabled:
            return

        try:
            # For now, we'll implement Bluesky engagement checking
            if (
                "Bluesky" not in self.disabled_services
                and self.bluesky_credentials_valid()
            ):
                await self._check_bluesky_engagement()

            # Clean up old data
            await self.analytics.cleanup_old_data()
            
            # Generate analytics report after each check if enabled
            if self.analytics.generate_reports:
                # Get analytics data for the report
                analytics_data = await self.get_social_analytics()
                # Generate the report
                await self.analytics.generate_text_report(analytics_data)
                logging.debug(f"📊 Generated analytics report after engagement check")
        except Exception as e:
            logging.error(f"💥 Error checking post engagement: {e}")

    async def _is_artist_recently_posted(self, platform: str, artist: str) -> bool:
        """Check if the same artist has been posted within the configured time window.

        Args:
            platform: Social media platform to check
            artist: Artist name to check

        Returns:
            True if artist was recently posted, False otherwise
        """
        if not hasattr(self, "artist_repost_window") or self.artist_repost_window <= 0:
            # Feature is disabled, allow post
            return False

        try:
            # Calculate cutoff time
            cutoff_time = (
                datetime.now() - timedelta(minutes=self.artist_repost_window)
            ).isoformat()

            with self.db_manager._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM social_media_posts smp
                    JOIN playouts p ON smp.track_id = p.id
                    WHERE smp.platform = ?
                    AND p.artist = ?
                    AND smp.posted_at > ?
                    AND smp.deleted = 0
                    """,
                    (platform, artist, cutoff_time),
                )
                result = cursor.fetchone()
                count = result[0] if result else 0

                if count > 0:
                    logging.info(
                        f"⏱️ Skipping {platform} post for artist '{artist}' (already posted within {self.artist_repost_window} minutes)"
                    )
                    return True

                return False
        except Exception as e:
            logging.error(f"💥 Error checking recent artist posts: {e}")
            # On error, allow the post to go through
            return False

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
                    "SELECT post_id FROM social_media_posts WHERE platform = ? AND posted_at > ? AND deleted = 0",
                    ("Bluesky", cutoff_date),
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
                                "clicks": 0,  # Bluesky doesn't provide click tracking
                            },
                        )
                except Exception as post_error:
                    # Check if it's a 404 (Not Found) error
                    error_str = str(post_error).lower()
                    if "404" in error_str or "not found" in error_str or "no record" in error_str:
                        logging.info(f"🗑️ Bluesky post {post_id} not found (likely deleted)")
                        # Mark the post as deleted in the database
                        await self.analytics.mark_post_as_deleted("Bluesky", post_id)
                    else:
                        # Log other errors normally
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
                    platform_stats[platform] = await self.analytics.get_platform_stats(
                        platform, days=days
                    )

            return {
                "enabled": True,
                "days": days,
                "top_tracks": top_tracks,
                "platforms": platform_stats,
            }
        except Exception as e:
            logging.error(f"💥 Error getting social analytics: {e}")
            return {"enabled": True, "error": str(e)}
