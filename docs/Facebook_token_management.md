# Facebook Token Management

This document describes the Facebook token management system integrated into Myrcat.

## Overview

Facebook tokens, particularly page access tokens, have limited lifetimes and expire after a period (typically 60 days). The token management system provides:

1. **Token Validation**: Checks if tokens are valid and not expired
2. **Automatic Refreshing**: Refreshes tokens before they expire
3. **Token Storage**: Maintains a history of tokens with timestamps
4. **Configuration Updates**: Updates the config file with new tokens
5. **Status Monitoring**: Provides detailed token status information
6. **CLI Interface**: Command-line tools for token management

## Components

### 1. Integrated Token Management

Token management is integrated directly into the `SocialMediaManager` class with these key methods:

- `_validate_facebook_token()`: Checks if the current token is valid
- `_validate_facebook_token_info()`: Gets detailed token information
- `_refresh_facebook_token()`: Refreshes the token when needed
- `_store_facebook_token()`: Stores token history in database
- `get_facebook_token_status()`: Gets detailed token status

### 2. Database Integration

Token history is stored in a SQLite database table:

```sql
CREATE TABLE IF NOT EXISTS facebook_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_type TEXT NOT NULL,
    access_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    metadata TEXT
)
```

This allows:
- Tracking token history
- Monitoring token expiration times
- Maintaining access to previous tokens if needed

### 3. Command-Line Interface

A separate CLI tool (`facebook_token_cli.py`) provides access to token management functions:

```bash
# Check current token status
python utils/facebook_token_cli.py status

# Force refresh the token
python utils/facebook_token_cli.py refresh

# Show token history
python utils/facebook_token_cli.py history
```

### 4. Token Validation

The system validates tokens at strategic points:
- Before posting to Facebook 
- When checking post engagement
- When explicitly checking token status
- Cached validation results are used when possible (validation_interval: 1 hour)

Note that validation is implemented as async coroutines, so they must be properly awaited. Token validation is NOT performed during initialization to avoid async issues in synchronous contexts.

### 5. Automatic Token Refresh

The system will automatically refresh tokens when:
- They are within 3 days of expiration
- Token validation fails
- Posting to Facebook with an invalid token

## Token Refresh Process

1. The system uses the Facebook Graph API to exchange the current token for a new one
2. The new token is stored in the database with creation and expiration timestamps
3. The config file is updated with the new token
4. The memory representation is updated with the new token
5. The Facebook GraphAPI client is reinitialized with the new token

## Configuration Requirements

For token management to function properly, these fields must be set in the config.ini file:

```ini
[facebook]
app_id = your-facebook-app-id
app_secret = your-facebook-app-secret
access_token = your-page-access-token
page_id = your-facebook-page-id
```

## Security Considerations

- Access tokens are stored in the database and config file
- For production deployments, ensure these files have appropriate permissions
- The app_secret in particular should be protected
- Consider encrypting sensitive information in the database for higher security

## Troubleshooting

Common token issues:

1. **Invalid App ID/Secret**: Check your Facebook Developer account
2. **Expired Token**: Use the CLI to refresh the token
3. **Insufficient Permissions**: The token must have these permissions:
   - pages_show_list
   - pages_read_engagement
   - pages_manage_posts
4. **Database Connection Issues**: Check database file permissions
5. **Config File Issues**: Ensure config file is readable and writable

## Future Improvements

Potential enhancements for token management:

1. Implement token encryption in the database
2. Add support for user access tokens
3. Add support for multiple Facebook pages
4. Implement a web interface for token management
5. Add support for Instagram tokens (linked to Facebook)
6. Add more detailed token analytics and logging
7. Implement true OAuth 2.0 flow for token acquisition rather than manual entry