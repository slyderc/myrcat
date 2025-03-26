![Myrcat Logo](Myrcat_logo.png)

# Myrcat - Myriad Cataloger - Now Wave Radio's Playout Publisher

🐾🎶 **Myrcat** is a tool for radio stations running the Myriad Playout software from Broadcast Radio.  It helps streamline radio station operations by integrating track management, social media updates, and more, all in one tool.  Primarily developed for Now Wave Radio's needs, the script can be easily modified to fit other requirements.

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
- PIL/Pillow for image generation

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
[main]
debug_log = false
verbose_log = true
logfile = /var/log/myrcat/myrcat.log
...
```

### Social Media Setup

1. Last.FM:
   - Create API application at https://www.last.fm/api/account/create
   - Set api_key and api_secret in config

2. Listenbrainz:
   - Get token from https://listenbrainz.org/profile/
   - Set auth_token in config

3. Facebook:
   - Create Facebook App
   - Get page access token
   - Set access_token and page_id in config

4. Bluesky:
   - Set handle and app_password in config
   - Configure additional Bluesky settings:
     ```ini
     [bluesky]
     handle = your-handle.bsky.social
     app_password = your-app-password
     # Enable image attachments for Bluesky posts
     enable_images = true
     # Enable AI-enhanced post content for Bluesky
     enable_ai_content = true
     # Templates directory for custom image generation
     templates_directory = templates/social
     # Fonts directory for custom image generation 
     fonts_directory = templates/fonts
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

### Template Setup

For custom image generation:

1. Create PNG template files in the templates/social directory
2. Add TrueType fonts to the templates/fonts directory:
   - bold.ttf - For track titles
   - regular.ttf - For artist names
   - light.ttf - For additional details

## Usage

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

### Custom Image Generation

When album artwork isn't available, Myrcat can generate custom images:

- Template-based image generation with track information
- Support for custom fonts and backgrounds
- Radio station branding and watermarks
- Automatically attaches to social media posts

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

### Test Prompt Utility

A utility to test AI prompts for social media posts without posting to social platforms:

```bash
# Run with sample configuration
./testprompt.sh -c utils/testprompt.ini.example

# Create your own test configuration
cp utils/testprompt.ini.example myconfig.ini
# Edit the file to add your API key and customize track info
nano myconfig.ini
# Run with your config
./testprompt.sh -c myconfig.ini
```

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

4. Image Generation:
   - Verify Pillow/PIL is installed
   - Check template and font directories exist
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
- website:  NowWave.Radio
- email: studio isattheaddress nowwave.radio!