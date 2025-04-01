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

        # Keep in-memory tracking as a fallback for database errors
        self.last_post_times = {}

        # Get artist repost window setting (in minutes)
        self.artist_repost_window = config.getint(
            "social_analytics", "artist_repost_window", fallback=60
        )

        # Check if social media publishing is globally enabled
        self.publish_enabled = self.config.getboolean(
            "publish_exceptions", "publish_socials", fallback=True
        )

        # Check individual service enabled states
        self.service_enabled = {
            "LastFM": self.config.getboolean("lastfm", "enabled", fallback=False),
            "ListenBrainz": self.config.getboolean("listenbrainz", "enabled", fallback=False),
            "Bluesky": self.config.getboolean("bluesky", "enabled", fallback=False),
            "Facebook": self.config.getboolean("facebook", "enabled", fallback=False)
        }
        
        logging.info(
            f"{'✅' if self.publish_enabled else '⛔️'} Social media publishing {'enabled' if self.publish_enabled else 'disabled'}"
        )
        
        # Log enabled services
        enabled_services = [name for name, enabled in self.service_enabled.items() if enabled]
        if enabled_services:
            logging.info(f"✅ Enabled services: {', '.join(enabled_services)}")
        else:
            logging.info("⚠️ No social media services are enabled")

        # Initialize new components
        self.content_generator = ContentGenerator(config)

        # Initialize analytics
        self.analytics = SocialMediaAnalytics(config, db_manager)

        # Initialize services that are enabled
        if self.publish_enabled:
            if self.service_enabled["LastFM"]:
                self.setup_lastfm()
            if self.service_enabled["ListenBrainz"]:
                self.setup_listenbrainz()
            if self.service_enabled["Bluesky"]:
                self.setup_bluesky()
            if self.service_enabled["Facebook"]:
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
        try:
            # Initialize variables
            self.facebook = None
            self.fb_page_id = self.config["facebook"]["page_id"]
            self._fb_token_valid = False
            self._last_fb_token_validation = 0  # Force validation on first use
            self._fb_access_token = None
            self._fb_token_expires_at = None
            
            # Load Facebook token from database
            if hasattr(self, "db_manager") and self.db_manager:
                with self.db_manager._get_connection() as conn:
                    # Try to load the most recent token
                    cursor = conn.execute("""
                        SELECT access_token, expires_at 
                        FROM facebook_tokens 
                        ORDER BY id DESC LIMIT 1
                    """)
                    token_data = cursor.fetchone()
                    
                    # If we found a token in the database
                    if token_data:
                        self._fb_access_token = token_data[0]
                        self._fb_token_expires_at = token_data[1]
                        
                        # Initialize the Facebook client with the token
                        if self._fb_access_token:
                            self.facebook = GraphAPI(self._fb_access_token)
                            
                            # Calculate days until expiration and log detailed information
                            if self._fb_token_expires_at:
                                try:
                                    expiry_date = datetime.fromisoformat(self._fb_token_expires_at)
                                    days_remaining = (expiry_date - datetime.now()).days
                                    
                                    # Determine when auto-renewal will occur (3 days threshold)
                                    # Calculate days until auto-renewal (when 3 days remain until expiration)
                                    # If expiry_date is May 29, and today is Mar 31, then:
                                    # days_remaining = 58 days, and we want auto-renewal when 3 days remain
                                    # so auto_renewal happens in (58-3) = 55 days
                                    auto_renew_date = expiry_date - timedelta(days=3)
                                    auto_renew_days = max(0, days_remaining - 3)
                                    
                                    # Log at DEBUG level for detailed information
                                    logging.debug(
                                        f"🔑 Facebook token status: {days_remaining} days until expiration "
                                        f"(expires: {expiry_date.isoformat()}). "
                                        f"Auto-renewal will trigger in {auto_renew_days} days "
                                        f"(on {auto_renew_date.strftime('%Y-%m-%d')})"
                                    )
                                    
                                    # Log at INFO level for more visibility
                                    logging.info(f"🔑 Facebook token status: {days_remaining} days until expiration")
                                    
                                    if days_remaining <= 7:
                                        logging.warning(f"⚠️ Facebook token will expire soon! Only {days_remaining} days remaining")
                                    if days_remaining <= 3:
                                        logging.warning(f"⚠️ Facebook token critically close to expiration! Only {days_remaining} days remaining")
                                except (ValueError, TypeError) as e:
                                    logging.debug(f"Loaded Facebook token from database (expiration date could not be parsed: {self._fb_token_expires_at})")
                            else:
                                logging.debug(f"Loaded Facebook token from database (no expiration date available)")
                    else:
                        logging.warning("⚠️ No Facebook token found in database - needs to be generated")
            
            # Configuration options
            self.fb_enable_images = self.config.getboolean(
                "facebook", "enable_images", fallback=True
            )
            self.fb_enable_ai = self.config.getboolean(
                "facebook", "enable_ai_content", fallback=True
            )
            self.fb_post_frequency = self.config.getint(
                "facebook", "post_frequency", fallback=1
            )
            self.fb_char_limit = self.config.getint(
                "facebook", "character_limit", fallback=500
            )
            self.fb_testing_mode = self.config.getboolean(
                "facebook", "testing_mode", fallback=False
            )
            
            # Image dimensions
            self.fb_image_width = self.config.getint(
                "facebook", "image_width", fallback=1200
            )
            self.fb_image_height = self.config.getint(
                "facebook", "image_height", fallback=630
            )
            
            # Log status
            if self.facebook:
                # Log configuration at DEBUG level
                logging.debug(
                    f"Facebook initialized for page: {self.fb_page_id} "
                    f"(images: {'enabled' if self.fb_enable_images else 'disabled'}, "
                    f"AI: {'enabled' if self.fb_enable_ai else 'disabled'}, "
                    f"image size: {self.fb_image_width}x{self.fb_image_height}, "
                    f"testing mode: {'enabled' if self.fb_testing_mode else 'disabled'})"
                )
                
                # Log token availability at INFO level
                if self._fb_token_expires_at:
                    try:
                        expiry_date = datetime.fromisoformat(self._fb_token_expires_at)
                        days_remaining = (expiry_date - datetime.now()).days
                        logging.info(f"🔑 Facebook token status: {days_remaining} days until expiration")
                    except (ValueError, TypeError):
                        logging.info(f"🔑 Facebook token available (expiration date unknown)")
                else:
                    logging.info(f"🔑 Facebook token available (no expiration date)")
                
                if self.fb_testing_mode:
                    logging.warning(
                        f"🧪 TESTING MODE ENABLED: Facebook frequency limits disabled - every track will be posted"
                    )
            else:
                logging.warning("⚠️ Facebook client not initialized - token needs to be generated")
            
            # We'll validate the token on first use instead of at initialization
            # since we're in a synchronous method and can't await coroutines directly
            logging.debug("Token will be validated on first use")
                
        except Exception as e:
            logging.error(f"💥 Facebook setup error: {str(e)}")
            self.facebook = None

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
        
    def facebook_credentials_valid(self) -> bool:
        """Check if Facebook credentials are valid and complete.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        # First check if we have the basic credentials and token
        has_credentials = (
            hasattr(self, "facebook") 
            and self.facebook is not None
            and hasattr(self, "fb_page_id")
            and self.fb_page_id
            and self._fb_access_token is not None
        )
        
        if not has_credentials:
            return False
            
        # For token validation, check if we've recently validated
        # to avoid checking on every operation
        current_time = time.time()
        
        # Set a validation interval (e.g., check once per hour)
        validation_interval = 3600  # 1 hour in seconds
        
        # Check if we've validated recently
        if (
            hasattr(self, "_last_fb_token_validation") 
            and (current_time - self._last_fb_token_validation) < validation_interval
        ):
            # Return cached validation result if we checked recently
            return self._fb_token_valid
        
        # Check if token has an expiration time and is expired based on that
        if self._fb_token_expires_at:
            try:
                expiry_date = datetime.fromisoformat(self._fb_token_expires_at)
                if datetime.now() > expiry_date:
                    logging.warning(f"⚠️ Facebook token has expired based on stored expiration date")
                    self._fb_token_valid = False
                    return False
            except (ValueError, TypeError) as e:
                # If we can't parse the expiration date, continue with regular checks
                logging.warning(f"⚠️ Unable to parse token expiration date: {e}")
            
        # Don't try to schedule async validation from here
        # Just assume credentials are valid for now based on our stored data
        # They'll be fully validated on first use
        
        # Return true if we have credentials, even if we haven't validated the token yet
        return has_credentials
    
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
        Uses database to get last post time to ensure persistence across restarts,
        with fallback to in-memory tracking if database lookup fails.

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
            
        # Check for Facebook testing mode
        if platform == "Facebook" and hasattr(self, "fb_testing_mode") and self.fb_testing_mode:
            logging.debug(f"🧪 Testing mode: Bypassing frequency limits for {platform}")
            # Still update the timestamp for tracking
            self.last_post_times[platform] = datetime.now()
            return True

        # Get platform-specific frequency settings
        frequency_hours = 1  # Default

        if platform == "Bluesky" and hasattr(self, "bluesky_post_frequency"):
            frequency_hours = self.bluesky_post_frequency
            
        if platform == "Facebook" and hasattr(self, "fb_post_frequency"):
            frequency_hours = self.fb_post_frequency

        # First try to get last post time from database (persistent across restarts)
        last_post_time = self.db_manager.get_last_post_time(platform)
        
        # If database lookup succeeds, use that time
        if last_post_time:
            hours_since_last = (datetime.now() - last_post_time).total_seconds() / 3600
            if hours_since_last < frequency_hours:
                logging.debug(
                    f"⏱️ Skipping {platform} post (from DB: posted {hours_since_last:.1f}h ago, limit is {frequency_hours}h)"
                )
                return False
            else:
                logging.debug(
                    f"✅ Will post to {platform} (from DB: last post was {hours_since_last:.1f}h ago, limit is {frequency_hours}h)"
                )
        # If database lookup fails, fall back to in-memory tracking
        elif platform in self.last_post_times:
            hours_since_last = (
                datetime.now() - self.last_post_times[platform]
            ).total_seconds() / 3600
            if hours_since_last < frequency_hours:
                logging.debug(
                    f"⏱️ Skipping {platform} post (from memory: posted {hours_since_last:.1f}h ago, limit is {frequency_hours}h)"
                )
                return False
            else:
                logging.debug(
                    f"✅ Will post to {platform} (from memory: last post was {hours_since_last:.1f}h ago, limit is {frequency_hours}h)"
                )
        else:
            logging.debug(f"📝 No previous posts found for {platform} in DB or memory, will post now")
            
        # Update in-memory tracking when we decide to post
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
        if not hasattr(self, "facebook") or self.facebook is None:
            logging.warning("⚠️ Facebook client not initialized")
            return False
            
        # Validate token before posting
        # This is especially important for Facebook which has expiring tokens
        if not await self._validate_facebook_token():
            logging.error("❌ Cannot post to Facebook: Invalid or expired token")
            # Try to refresh the token if app credentials are available
            if (
                self.config["facebook"].get("app_id") 
                and self.config["facebook"].get("app_secret")
            ):
                logging.info("🔄 Attempting to refresh Facebook token...")
                if await self._refresh_facebook_token():
                    logging.info("✅ Facebook token refreshed successfully, continuing with post")
                else:
                    return False
            else:
                return False
                
        # Check if we should post now based on frequency
        if not self._should_post_now("Facebook"):
            return False

        # Check if the same artist was recently posted
        if await self._is_artist_recently_posted("Facebook", track.artist):
            logging.debug(f"⏱️ Skipping Facebook post - same artist posted recently: {track.artist}")
            return False

        try:
            # Generate post text based on track info
            content_source = "standard"
            source_details = "basic"

            if self.fb_enable_ai:
                post_text, content_metadata = await self.content_generator.generate_track_description(track)
                content_source = content_metadata.get("source_type", "unknown")
                if content_source == "ai":
                    source_details = content_metadata.get("prompt_name", "unknown")
                else:
                    source_details = content_metadata.get("template_name", "unknown")
            else:
                # Use standard text if AI is disabled
                post_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
                if track.album:
                    post_text += f"\nFrom the album: {track.album}"
                if track.program:
                    post_text += f"\nProgram: {track.program}"
                if track.presenter:
                    post_text += f"\nPresenter: {track.presenter}"

            # Generate system hashtags - pass content source info
            is_ai_content = content_source == "ai"
            system_hashtags = self.content_generator.generate_hashtags(
                track, is_ai_content=is_ai_content
            )

            # Add show name as final hashtag if it exists and isn't already included
            if track.program and track.program.strip():
                # Create proper show hashtag
                show_hashtag = "#" + "".join(
                    word.capitalize() for word in track.program.strip().split()
                )
                # Only add if not already in hashtags
                if show_hashtag not in system_hashtags:
                    system_hashtags = system_hashtags + " " + show_hashtag

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

            # Process hashtags based on content source
            if is_ai_content:
                # If AI content has "\n\n#" pattern, deduplicate the hashtags
                if "\n\n#" in post_text:
                    main_content, ai_hashtags = post_text.split("\n\n#", 1)
                    deduplicated_hashtags = deduplicate_hashtags(
                        "#" + ai_hashtags.strip()
                    )
                    if deduplicated_hashtags:
                        post_text = main_content.strip() + f"\n\n{deduplicated_hashtags}"
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
                        "#" + existing_hashtags.strip() + " " + system_hashtags
                    )
                    # Rebuild the post
                    post_text = main_content.strip() + f"\n\n{combined_hashtags}"
                else:
                    # No existing hashtags, add system hashtags if we have any
                    post_text = post_text.strip()
                    if system_hashtags:
                        post_text += f"\n\n{system_hashtags}"

            # Check post length for Facebook's character limit
            if hasattr(self, "fb_char_limit") and self.fb_char_limit > 0 and len(post_text) > self.fb_char_limit:
                logging.warning(
                    f"⚠️ Post too long ({len(post_text)} of {self.fb_char_limit} chars) Trimming hashtags."
                )
                # Trim hashtags first if needed
                if "\n\n" in post_text:
                    main_content, hashtags = post_text.split("\n\n", 1)
                    if len(main_content) <= self.fb_char_limit - 10:
                        # Keep main content and just the first hashtag
                        first_hashtag = hashtags.split(" ")[0] if " " in hashtags else hashtags
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
            logging.debug(f"📘 Facebook post content ({len(post_text)} chars): {post_text}")

            # Create embed with image if available
            post_with_image = False
            response = None
            img_width = 0
            img_height = 0

            if self.fb_enable_images:
                image_path = None
                if track.image:
                    # Get full path to processed artwork
                    artwork_path = self.artwork_manager.publish_dir / track.image
                    if artwork_path.exists():
                        image_path = artwork_path

                # Upload image to Facebook if available
                if image_path and image_path.exists():
                    try:
                        # Resize image for social media using configured dimensions
                        temp_resized, dimensions = await self.artwork_manager.resize_for_social(
                            image_path,
                            size=(self.fb_image_width, self.fb_image_height),
                        )
                        upload_path = temp_resized if temp_resized else image_path
                        img_width, img_height = dimensions

                        # Post with image
                        with open(upload_path, "rb") as image_file:
                            response = await self._facebook_api_call_with_retry(
                                self.facebook.put_photo,
                                image=image_file,
                                message=post_text,
                                album_path=f"{self.fb_page_id}/photos"
                            )
                            post_with_image = True

                        # Clean up temp file if it exists
                        if temp_resized and temp_resized.exists():
                            try:
                                temp_resized.unlink()
                                logging.debug(f"🧹 Removed temporary resized image: {temp_resized}")
                            except Exception as clean_err:
                                logging.warning(f"⚠️ Failed to remove temporary image: {clean_err}")
                    except Exception as img_err:
                        logging.error(f"💥 Error uploading image to Facebook: {img_err}")
                        post_with_image = False

            # If no image or image upload failed, post as text only
            if not post_with_image:
                response = await self._facebook_api_call_with_retry(
                    self.facebook.put_object,
                    parent_object=self.fb_page_id,
                    connection_name="feed",
                    message=post_text
                )
                logging.debug(f"📘 Posted to Facebook with text only")

            # Extract post ID from response
            if isinstance(response, dict) and "id" in response:
                post_id = response["id"]
                post_url = f"https://facebook.com/{post_id}"
            else:
                # Generate synthetic ID for tracking
                post_id = f"fb_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                post_url = None

            # Track post in analytics
            if hasattr(self, "analytics"):
                await self.analytics.record_post(
                    platform="Facebook",
                    post_id=post_id,
                    track=track,
                    content=post_text,
                    post_url=post_url,
                    has_image=post_with_image
                )

            # Add detail about content source to log
            if content_source == "ai":
                source_log = f"AI content (prompt: {source_details})"
            else:
                source_log = f"template content (template: {source_details})"

            # Log at INFO level for operational monitoring
            if post_with_image:
                image_info = f"image ({img_width}x{img_height})"
            else:
                image_info = "no image"

            logging.info(
                f"📘 Facebook post created using {source_log} with {image_info}"
            )

            return True
        except Exception as e:
            logging.error(f"💥 Facebook update error: {e}")
            if hasattr(self, "analytics"):
                await self.analytics.track_error("Facebook", track, str(e))
            return False

    async def update_social_media(self, track: TrackInfo):
        """Update all configured social media platforms with track debug.

        Args:
            track: TrackInfo object containing track information
        """
        if not self.publish_enabled:
            logging.debug("⚠️ Social media publishing is disabled globally!")
            return

        updates = {
            "LastFM": self.update_lastfm,
            "ListenBrainz": self.update_listenbrainz,
            "Bluesky": self.update_bluesky,
            "Facebook": self.update_facebook,
        }

        for platform, update_func in updates.items():
            if self.service_enabled.get(platform, False):
                try:
                    logging.debug(f"Updating {platform}...")
                    await update_func(track)
                except Exception as e:
                    logging.error(f"💥 Error updating {platform}: {e}")
            else:
                logging.debug(f"Skipping {platform} (disabled in config)")

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
        
        # Update service-specific enabled states
        self.service_enabled = {
            "LastFM": self.config.getboolean("lastfm", "enabled", fallback=False),
            "ListenBrainz": self.config.getboolean("listenbrainz", "enabled", fallback=False),
            "Bluesky": self.config.getboolean("bluesky", "enabled", fallback=False),
            "Facebook": self.config.getboolean("facebook", "enabled", fallback=False)
        }
        
        # Log changes
        enabled_services = [name for name, enabled in self.service_enabled.items() if enabled]
        if enabled_services:
            logging.info(f"✅ Enabled services after config reload: {', '.join(enabled_services)}")
        else:
            logging.info("⚠️ No social media services are enabled after config reload")
        
        # Update analytics settings
        if hasattr(self, "analytics"):
            self.analytics.load_config()
            
        # Update content generator settings
        if hasattr(self, "content_generator"):
            self.content_generator.load_config()
            logging.debug(f"🔄 Updated content generator with new configuration")
    
    async def _validate_facebook_token(self) -> bool:
        """Validate if the Facebook access token is still valid.
        
        Returns:
            True if token is valid, False otherwise
        """
        if not hasattr(self, "facebook") or self.facebook is None:
            return False
            
        try:
            # Use our detailed validation method to get token info
            token_info = await self._validate_facebook_token_info()
            if not token_info:
                logging.warning("⚠️ Facebook token validation failed: Could not get token info")
                return False
                
            # Check if token is valid
            is_valid = token_info.get("is_valid", False)
            
            if not is_valid:
                error_message = token_info.get("error", {}).get("message", "Unknown error")
                logging.warning(f"⚠️ Facebook token validation failed: {error_message}")
                return False
                
            # Check expiration - warn if token will expire soon (within 7 days)
            expires_at = token_info.get("expires_at", 0)
            if expires_at:
                expiry_date = datetime.fromtimestamp(expires_at)
                days_remaining = (expiry_date - datetime.now()).days
                
                if days_remaining <= 7:
                    logging.warning(f"⚠️ Facebook token will expire in {days_remaining} days - consider refreshing")
                    # Auto-refresh the token if needed (when ≤ 3 days remain)
                    if days_remaining <= 3:
                        # This date is just for logging purposes (when auto-renewal should happen)
                        auto_renew_date = datetime.now()  # It's happening now as we're within the threshold
                        logging.info(f"🔄 Attempting to auto-refresh Facebook token (token expires in {days_remaining} days)")
                        logging.debug(f"Token auto-renewal triggered: Current time {datetime.now().isoformat()}, expiration date {expiry_date.isoformat()}, threshold 3 days")
                        
                        if await self._refresh_facebook_token():
                            logging.info("✅ Facebook token auto-refreshed successfully")
                            return True
                        else:
                            logging.warning("⚠️ Automatic token refresh attempt failed - manual refresh may be required")
                    else:
                        logging.debug(f"Token expiration warning: {days_remaining} days left, but not yet eligible for auto-renewal (threshold: 3 days)")
                    
                    
            return True
        except Exception as e:
            logging.error(f"💥 Error validating Facebook token: {e}")
            return False

    async def _refresh_facebook_token(self):
        """Attempt to refresh the Facebook access token.
        
        Returns:
            True if token was refreshed successfully, False otherwise
        """
        try:
            # Facebook Graph API method to extend token lifetime
            # This requires app_id and app_secret to be available
            if not self.config.has_section("facebook") or not self.config["facebook"].get("app_id") or not self.config["facebook"].get("app_secret"):
                logging.warning("⚠️ Cannot refresh Facebook token: app_id or app_secret missing")
                return False
                
            # Get app credentials
            app_id = self.config["facebook"]["app_id"]
            app_secret = self.config["facebook"]["app_secret"]
            
            # Get current token - either from instance variable or try to load from database
            current_token = self._fb_access_token
            
            # If we don't have a token yet, we can't refresh - need to generate a new one
            if not current_token:
                logging.warning("⚠️ No Facebook token available to refresh")
                return False
                
            # Use the OAuth framework to exchange tokens
            import requests
            
            url = f"https://graph.facebook.com/v18.0/oauth/access_token"
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": current_token
            }
            
            response = requests.get(url, params=params)
            result = response.json()
            
            if "access_token" in result:
                new_token = result["access_token"]
                
                # Update the token in memory
                self.facebook = GraphAPI(new_token)
                
                # Store the token in database only
                await self._store_facebook_token(new_token, result.get("expires_in"))
                
                # Validate the new token to get its details
                token_info = await self._validate_facebook_token_info(new_token)
                
                # Log the new expiration if available
                if token_info and "expires_at" in token_info:
                    expiry_date = datetime.fromtimestamp(token_info["expires_at"])
                    days_remaining = (expiry_date - datetime.now()).days
                    logging.info(f"✅ Facebook token refreshed. New token expires in {days_remaining} days")
                elif "expires_in" in result:
                    expires_in_days = result["expires_in"] / 86400  # Convert seconds to days
                    logging.info(f"✅ Facebook token refreshed. New token expires in {expires_in_days:.1f} days (approximate)")
                else:
                    logging.info(f"✅ Facebook token refreshed successfully")
                    
                return True
            else:
                error = result.get("error", {}).get("message", "Unknown error")
                logging.error(f"❌ Failed to refresh Facebook token: {error}")
                return False
                
        except Exception as e:
            logging.error(f"💥 Error refreshing Facebook token: {e}")
            return False
            
    async def _store_facebook_token(self, access_token, expires_in=None):
        """Store a Facebook token in the database. Only keeps the latest token.
        
        Args:
            access_token: The access token to store
            expires_in: Seconds until the token expires (optional)
            
        Returns:
            True if storing was successful, False otherwise
        """
        if not hasattr(self, "db_manager") or not self.db_manager:
            logging.warning("⚠️ Cannot store Facebook token: database manager not available")
            return False
            
        try:
            # Calculate expiration time if provided
            created_at = datetime.now().isoformat()
            expires_at = None
            if expires_in:
                expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            
            # Store metadata with app and page info
            import json
            metadata = json.dumps({
                "app_id": self.config["facebook"].get("app_id", ""),
                "page_id": self.config["facebook"].get("page_id", "")
            })
            
            with self.db_manager._get_connection() as conn:
                # First, check if this exact token already exists
                cursor = conn.execute(
                    "SELECT id FROM facebook_tokens WHERE access_token = ?",
                    (access_token,)
                )
                existing_token = cursor.fetchone()
                
                if existing_token:
                    # Update the existing token's expiration and metadata
                    conn.execute(
                        """UPDATE facebook_tokens SET 
                           expires_at = ?, 
                           created_at = ?,
                           metadata = ? 
                           WHERE id = ?""",
                        (expires_at, created_at, metadata, existing_token[0])
                    )
                    logging.debug(f"Updated existing Facebook token in database (expires: {expires_at or 'unknown'})")
                else:
                    # Insert the new token
                    conn.execute(
                        "INSERT INTO facebook_tokens (access_token, created_at, expires_at, metadata) VALUES (?, ?, ?, ?)",
                        (access_token, created_at, expires_at, metadata)
                    )
                    logging.info(f"✅ Stored new Facebook token in database (expires: {expires_at or 'unknown'})")
                
                # Update instance variables
                self._fb_access_token = access_token
                self._fb_token_expires_at = expires_at
                self._fb_token_valid = True
                self._last_fb_token_validation = time.time()
                
                # Log detailed expiration information for debugging
                if expires_at:
                    try:
                        expiry_date = datetime.fromisoformat(expires_at)
                        days_remaining = (expiry_date - datetime.now()).days
                        
                        # Determine when auto-renewal will occur (3 days threshold)
                        # Calculate when we'll auto-renew (3 days before expiration)
                        auto_renew_date = expiry_date - timedelta(days=3)
                        auto_renew_days = max(0, days_remaining - 3)
                        
                        # Log at DEBUG level with detailed info
                        logging.debug(
                            f"🔑 New Facebook token stored: {days_remaining} days until expiration "
                            f"(expires: {expiry_date.isoformat()}). "
                            f"Auto-renewal will trigger in {auto_renew_days} days "
                            f"(on {auto_renew_date.strftime('%Y-%m-%d')})"
                        )
                        
                        # Log at INFO level for more visibility
                        logging.info(f"🔑 New Facebook token stored: {days_remaining} days until expiration")
                    except (ValueError, TypeError) as e:
                        logging.debug(f"New Facebook token stored, but expiration date could not be parsed: {expires_at}")
                else:
                    logging.debug(f"New Facebook token stored (no expiration date available)")
                
                return True
                
        except Exception as e:
            logging.error(f"💥 Error storing Facebook token: {e}")
            return False
    
    async def get_facebook_token_status(self):
        """Get the status of the current Facebook token.
        
        Returns:
            Dictionary with token status information
        """
        if not hasattr(self, "facebook") or self.facebook is None:
            return {"valid": False, "error": "Facebook client not initialized"}
            
        if not self.config.has_section("facebook"):
            return {"valid": False, "error": "No Facebook configuration"}
            
        # Use the in-memory token instead of looking in config
        if not self._fb_access_token:
            return {"valid": False, "error": "No access token available"}
            
        try:
            # Validate the token
            token_info = await self._validate_facebook_token_info()
            if not token_info:
                return {"valid": False, "error": "Failed to validate token"}
                
            is_valid = token_info.get("is_valid", False)
            if not is_valid:
                error = token_info.get("error", {}).get("message", "Unknown error")
                return {"valid": False, "error": error}
                
            # Build status information
            status = {
                "valid": True,
                "type": token_info.get("type", "unknown"),
                "app_id": token_info.get("app_id"),
            }
            
            # Add expiration information
            expires_at = token_info.get("expires_at")
            if expires_at:
                expiry_date = datetime.fromtimestamp(expires_at)
                days_remaining = (expiry_date - datetime.now()).days
                
                status["expires_at"] = expiry_date.isoformat()
                status["days_remaining"] = days_remaining
                status["expiring_soon"] = days_remaining <= 14  # Two weeks threshold
            
            # Add data access expiration
            data_access_expires_at = token_info.get("data_access_expires_at")
            if data_access_expires_at:
                data_access_expiry = datetime.fromtimestamp(data_access_expires_at)
                status["data_access_expires_at"] = data_access_expiry.isoformat()
            
            # Add scopes
            status["scopes"] = token_info.get("scopes", [])
            
            # Add page info
            if token_info.get("type") == "PAGE":
                status["page_id"] = token_info.get("profile_id")
            
            # Add database token history if available
            if hasattr(self, "db_manager") and self.db_manager:
                try:
                    with self.db_manager._get_connection() as conn:
                        # Get token count
                        cursor = conn.execute(
                            "SELECT COUNT(*) FROM facebook_tokens"
                        )
                        count_result = cursor.fetchone()
                        if count_result:
                            status["stored_tokens"] = count_result[0]
                        
                        # Get latest token info
                        cursor = conn.execute(
                            """SELECT created_at, expires_at 
                               FROM facebook_tokens 
                               ORDER BY id DESC LIMIT 1"""
                        )
                        token_result = cursor.fetchone()
                        if token_result:
                            status["latest_stored"] = {
                                "created_at": token_result[0],
                                "expires_at": token_result[1] if token_result[1] else "Unknown"
                            }
                except Exception as db_err:
                    logging.warning(f"⚠️ Error getting token history: {db_err}")
            
            return status
            
        except Exception as e:
            logging.error(f"💥 Error getting Facebook token status: {e}")
            return {"valid": False, "error": str(e)}
    
    async def _validate_facebook_token_info(self, access_token=None):
        """Get validation information for a Facebook access token.
        
        Args:
            access_token: The token to validate (defaults to current token from instance)
            
        Returns:
            Dictionary with token information or None if validation failed
        """
        if access_token is None:
            # Use instance variable as the source of truth
            access_token = self._fb_access_token
            if not access_token:
                logging.warning("⚠️ No Facebook token available for validation")
                return None
        
        try:
            if not self.config.has_section("facebook") or not self.config["facebook"].get("app_id") or not self.config["facebook"].get("app_secret"):
                logging.warning("⚠️ Cannot validate Facebook token: app_id or app_secret missing")
                return None
                
            app_id = self.config["facebook"]["app_id"]
            app_secret = self.config["facebook"]["app_secret"]
            
            import requests
            
            # Use app access token (app_id|app_secret) for validation
            url = "https://graph.facebook.com/debug_token"
            params = {
                "input_token": access_token,
                "access_token": f"{app_id}|{app_secret}"
            }
            
            response = requests.get(url, params=params)
            data = response.json()
            
            if "data" not in data:
                error = data.get("error", {}).get("message", "Unknown error")
                logging.error(f"Failed to validate token: {error}")
                return None
                
            # Update our last validation timestamp
            self._last_fb_token_validation = time.time()
            # Store validation result for caching
            self._fb_token_valid = data["data"].get("is_valid", False)
                
            return data["data"]
            
        except Exception as e:
            logging.error(f"💥 Error validating Facebook token: {e}")
            return None
    
    async def check_post_engagement(self):
        """Check engagement metrics for recent posts and update analytics.

        This should be called periodically to update engagement metrics.
        """
        if not hasattr(self, "analytics") or not self.analytics.enabled:
            return

        try:
            # Check Bluesky engagement if enabled
            if (
                self.service_enabled.get("Bluesky", False)
                and self.bluesky_credentials_valid()
            ):
                await self._check_bluesky_engagement()
                
            # Check Facebook engagement if enabled
            if (
                self.service_enabled.get("Facebook", False)
                and self.facebook_credentials_valid()
            ):
                await self._check_facebook_engagement()

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
            
    async def _facebook_api_call_with_retry(self, api_method, *args, **kwargs):
        """Execute a Facebook API call with retry logic.
        
        Args:
            api_method: The Facebook API method to call
            *args: Positional arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method
            
        Returns:
            API response or None on failure
        """
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                return api_method(*args, **kwargs)
            except Exception as e:
                if "rate limit" in str(e).lower():
                    # Rate limit hit
                    wait_time = retry_delay * (2 ** attempt)
                    logging.warning(f"⚠️ Facebook rate limit hit, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                elif attempt < max_retries - 1:
                    # Other error, retry
                    logging.warning(f"⚠️ Facebook API error, retrying: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    # Final attempt failed
                    raise
        
        return None

    async def _check_facebook_engagement(self):
        """Check engagement metrics for recent Facebook posts."""
        try:
            # Verify we have valid credentials
            if not self.facebook_credentials_valid():
                logging.warning("⚠️ Cannot check Facebook engagement: Invalid credentials")
                return
                
            # Ensure token is valid
            if not await self._validate_facebook_token():
                logging.warning("⚠️ Cannot check Facebook engagement: Invalid token")
                return
                
            # Get recent posts from analytics
            cutoff_date = (datetime.now() - timedelta(days=7)).isoformat()

            with self.db_manager._get_connection() as conn:
                # Get post_id for real Facebook posts (not synthetic IDs) 
                cursor = conn.execute(
                    "SELECT post_id FROM social_media_posts WHERE platform = ? AND posted_at > ? AND deleted = 0 AND NOT post_id LIKE 'fb_%'",
                    ("Facebook", cutoff_date),
                )
                post_ids = [row[0] for row in cursor.fetchall()]
                
            # Process actual Facebook posts (non-synthetic IDs)
            for post_id in post_ids:
                try:
                    # Get post engagement metrics from Facebook API
                    engagement = await self._facebook_api_call_with_retry(
                        self.facebook.get_object,
                        id=post_id,
                        fields="reactions.summary(true),shares,comments.summary(true)"
                    )
                    
                    if engagement:
                        # Extract metrics, using 0 for missing values
                        likes = engagement.get("reactions", {}).get("summary", {}).get("total_count", 0)
                        shares = engagement.get("shares", {}).get("count", 0) if "shares" in engagement else 0
                        comments = engagement.get("comments", {}).get("summary", {}).get("total_count", 0)
                        
                        # Update analytics
                        await self.analytics.update_engagement(
                            "Facebook",
                            post_id,
                            {
                                "likes": likes,
                                "shares": shares,
                                "comments": comments,
                                "clicks": 0,  # Facebook doesn't provide click data
                            },
                        )
                        
                        logging.debug(f"📊 Updated Facebook engagement for post {post_id}: {likes} likes, {shares} shares, {comments} comments")
                except Exception as post_error:
                    error_str = str(post_error).lower()
                    # Check if post was deleted or not found
                    if "(#100)" in error_str or "not found" in error_str or "does not exist" in error_str:
                        logging.info(f"🗑️ Facebook post {post_id} not found (likely deleted)")
                        await self.analytics.mark_post_as_deleted("Facebook", post_id)
                    else:
                        logging.warning(f"⚠️ Error checking Facebook post {post_id}: {post_error}")
                        # Still update engagement with zeros to avoid missing data
                        try:
                            await self.analytics.update_engagement(
                                "Facebook",
                                post_id,
                                {
                                    "likes": 0,
                                    "shares": 0,
                                    "comments": 0,
                                    "clicks": 0,
                                },
                            )
                            logging.debug(f"📊 Set zero engagement for Facebook post {post_id} due to API error")
                        except Exception as analytics_error:
                            logging.error(f"💥 Error updating engagement for Facebook post {post_id}: {analytics_error}")
        except Exception as e:
            logging.error(f"💥 Error checking Facebook engagement: {e}")

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
                if self.service_enabled.get(platform, False):
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
