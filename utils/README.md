# Myrcat Utilities

This directory contains helper utilities for the Myrcat system.

## testprompt.py

A utility to test AI prompts for social media posts without posting to social platforms.

### Purpose

This utility allows you to test how different track metadata and prompts generate social media posts, helping to refine prompt templates for better results. It uses the same code as the main application for prompt selection, AI calls, and content generation, ensuring that what you see in the test will match what will be posted in production.

### Features

- Uses the same prompt selection logic as the main application
- Makes real API calls to Claude for authentic results
- Displays formatted sample posts with hashtags
- Shows statistics about the generated post
- Pulls track information from a configuration file
- Doesn't post to any social media platforms

### Usage

1. Copy the sample configuration file:

```bash
cp utils/testprompt.ini.example utils/myconfig.ini
```

2. Edit the configuration file to add your API key and customize track information:

```bash
vim utils/myconfig.ini
```

3. Run the utility:

```bash
./testprompt.sh -c utils/myconfig.ini
```

### Configuration

The configuration file includes:

- `[track]` section: Track metadata (artist, title, album, etc.)
- `[ai_content]` section: AI service settings (API key, model, etc.)
- `[bluesky]` section: Formatting settings (used for hashtag generation)
- `[publish_exceptions]` section: Ensures no actual posts are made

### Example Output

```
========================================================================
Test Prompt Utility - Sample Post Generator
========================================================================

📋 Track Information:
   Artist:    Bonobo
   Title:     Ketto
   Album:     Days to Come
   Year:      2006
   Program:   Morning Chill
   Presenter: DJ Ambient

🤖 AI Generation Information:
   Source:  ai
   Prompt:  morning_chill

📝 Generated Post:
------------------------------------------------------------------------
☕ Ease into your day with Bonobo's atmospheric "Ketto" on Now Wave Radio. DJ Ambient bringing those perfect morning downtempo vibes from 2006's "Days to Come" album. Pure chill perfection!

#NowWaveRadio #MorningChill #Bonobo
------------------------------------------------------------------------

📊 Post Statistics:
   Character count: 212/300 (✅ OK)
   Word count:      35
   Hashtags:        3

🔖 Extracted Hashtags:
   #NowWaveRadio
   #MorningChill
   #Bonobo
```

### Troubleshooting

If you encounter errors:

1. Check your API key is correctly set in the configuration file
2. Ensure the paths to prompt files are correct
3. Check for any missing required fields in the configuration file
4. Run with verbose logging to see what's happening

For more detailed error information, you can modify the logging level in the script to DEBUG.

## facebook_token_manager.py

A utility for managing Facebook access tokens, including generation, validation, and automatic renewal.

### Purpose

This utility helps maintain valid Facebook access tokens for the Myrcat system, ensuring uninterrupted posting to Facebook. It handles:

- Interactive token generation with proper permissions
- Token storage in the database with expiration tracking
- Token validation and status checking
- Automatic token refresh before expiration
- Configuration updates with new tokens

### Features

- OAuth-based authentication flow
- Long-lived page access token generation
- Token expiration tracking
- Database integration for persistent token storage
- Config file integration
- Command-line interface for common operations

### Usage

1. Generate a new token:

```bash
python utils/facebook_token_manager.py generate
```

2. Check the status of the current token:

```bash
python utils/facebook_token_manager.py check
```

3. Refresh the token (if needed):

```bash
python utils/facebook_token_manager.py refresh
```

4. Interactive setup process:

```bash
python utils/facebook_token_manager.py setup
```

### Token Management Flow

The utility implements the following token management flow:

1. **Generation**: Creates a long-lived page access token using OAuth authentication
2. **Storage**: Stores the token in the database with creation and expiration timestamps
3. **Validation**: Checks token validity and expiration using Facebook's debug_token endpoint
4. **Renewal**: Automatically refreshes tokens that are expiring soon

### Auto-Refresh Integration

The Myrcat system is integrated with this utility to enable automatic token refreshing:

- The `SocialMediaManager` checks token validity before posting
- If a token is expiring soon (within 7 days), it attempts auto-refresh
- The TokenManager handles the refresh process and updates the configuration
- The system loads the new token and continues operation without interruption

### Requirements

- Facebook Developer Account
- Facebook App with appropriate permissions:
  - pages_show_list
  - pages_read_engagement
  - pages_manage_posts
- A Facebook Page that you manage
- App ID and App Secret in your config.ini
- Page ID in your config.ini

### Troubleshooting

If you encounter token errors:

1. Run the check command to see the current token status:
   ```bash
   python utils/facebook_token_manager.py check
   ```

2. If the token is invalid, try generating a new one:
   ```bash
   python utils/facebook_token_manager.py generate
   ```

3. Check your app permissions in the Facebook Developer Console
4. Verify your Page ID is correct
5. Ensure your app has been approved for the required permissions

For more detailed error information, run the commands with verbose logging.