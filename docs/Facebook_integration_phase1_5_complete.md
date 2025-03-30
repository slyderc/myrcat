# Facebook Integration Enhancement - Phase 1.5 Complete

We have successfully implemented Phase 1.5 of the Facebook integration enhancement plan, which focuses on adding token validation and refresh functionality. This phase builds on the foundation established in Phase 1 to properly handle Facebook's authentication requirements.

## Completed Tasks

### 1. Enhanced Token Validation in Credential Checking

Updated the `facebook_credentials_valid()` method to include token validation:

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
```

This implementation:
- First checks for basic credentials
- Uses a caching mechanism to avoid checking token validity on every operation
- Schedules background validation to maintain performance
- Uses a 1-hour validation interval to balance security and efficiency

### 2. Added Token Validation Scheduling

Implemented a method to schedule validation without blocking operations:

```python
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
```

This ensures token validation happens asynchronously without blocking the main thread.

### 3. Implemented Token Validation Method

Added a comprehensive token validation method:

```python
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
```

This method:
- Uses Facebook's debug_token endpoint to check token validity
- Extracts expiration information to provide warnings
- Provides detailed error logging
- Has comprehensive exception handling

### 4. Added Token Refresh Capability

Implemented a token refresh method to extend token lifetime:

```python
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

This method:
- Uses Facebook's OAuth token exchange mechanism
- Requires app_id and app_secret for token exchange
- Updates the client with the new token when successful
- Provides detailed logging about token expiration

### 5. Updated Setup Method with Validation State

Modified the `setup_facebook()` method to initialize token validation state:

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
        # ... [rest of setup code]
```

This ensures proper initialization of token validation state during setup.

### 6. Enhanced the Update Method with Token Validation

Updated the `update_facebook()` method to include token validation and refresh:

```python
async def update_facebook(self, track: TrackInfo):
    """Update Facebook page with current track."""
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
        
    # Rest of the method...
```

This enhancement:
- Validates the token before attempting to post
- Automatically attempts to refresh expired tokens
- Provides detailed logging about token status
- Ensures robust error handling

## Benefits

1. **More Robust Authentication**: Properly handles Facebook's token expiration requirements
2. **Improved Reliability**: Prevents posting failures due to expired tokens
3. **Self-Healing**: Automatically refreshes tokens when possible
4. **Performance Optimized**: Uses background validation and caching to maintain efficiency
5. **User Feedback**: Provides clear logging about token status and expiration

## Next Steps

With Phase 1.5 complete, we can proceed to the remaining phases:

### Phase 2: Content Generation and Image Support
- Implement AI content generation integration
- Add image resizing and attachment support
- Create Facebook-specific content formatting
- Update post creation logic

### Phase 3: Engagement Tracking
- Implement _check_facebook_engagement method
- Integrate with check_post_engagement
- Update analytics.track_post method to handle Facebook-specific fields

### Phase 4: Error Handling and Retry Logic
- Implement _facebook_api_call_with_retry method
- Replace direct API calls with retry-wrapped versions
- Add comprehensive error handling