# Adding a New Social Media Platform to Myrcat

This guide provides step-by-step instructions for adding a new social media platform to Myrcat, using Mastodon as an example.

## Overview

Myrcat's architecture is designed to make adding new social media platforms straightforward. The key integration points are:

1. Configuration section in `config.ini`
2. Client setup method in `SocialMediaManager`
3. Platform-specific update method
4. Integration into the update loop

This guide demonstrates the process using Mastodon as an example, but the same approach applies to any platform.

## Required Files to Modify

1. `/myrcat/managers/social_media.py` - Primary integration file
2. `/conf/config.ini.example` - Add configuration section
3. `/myrcat/managers/content.py` - Optional content customization

## Step 1: Add Dependency

First, add the Mastodon.py library to `requirements.txt`:

```
mastodon.py>=1.8.0
```

## Step 2: Add Configuration Section

Add a new section to `conf/config.ini.example`:

```ini
[mastodon]
# Instance URL (e.g., mastodon.social)
instance = 
# Access token for authentication
access_token = 
# Enable image attachments for Mastodon posts
enable_images = true
# Enable AI-enhanced post content for Mastodon
enable_ai_content = true
# Post frequency limit (hours between posts)
post_frequency = 1
# Image dimensions for Mastodon
image_width = 1200
image_height = 675
# Character limit (Mastodon generally allows 500 characters)
character_limit = 500
```

## Step 3: Add Client Setup Method

Add this method to the `SocialMediaManager` class in `social_media.py`:

```python
def setup_mastodon(self):
    """Initialize Mastodon client."""
    try:
        from mastodon import Mastodon
        
        self.mastodon_instance = self.config["mastodon"]["instance"]
        self.mastodon_token = self.config["mastodon"]["access_token"]
        self.mastodon_enable_images = self.config.getboolean(
            "mastodon", "enable_images", fallback=True
        )
        self.mastodon_enable_ai = self.config.getboolean(
            "mastodon", "enable_ai_content", fallback=True
        )
        self.mastodon_post_frequency = self.config.getint(
            "mastodon", "post_frequency", fallback=1
        )
        self.mastodon_char_limit = self.config.getint(
            "mastodon", "character_limit", fallback=500
        )
        
        # Create Mastodon client
        self.mastodon = Mastodon(
            api_base_url=f"https://{self.mastodon_instance}",
            access_token=self.mastodon_token
        )
        
        # Get image dimensions from config
        self.mastodon_image_width = self.config.getint(
            "mastodon", "image_width", fallback=1200
        )
        self.mastodon_image_height = self.config.getint(
            "mastodon", "image_height", fallback=675
        )
        
        logging.debug(
            f"Mastodon initialized for instance: {self.mastodon_instance} "
            f"(images: {'enabled' if self.mastodon_enable_images else 'disabled'}, "
            f"AI: {'enabled' if self.mastodon_enable_ai else 'disabled'}, "
            f"image size: {self.mastodon_image_width}x{self.mastodon_image_height})"
        )
    except Exception as e:
        logging.error(f"💥 Mastodon setup error: {str(e)}")
        self.mastodon = None
```

## Step 4: Add the Update Method

Add this method to handle posting tracks to Mastodon:

```python
async def update_mastodon(self, track: TrackInfo):
    """Post track to Mastodon.
    
    Args:
        track: TrackInfo object containing track information
    """
    if not hasattr(self, "mastodon") or self.mastodon is None:
        logging.warning("⚠️ Mastodon client not initialized")
        return
        
    # Check if we should post now (frequency and artist repost limits)
    if not self._should_post_now("Mastodon"):
        return
    
    # Check if this artist was recently posted
    if await self._is_artist_recently_posted("Mastodon", track.artist):
        logging.debug(f"⏱️ Skipping Mastodon post - same artist posted recently: {track.artist}")
        return
        
    try:
        # Generate content for post
        content = await self.content_generator.generate_content(
            track, "Mastodon", self.mastodon_enable_ai, self.mastodon_char_limit
        )
        
        media_id = None
        image_path = None
        
        # Handle image attachment if enabled
        if self.mastodon_enable_images and track.image:
            try:
                # Resize image for Mastodon
                image_path = await self.artwork_manager.resize_image_for_social(
                    track.image, 
                    self.mastodon_image_width, 
                    self.mastodon_image_height
                )
                
                if image_path:
                    # Upload media
                    media_response = self.mastodon.media_post(
                        image_path,
                        description=f"Album artwork for {track.title} by {track.artist}"
                    )
                    media_id = media_response["id"]
                    logging.debug(f"🖼️ Uploaded image to Mastodon: {media_id}")
            except Exception as e:
                logging.error(f"💥 Error uploading image to Mastodon: {e}")
        
        # Post to Mastodon
        if media_id:
            response = self.mastodon.status_post(
                content,
                media_ids=[media_id],
                visibility="public"
            )
        else:
            response = self.mastodon.status_post(
                content,
                visibility="public"
            )
        
        # Get post ID 
        post_id = response["id"]
        post_url = response["url"]
        
        logging.info(f"📱 Posted to Mastodon: {post_url}")
        
        # Record post in analytics
        await self.analytics.track_post(
            platform="Mastodon",
            track=track,
            post_id=post_id,
            post_url=post_url,
            content=content,
            has_image=bool(media_id)
        )
        
        # Clean up temporary image file
        if image_path and isinstance(image_path, str):
            try:
                import os
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as e:
                logging.warning(f"⚠️ Failed to clean up temporary Mastodon image: {e}")
    
    except Exception as e:
        logging.error(f"💥 Error posting to Mastodon: {e}")
        # Add to errors in analytics
        await self.analytics.track_error("Mastodon", track, str(e))
```

## Step 5: Add Mastodon Engagement Tracking

Add a method to check engagement metrics:

```python
async def _check_mastodon_engagement(self):
    """Check engagement metrics for recent Mastodon posts."""
    if not hasattr(self, "mastodon") or self.mastodon is None:
        return
        
    try:
        # Get recent posts from database
        recent_posts = await self.analytics.get_recent_posts("Mastodon")
        
        for post in recent_posts:
            post_id = post["post_id"]
            
            try:
                # Get status from Mastodon API
                status = self.mastodon.status(post_id)
                
                # Extract engagement metrics
                likes = status.get("favourites_count", 0)
                shares = status.get("reblogs_count", 0)
                comments = status.get("replies_count", 0)
                
                # Update engagement in database
                await self.analytics.update_engagement(
                    platform="Mastodon",
                    post_id=post_id,
                    likes=likes,
                    shares=shares,
                    comments=comments
                )
                
                logging.debug(f"📊 Updated Mastodon engagement for post {post_id}")
            except Exception as e:
                logging.warning(f"⚠️ Error checking Mastodon post {post_id}: {e}")
    except Exception as e:
        logging.error(f"💥 Error checking Mastodon engagement: {e}")
```

## Step 6: Add to the Update Loop

Modify the following methods in `SocialMediaManager`:

1. Add to `__init__` to initialize the platform:

```python
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
    if "Mastodon" not in self.disabled_services:  # Add this line
        self.setup_mastodon()                     # Add this line
```

2. Add to `update_social_media`:

```python
updates = {
    "Last.FM": self.update_lastfm,
    "ListenBrainz": self.update_listenbrainz,
    "Bluesky": self.update_bluesky,
    "Facebook": self.update_facebook,
    "Mastodon": self.update_mastodon,  # Add this line
}
```

3. Add to `check_post_engagement`:

```python
# For now, we'll implement Bluesky engagement checking
if (
    "Bluesky" not in self.disabled_services
    and self.bluesky_credentials_valid()
):
    await self._check_bluesky_engagement()

# Add Mastodon engagement checking
if (
    "Mastodon" not in self.disabled_services
    and hasattr(self, "mastodon") and self.mastodon is not None
):
    await self._check_mastodon_engagement()
```

## Step 7: Add Helper Method for Credentials Validation

Add this method to check if Mastodon credentials are valid:

```python
def mastodon_credentials_valid(self) -> bool:
    """Check if Mastodon credentials are valid and complete.
    
    Returns:
        True if credentials are valid, False otherwise
    """
    return (
        hasattr(self, "mastodon") 
        and self.mastodon is not None
        and hasattr(self, "mastodon_instance")
        and self.mastodon_instance
        and hasattr(self, "mastodon_token")
        and self.mastodon_token
    )
```

## Optional: Content Customization

If Mastodon has specific formatting needs, you can extend the `ContentGenerator` class in `content.py`:

```python
def _format_for_mastodon(self, content: str, hashtags: str) -> str:
    """Format content specifically for Mastodon.
    
    Args:
        content: The generated content
        hashtags: The hashtags to append
        
    Returns:
        Formatted content for Mastodon
    """
    # Mastodon-specific formatting could go here
    # For example, handling CWs/content warnings
    return f"{content}\n\n{hashtags}"
```

Then update the `generate_content` method to use this formatter when the platform is "Mastodon".

## Usage Example

Once implemented, you can configure Mastodon in your config.ini:

```ini
[mastodon]
instance = mastodon.social
access_token = your_access_token_here
enable_images = true
enable_ai_content = true
post_frequency = 1
```

## Testability

Create a test for your implementation using Python's unittest framework:

```python
# test/test_mastodon.py
import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from myrcat.managers.social_media import SocialMediaManager
from myrcat.models import TrackInfo

class TestMastodonIntegration(unittest.TestCase):
    # Test implementation
    # ...
```

## Troubleshooting

Common issues when adding a new platform:

1. **Authentication fails**: Verify your token and instance information
2. **Rate limiting**: Ensure post frequency is set appropriately 
3. **Image upload fails**: Check image size constraints and permissions
4. **Content formatting**: Some platforms have specific formatting requirements

## Conclusion

By following these steps, you've successfully added Mastodon support to Myrcat. The same approach can be used to add any other social media platform that has a Python API client available.