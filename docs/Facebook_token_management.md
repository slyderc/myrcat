# Facebook Token Management

This document describes the Facebook token management system integrated into Myrcat.

## Overview

Facebook tokens, particularly page access tokens, have limited lifetimes and expire after a period (typically 60 days). The token management system provides:

1. **Token Validation**: Checks if tokens are valid and not expired
2. **Automatic Refreshing**: Refreshes tokens before they expire
3. **Token Storage**: Stores tokens securely in the database, not in config files
4. **In-Memory State**: Maintains token state in memory for performance
5. **Status Monitoring**: Provides detailed token status information
6. **CLI Interface**: Command-line tools for token management

## Components

### 1. Integrated Token Management

Token management is integrated directly into the `SocialMediaManager` class with these key methods:

- `_validate_facebook_token()`: Checks if the current token is valid
- `_validate_facebook_token_info()`: Gets detailed token information
- `_refresh_facebook_token()`: Refreshes the token when needed
- `_store_facebook_token()`: Stores token in the database
- `get_facebook_token_status()`: Gets detailed token status

### 2. Database-Only Token Storage

Tokens are now stored ONLY in the database, not in configuration files. This improves security and centralizes token management. The database uses a simplified schema:

```sql
CREATE TABLE IF NOT EXISTS facebook_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    access_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    metadata TEXT
)
```

While the system only uses the most recent valid token, history is maintained for auditing purposes.

### 3. Command-Line Interface

An enhanced CLI tool (`facebook_token_cli.py`) provides access to token management functions:

```bash
# Check current token status
python utils/facebook_token_cli.py status

# Force refresh the token
python utils/facebook_token_cli.py refresh

# Generate a new token interactively
python utils/facebook_token_cli.py generate

# Show token history
python utils/facebook_token_cli.py history
```

### 4. Token Validation

The system validates tokens at strategic points:
- Before posting to Facebook 
- When checking post engagement
- When explicitly checking token status
- Cached validation results are used when possible (validation_interval: 1 hour)

Validation is now based on token state maintained in memory, with expiration dates checked for quick validation without API calls.

### 5. Automatic Token Refresh

The system will automatically refresh tokens when:
- They are within 3 days of expiration
- Token validation fails
- Posting to Facebook with an invalid token

## Token Refresh Process

1. The system uses the Facebook Graph API to exchange the current token for a new one
2. The new token is stored in the database with creation and expiration timestamps
3. The in-memory token state is updated
4. The Facebook GraphAPI client is reinitialized with the new token

## Configuration Requirements

For token management to function properly, these fields must be set in the config.ini file:

```ini
[facebook]
enabled = true  # Set to true to activate Facebook integration
app_id = your-facebook-app-id
app_secret = your-facebook-app-secret
page_id = your-facebook-page-id
```

**Important**: The access_token is no longer stored in the configuration file. All tokens are stored in the database only.

In addition, the global social media publishing switch must be enabled:

```ini
[publish_exceptions]
publish_socials = true
```

Both the global `publish_socials` setting and the Facebook-specific `enabled` setting must be `true` for Facebook posting to be active.

## Generating a New Token

The new `generate` command in the CLI tool guides you through creating a new token:

```bash
python utils/facebook_token_cli.py generate
```

This interactive process will:
1. Open the Facebook Graph API Explorer in your browser
2. Guide you through permission selection
3. Help you generate a token with the right scope
4. Validate and store the token in the database
5. Initialize the system to use the new token

## Security Improvements

- Access tokens are now stored ONLY in the database, not in config files
- Token data is loaded into memory during initialization
- Only app credentials (app_id, app_secret) remain in the config file
- For production deployments, ensure database files have appropriate permissions

## Troubleshooting

Common token issues:

1. **No Token in Database**: Use the CLI's `generate` command to create a new token
2. **Invalid App ID/Secret**: Check your Facebook Developer account
3. **Expired Token**: Use the CLI to refresh the token
4. **Insufficient Permissions**: The token must have these permissions:
   - pages_show_list
   - pages_read_engagement
   - pages_manage_posts
5. **Database Connection Issues**: Check database file permissions

## Future Improvements

Potential enhancements for token management:

1. Implement token encryption in the database
2. Add support for user access tokens
3. Add support for multiple Facebook pages
4. Implement a web interface for token management
5. Add support for Instagram tokens (linked to Facebook)
6. Add more detailed token analytics and logging
7. Implement true OAuth 2.0 flow for token acquisition rather than manual entry