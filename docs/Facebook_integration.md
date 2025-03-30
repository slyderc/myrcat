# Facebook Integration Enhancement Plan

This document outlines a comprehensive plan to enhance the Facebook integration in Myrcat to achieve feature parity with the Bluesky implementation.

## Current State Analysis

The current Facebook implementation provides basic functionality:
- Posts track information to a Facebook page feed
- Uses simple text-only format
- Tracks posts in analytics system (with synthetic IDs)
- Respects artist repost window to prevent duplicate content

However, compared to Bluesky, it lacks several key features:
- No image attachment support
- No AI-enhanced content generation
- No engagement metrics tracking
- Limited configuration options
- No retry logic or robust error handling

## Enhancement Plan

### 1. Configuration Enhancements

Add these options to the `[facebook]` section of config.ini:

```ini
[facebook]
app_id = 
app_secret = 
access_token = 
page_id = 
# New configuration options
enable_images = true
enable_ai_content = true
post_frequency = 1
image_width = 1200
image_height = 630
character_limit = 500
```

### 2. Setup Method Enhancement

Update the `setup_facebook()` method to handle new configuration options:

```python
def setup_facebook(self):
    """Initialize Facebook Graph API client."""
    try:
        self.facebook = GraphAPI(self.config["facebook"]["access_token"])
        self.fb_page_id = self.config["facebook"]["page_id"]
        
        # New configuration options
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
        
        # Image dimensions
        self.fb_image_width = self.config.getint(
            "facebook", "image_width", fallback=1200
        )
        self.fb_image_height = self.config.getint(
            "facebook", "image_height", fallback=630
        )
        
        logging.debug(
            f"Facebook initialized for page: {self.fb_page_id} "
            f"(images: {'enabled' if self.fb_enable_images else 'disabled'}, "
            f"AI: {'enabled' if self.fb_enable_ai else 'disabled'}, "
            f"image size: {self.fb_image_width}x{self.fb_image_height})"
        )
    except Exception as e:
        logging.error(f"💥 Facebook setup error: {str(e)}")
        self.facebook = None
```

### 3. Add Credential Validation Methods

Add methods for Facebook credential validation and token management:

```python
def facebook_credentials_valid(self) -> bool:
    """Check if Facebook credentials are valid and complete.
    
    Returns:
        True if credentials are valid, False otherwise
    """
    # First check if we have the basic credentials
    has_credentials = (
        hasattr(self, "facebook") 
        and self.facebook is not None
        and hasattr(self, "fb_page_id")
        and self.fb_page_id
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
        
    # Schedule an async validation
    self._schedule_fb_token_validation()
    
    # Return true if we have credentials, even if we haven't validated the token yet
    return has_credentials

def _schedule_fb_token_validation(self):
    """Schedule Facebook token validation to run in the background."""
    async def _run_validation():
        is_valid = await self._validate_facebook_token()
        self._fb_token_valid = is_valid
        self._last_fb_token_validation = time.time()
        
        if not is_valid:
            logging.warning("⚠️ Facebook token is invalid or expired")
            
    # Create and start the task
    import asyncio
    asyncio.create_task(_run_validation())

async def _validate_facebook_token(self) -> bool:
    """Validate if the Facebook access token is still valid.
    
    Returns:
        True if token is valid, False otherwise
    """
    if not hasattr(self, "facebook") or self.facebook is None:
        return False
        
    try:
        # Use the 'debug_token' endpoint to validate the token
        debug_token_info = self.facebook.debug_token(
            input_token=self.config["facebook"]["access_token"]
        )
        
        # Check if token is valid
        is_valid = debug_token_info.get("data", {}).get("is_valid", False)
        
        if not is_valid:
            error_message = debug_token_info.get("data", {}).get("error", {}).get("message", "Unknown error")
            logging.warning(f"⚠️ Facebook token validation failed: {error_message}")
            return False
            
        # Check expiration - warn if token will expire soon (within 7 days)
        expires_at = debug_token_info.get("data", {}).get("expires_at", 0)
        if expires_at:
            expiry_date = datetime.fromtimestamp(expires_at)
            days_remaining = (expiry_date - datetime.now()).days
            
            if days_remaining <= 7:
                logging.warning(f"⚠️ Facebook token will expire in {days_remaining} days - consider refreshing")
                
        return True
    except Exception as e:
        logging.error(f"💥 Error validating Facebook token: {e}")
        return False

async def _refresh_facebook_token(self):
    """Attempt to refresh the Facebook access token.
    
    Returns:
        True if token was refreshed successfully, False otherwise
    """
    if not hasattr(self, "facebook") or self.facebook is None:
        return False
        
    try:
        # Facebook Graph API method to extend token lifetime
        # This requires app_id and app_secret to be available
        if not self.config["facebook"].get("app_id") or not self.config["facebook"].get("app_secret"):
            logging.warning("⚠️ Cannot refresh Facebook token: app_id or app_secret missing")
            return False
            
        # Exchange short-lived token for a long-lived one
        app_id = self.config["facebook"]["app_id"]
        app_secret = self.config["facebook"]["app_secret"]
        current_token = self.config["facebook"]["access_token"]
        
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
            
            # Log the new expiration if available
            if "expires_in" in result:
                expires_in_days = result["expires_in"] / 86400  # Convert seconds to days
                logging.info(f"✅ Facebook token refreshed. New token expires in {expires_in_days:.1f} days")
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
```

Also update the `setup_facebook` method to initialize token validation state:

```python
def setup_facebook(self):
    """Initialize Facebook Graph API client."""
    try:
        self.facebook = GraphAPI(self.config["facebook"]["access_token"])
        self.fb_page_id = self.config["facebook"]["page_id"]
        
        # Initialize token validation state
        self._fb_token_valid = True  # Assume valid until checked
        self._last_fb_token_validation = 0  # Force validation on first use
        
        # New configuration options
        # ... [rest of the setup code]
```

### 4. Enhanced Update Method

Rewrite the `update_facebook()` method to support images and AI content, and include token validation:

```python
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
        # Generate content (AI or template-based)
        content_source = "template"
        source_details = "standard"
        
        if hasattr(self, "fb_enable_ai") and self.fb_enable_ai:
            content, content_source, source_details = await self.content_generator.generate_content(
                track, "Facebook", use_ai=True, char_limit=self.fb_char_limit
            )
        else:
            # Basic template content
            content = f"Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
            if track.album:
                content += f"\nAlbum: {track.album}"
            if track.program:
                content += f"\nProgram: {track.program}"
            if track.presenter:
                content += f"\nPresenter: {track.presenter}"
        
        post_args = {
            "message": content
        }
        
        # Handle image attachment
        image_path = None
        post_with_image = False
        
        if hasattr(self, "fb_enable_images") and self.fb_enable_images and track.image:
            try:
                # Resize image for Facebook
                image_path = await self.artwork_manager.resize_image_for_social(
                    track.image, 
                    self.fb_image_width, 
                    self.fb_image_height
                )
                
                if image_path:
                    # Facebook API requires open file objects for photos
                    with open(image_path, "rb") as image_file:
                        post_args["source"] = image_file
                        response = await self._facebook_api_call_with_retry(
                            self.facebook.put_photo,
                            image=image_file,
                            message=content,
                            album_path=f"{self.fb_page_id}/photos"
                        )
                        post_with_image = True
            except Exception as e:
                logging.error(f"💥 Error uploading image to Facebook: {e}")
                post_with_image = False
        
        # If no image or image upload failed, post as text only
        if not post_with_image:
            response = await self._facebook_api_call_with_retry(
                self.facebook.put_object,
                parent_object=self.fb_page_id, 
                connection_name="feed", 
                message=content
            )
            
        # Extract post ID
        if isinstance(response, dict) and "id" in response:
            post_id = response["id"]
            post_url = f"https://facebook.com/{post_id}"
        else:
            # Generate synthetic ID for tracking
            post_id = f"fb_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            post_url = None
        
        # Track post in analytics
        await self.analytics.track_post(
            platform="Facebook",
            track=track,
            post_id=post_id,
            post_url=post_url,
            content=content,
            has_image=post_with_image
        )
        
        # Add detail about content source to log
        if content_source == "ai":
            source_log = f"AI content (prompt: {source_details})"
        else:
            source_log = f"template content (template: {source_details})"
            
        logging.info(
            f"📘 Facebook post created using {source_log} with "
            f"{'image' if post_with_image else 'no image'}"
        )
        
        # Clean up temporary image file
        if image_path and isinstance(image_path, str):
            try:
                import os
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as e:
                logging.warning(f"⚠️ Failed to clean up temporary Facebook image: {e}")
                
        return True
        
    except Exception as e:
        logging.error(f"💥 Facebook update error: {e}")
        # Add to errors in analytics
        await self.analytics.track_error("Facebook", track, str(e))
        return False
```

### 5. Add Engagement Tracking

Implement a method to check and update engagement metrics for Facebook posts:

```python
async def _check_facebook_engagement(self):
    """Check engagement metrics for recent Facebook posts."""
    if not hasattr(self, "facebook") or self.facebook is None:
        return
        
    try:
        # Get recent posts from database
        recent_posts = await self.analytics.get_recent_posts("Facebook")
        
        for post in recent_posts:
            post_id = post["post_id"]
            
            # Skip posts with synthetic IDs
            if post_id.startswith("fb_"):
                continue
                
            try:
                # Get post engagement metrics from Facebook API
                engagement = await self._facebook_api_call_with_retry(
                    self.facebook.get_object,
                    id=post_id,
                    fields="reactions.summary(true),shares,comments.summary(true)"
                )
                
                # Extract metrics
                likes = engagement.get("reactions", {}).get("summary", {}).get("total_count", 0)
                shares = engagement.get("shares", {}).get("count", 0) if "shares" in engagement else 0
                comments = engagement.get("comments", {}).get("summary", {}).get("total_count", 0)
                
                # Update engagement in database
                await self.analytics.update_engagement(
                    platform="Facebook",
                    post_id=post_id,
                    likes=likes,
                    shares=shares,
                    comments=comments
                )
                
                logging.debug(f"📊 Updated Facebook engagement for post {post_id}")
            except Exception as e:
                logging.warning(f"⚠️ Error checking Facebook post {post_id}: {e}")
    except Exception as e:
        logging.error(f"💥 Error checking Facebook engagement: {e}")
```

### 6. Add API Call Retry Logic

Implement retry logic for Facebook API calls:

```python
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
```

### 7. Update Engagement Checking Integration

Modify the `check_post_engagement` method to include Facebook:

```python
async def check_post_engagement(self):
    """Check engagement metrics for recent posts and update analytics."""
    if not hasattr(self, "analytics") or not self.analytics.enabled:
        return

    try:
        # For now, we'll implement Bluesky engagement checking
        if (
            "Bluesky" not in self.disabled_services
            and self.bluesky_credentials_valid()
        ):
            await self._check_bluesky_engagement()
            
        # Add Facebook engagement checking
        if (
            "Facebook" not in self.disabled_services
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
```

### 8. Add Content Generator Support

Ensure Facebook-specific content formatting in the ContentGenerator class:

```python
def _format_for_facebook(self, content: str, hashtags: str) -> str:
    """Format content specifically for Facebook.
    
    Args:
        content: The generated content
        hashtags: The hashtags to append
        
    Returns:
        Formatted content for Facebook
    """
    # Facebook-specific formatting
    # Facebook displays hashtags as inline text, so integrate them naturally
    return f"{content}\n\n{hashtags}"
```

## Implementation Strategy

### Phase 1: Configuration and Setup Enhancement
1. Update config.ini.example with new Facebook options
2. Enhance the setup_facebook() method
3. Add facebook_credentials_valid() method
4. Update social media manager initialization

### Phase 2: Content Generation and Image Support
1. Implement AI content generation integration
2. Add image resizing and attachment support
3. Create facebook-specific content formatting
4. Update post creation logic

### Phase 3: Engagement Tracking
1. Implement _check_facebook_engagement method
2. Integrate with check_post_engagement
3. Update analytics.track_post method to handle Facebook-specific fields

### Phase 4: Error Handling and Retry Logic
1. Implement _facebook_api_call_with_retry method
2. Replace direct API calls with retry-wrapped versions
3. Add comprehensive error handling

## Testing Strategy

1. **Configuration Testing**:
   - Test new configuration options are loaded correctly
   - Test defaults are applied appropriately

2. **Post Creation Testing**:
   - Test text-only posts work correctly
   - Test image attachment works correctly
   - Test AI content generation integration

3. **Engagement Testing**:
   - Test engagement metrics are retrieved correctly
   - Test metrics are stored correctly in the database

4. **Retry Logic Testing**:
   - Test API call retries on rate limit errors
   - Test API call retries on temporary errors

## Benefits

1. **Feature Parity**: Brings Facebook integration to the same level as Bluesky
2. **Enhanced User Experience**: Rich posts with images and AI-generated content
3. **Better Analytics**: Complete engagement tracking for Facebook posts
4. **Improved Reliability**: Robust error handling and retry logic
5. **Consistent API**: Similar interface for all social media platforms
6. **Maintainability**: Common patterns across platform implementations

## Conclusion

This enhancement plan provides a clear roadmap to achieving feature parity between Facebook and Bluesky integrations in Myrcat. By following the phased implementation approach, we can incrementally improve the Facebook functionality while maintaining system stability.

The end result will be a more robust, feature-rich Facebook integration that allows radio stations to create engaging, image-rich posts with AI-enhanced content and track engagement metrics effectively.