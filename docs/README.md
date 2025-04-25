![Myrcat Logo](Myrcat_logo.png)

# Myrcat - Myriad Cataloger - Now Wave Radio's Playout Publisher

🐾🎶 **Myrcat** is a tool for radio stations running the Myriad Playout software from Broadcast Radio. It helps streamline radio station operations by integrating track management, social media updates, and more, all in one tool. Primarily developed for Now Wave Radio's needs, the script can be easily modified to fit other requirements.

## Features

- Monitors Myriad OCP playout info. via a Web API for track changes
- Publishes to social media platforms (Last.FM, Listenbrainz, Facebook, Bluesky)
- Enhanced Bluesky integration with AI-generated content and image support
- Records plays in a SQLite database for SoundExchange reporting and historical analysis
- Manages album artwork sent by Myriad OCP (FTP) for web display
- Provides real-time "Now Playing" information for web display
- Tracks programming and show transitions and statistics
- Social media engagement analytics and tracking
- Reads all configuration details from a config.ini file for easy setup

### Prerequisites

- Python 3.8 or higher
- SQLite3
- Appropriate API credentials for social media services
- Anthropic API key for AI-enhanced content (optional)
- PIL/Pillow for image handling

### Basic Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install package
pip install .

# Copy default config
sudo cp config/myrcat_MYRIAD.ini /etc/myrcat_MYRIAD.ini
```

### System Service Installation

```bash
# Copy service file
sudo cp system/myrcat.service /etc/systemd/system/

# Create system user
sudo useradd -r -s /bin/false myrcat

# Create required directories
sudo mkdir -p /opt/myrcat
sudo mkdir -p /var/lib/myrcat
sudo mkdir -p /var/log/myrcat
sudo mkdir -p /opt/myrcat/templates/social
sudo mkdir -p /opt/myrcat/templates/fonts

# Set permissions
sudo chown -R myrcat:myrcat /opt/myrcat
sudo chown -R myrcat:myrcat /var/lib/myrcat
sudo chown -R myrcat:myrcat /var/log/myrcat

# Initialize database
sudo -u myrcat sqlite3 /var/lib/myrcat/myrcat.db < db/schema.sql

# Enable and start service
sudo systemctl enable myrcat
sudo systemctl start myrcat
```

## Configuration

Edit `config.ini_default` and set your configuration:

```ini
[general]
log_level = INFO
log_file = log/myrcat.log
database_path = myrcat.db
publish_delay = 45

[network]
# Network operation settings
connection_timeout = 10      # Seconds to wait for connections
socket_timeout = 5           # Seconds to wait for socket operations
max_retries = 3              # Default maximum retry count
retry_delay = 2              # Seconds between retries
jitter_factor = 0.1          # Random jitter factor for retry timing
backoff_factor = 2.0         # Exponential backoff multiplier

[server]
host = 192.168.123.106
port = 8080
...
```

### Social Media Setup

Each social media service has its own section in the config file with an `enabled` option that determines whether that service is active. Set `enabled = true` to activate a service.

> **Note:** There is also a global `publish_socials` option in the `[publish_exceptions]` section. If this is set to `false`, no social media posts will be sent regardless of individual service settings. You must set both the global option to `true` AND the service-specific `enabled` option to `true` for a service to be active.
>
> ```ini
> [publish_exceptions]
> publish_socials = true  # Master switch for all social media
> ```

1. Last.FM:

   - Create API application at https://www.last.fm/api/account/create
   - Set enabled = true to activate this service
   - Set api_key and api_secret in config
   ```ini
   [lastfm]
   enabled = true
   api_key = your_api_key
   api_secret = your_api_secret
   username = your_username
   password = your_password
   ```

2. Listenbrainz:

   - Get token from https://listenbrainz.org/profile/
   - Set enabled = true to activate this service
   - Set token in config
   ```ini
   [listenbrainz]
   enabled = true
   token = your_token
   ```

3. Facebook:

   - Create Facebook App at https://developers.facebook.com/apps/
   - Set enabled = true to activate this service
   - Set app_id, app_secret, and page_id in config (tokens are stored in the database)
   - Configure additional Facebook settings:
     ```ini
     [facebook]
     enabled = true
     app_id = your-app-id
     app_secret = your-app-secret
     page_id = your-page-id
     # Enable image attachments for Facebook posts
     enable_images = true
     # Enable AI-enhanced post content for Facebook
     enable_ai_content = true
     # Post frequency limit (hours between posts)
     post_frequency = 1
     # Image dimensions for Facebook
     image_width = 1200
     image_height = 630
     ```
     
     **Important**: Facebook tokens are stored only in the database, not in the configuration file. This improves security by separating credentials from tokens. Use the token CLI utility to generate and manage tokens:
     
     ```bash
     # Generate a new token (interactive process)
     python utils/facebook_token_cli.py generate
     
     # Check current token status
     python utils/facebook_token_cli.py status
     
     # Force token refresh
     python utils/facebook_token_cli.py refresh
     
     # View token history
     python utils/facebook_token_cli.py history
     ```

4. Bluesky:

   - Set enabled = true to activate this service
   - Set handle and app_password in config
   - Configure additional Bluesky settings:
     ```ini
     [bluesky]
     enabled = true
     handle = your-handle.bsky.social
     app_password = your-app-password
     # Enable image attachments for Bluesky posts
     enable_images = true
     # Enable AI-enhanced post content for Bluesky
     enable_ai_content = true
     # Post frequency limit (hours between posts)
     post_frequency = 1
     ```

5. AI Content Generation (Optional):

   - Get an Anthropic API key for Claude integration
   - Configure AI settings:
     ```ini
     [ai_content]
     # AI model to use for content generation
     model = claude-3-7-sonnet-latest
     # API key for Anthropic
     anthropic_api_key = your-api-key
     # Maximum tokens for AI generation
     max_tokens = 150
     # Temperature for content generation (0.0-1.0)
     temperature = 0.7
     # Percentage of posts to enhance with AI (0.0-1.0)
     ai_post_ratio = 0.3
     ```

6. Social Analytics:
   - Configure engagement tracking:
     ```ini
     [social_analytics]
     # Enable tracking social media engagement
     enable_analytics = true
     # Check frequency in hours (how often to check post engagement)
     check_frequency = 6
     # Retention period for analytics data in days
     retention_period = 90
     ```

### Command Line

```bash
# Run with default config
myrcat

# Run with custom config
myrcat -c /path/to/config.ini
```

### Service Management

```bash
# Start service
sudo systemctl start myrcat

# Check status
sudo systemctl status myrcat

# View logs
sudo journalctl -u myrcat
```

## Enhanced Social Media Features

### AI-Enhanced Content

Myrcat can generate engaging social media posts using the Anthropic Claude AI model:

- Contextual post generation based on track metadata
- Multiple post templates for variety
- Automatic hashtag generation based on track genre and era
- Customizable AI parameters for temperature and token length

#### Post Generation Process

Myrcat uses a sophisticated process to select and generate content for social media posts:

1. **Selection Logic**: The system decides whether to use an AI-generated post or a template-based post based on:

   - If testing mode is enabled (`testing_mode = true`), AI content is always used
   - If not in testing mode, AI content is randomly selected based on the `ai_post_ratio` setting (e.g., 0.3 means 30% of posts use AI)
   - AI generation requires a valid Anthropic API key

2. **AI-Generated Post Selection Hierarchy**:
   When using AI-generated content, prompts are selected in this order:

   a. **Program-Specific Prompts** (Highest Priority)

   - If the track has a program name, the system looks for a prompt file matching the program name
   - Example: For a track on "Morning Chill" program, it looks for `morning_chill.txt`

   b. **Time-of-Day Prompts** (Medium Priority)

   - Based on the current hour, selects a time-appropriate prompt:
     - 5 AM to 10 AM: `morning.txt` (morning themes)
     - 10 AM to 3 PM: `daytime.txt` (daytime themes)
     - 3 PM to 7 PM: `afternoon.txt` (afternoon themes)
     - 7 PM to 11 PM: `evening.txt` (evening themes)
     - 11 PM to 5 AM: `late_night.txt` (late night themes)

   c. **Default Prompt** (Low Priority)

   - Falls back to `default.txt` if no program or time-specific prompt is available

   d. **Minimal Fallback** (Last Resort)

   - If all else fails, uses a built-in minimal prompt template

3. **Template-Based Post Selection**:
   When using template-based posts, the selection process is:

   a. **DJ Pick Template** - Used when both presenter and program information is available

   - Format: "DJ Pick: {presenter} has selected {artist}'s '{title}' for your listening pleasure on {program}! 🎧"

   b. **Nostalgic Template** - Used for tracks released before 2000

   - Format: "Taking you back to {year} with {artist}'s '{title}' on Now Wave Radio! 🎵 #ThrowbackTunes"

   c. **With Album Template** - Used when album information is available

   - Format: "🎵 Now Playing on Now Wave Radio:\n{artist} - {title}\nFrom the album: {album}"

   d. **Standard Template** - Default fallback

   - Format: "🎵 Now Playing on Now Wave Radio:\n{artist} - {title}"

4. **Hashtag Generation**:
   - For template-based posts, hashtags are automatically generated and appended
   - For AI-generated posts, hashtags are typically included in the AI prompt instructions
   - Standard hashtags include:
     - #NowWaveRadio (always included)
     - Program-specific hashtag (e.g., #MorningChill)
     - Artist hashtag (cleaned and formatted)
     - #NewMusic (for current year releases)

#### Prompt File Variables

All prompt files support these template variables:

| Variable      | Description           | Example             |
| ------------- | --------------------- | ------------------- |
| `{title}`     | Track title           | "Dreams"            |
| `{artist}`    | Artist name           | "Fleetwood Mac"     |
| `{album}`     | Album name            | "Rumours"           |
| `{year}`      | Release year          | "1977"              |
| `{program}`   | Radio program name    | "Classic Rock Hour" |
| `{presenter}` | DJ/Presenter name     | "DJ Smith"          |
| `{dow}`       | Current day of week   | "Monday"            |

#### Creating Custom Prompts

Create custom prompt files in the `prompts_directory` (default: `templates/prompts`):

1. **Program-specific prompts**: Name the file after the program (lowercase with underscores)

   - Example: `classic_rock_hour.txt` for the "Classic Rock Hour" program

2. **Time-specific prompts**: Use time period names

   - Examples: `morning.txt`, `evening.txt`, `late_night.txt`

3. **Default prompt**: Use `default.txt` for the fallback prompt

Prompt files should include specific instructions for the AI to generate appropriate content.
Include restrictions like character limits and stylistic guidelines.

### Social Media Analytics

Track the performance of your social media posts:

- Records likes, shares, comments, and other metrics
- Identifies top-performing tracks and content
- Generates platform-specific performance statistics
- Automatic cleanup of old analytics data

## Database Maintenance

Periodic cleanup script for old entries:

```bash
# Clean entries older than 90 days
sqlite3 /var/lib/myrcat/myrcat.db "DELETE FROM realtime WHERE timestamp < strftime('%s', 'now', '-90 days');"

# Clean old social media analytics data
sqlite3 /var/lib/myrcat/myrcat.db "DELETE FROM social_media_engagement WHERE checked_at < datetime('now', '-90 days');"
sqlite3 /var/lib/myrcat/myrcat.db "DELETE FROM social_media_posts WHERE posted_at < datetime('now', '-90 days');"
```

## Development Utilities

### Facebook Token Management

A command-line utility is available to help manage Facebook tokens:

```bash
# Generate a new token interactively
python utils/facebook_token_cli.py generate

# Check current token status
python utils/facebook_token_cli.py status

# Force refresh the token
python utils/facebook_token_cli.py refresh

# Show token history
python utils/facebook_token_cli.py history
```

The utility integrates directly with Myrcat and provides:

- Token generation with guided interactive process
- Token status checking with expiration warnings
- Token refresh capabilities
- Token history tracking
- Database-only token storage (improved security)

**Security Improvements**: Facebook tokens are now stored only in the database, not in configuration files. This improves security by separating app credentials from access tokens. The system loads tokens from the database during initialization and maintains token state in memory for better performance.

Facebook tokens generally expire after 60 days, so periodic token refreshes are recommended. The Myrcat system will automatically attempt to refresh tokens when they are nearing expiration or when a token is found to be invalid.

For detailed documentation on the token management system, see `docs/Facebook_token_management.md`.

### Test Prompt Utility

A utility to test AI prompts for social media posts without posting to platforms. This helps you develop and test prompts to see how they generate content for different tracks and scenarios:

```bash
# Run with sample configuration
./testprompt.sh -c utils/testprompt.ini.example

# Create your own test configuration
cp utils/testprompt.ini.example myconfig.ini
# Edit the file to add your API key and customize track info
vim myconfig.ini
# Run with your config
./testprompt.sh -c myconfig.ini
```

#### Testing with Time Simulation

The utility supports simulating different times of day to test time-specific prompts:

```ini
[test_options]
# Simulate a specific hour (0-23) to test time-based prompts
simulated_hour = 8  # Will use morning prompt (5-10 AM)
```

Available time segments for testing:

- Morning: 5-10 AM (`morning.txt`)
- Daytime: 10 AM - 3 PM (`daytime.txt`)
- Afternoon: 3-7 PM (`afternoon.txt`)
- Evening: 7-11 PM (`evening.txt`)
- Late Night: 11 PM - 5 AM (`late_night.txt`)

#### Example Configuration

```ini
[track]
# Track information
artist = Bonobo
title = Ketto
album = Days to Come
year = 2006
program = Morning Chill
presenter = DJ Ambient

[ai_content]
# AI service configuration
model = claude-3-sonnet-20240229
anthropic_api_key = YOUR_API_KEY_HERE
prompts_directory = templates/prompts
```

The utility will show:

- Which prompt was selected and why
- The generated post content
- Character count and stats
- Extracted hashtags
- Token usage estimation (if available)

See `utils/README.md` for more details.

## Troubleshooting

### Common Issues

1. File Monitoring:

   - Check file permissions
   - Verify FTP transfer completion
   - Check debounce_time settings

2. Social Media:

   - Verify API credentials
   - Check network connectivity
   - Review service rate limits

3. AI Content Generation:

   - Verify Anthropic API key is valid
   - Check API rate limits and quotas
   - Ensure aiohttp is installed properly

4. Image Handling:
   - Verify Pillow/PIL is installed
   - Ensure write permissions for temporary files

### Log Locations

- Application log: `./log/myrcat/myrcat.log`
- System service log: `journalctl -u myrcat`

## Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Submit pull request

## License

MIT License - See LICENSE file for details.

## Support

For issues or questions, please file an issue on GitHub or contact:

- website: NowWave.Radio
- email: studio isattheaddress nowwave.radio!
