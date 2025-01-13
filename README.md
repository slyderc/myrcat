![Myrcat Logo](Myrcat_logo.png)

# Myrcat - Myriad Cataloger - Now Wave Radio's Playout Publisher

🐾🎶 **Myrcat** is a tool for radio stations running the Myriad Playout software from Broadcast Radio.  It helps streamline radio station operations by integrating track management, social media updates, and more, all in one tool.  Primarily developed for Now Wave Radio's needs, the script can be easily modified to fit other requirements.

## Features

- Monitors Myriad OCP playout info. via a Web API for track changes
- Publishes to social media platforms (Last.FM, Listenbrainz, Facebook, Bluesky)
- Records plays in a SQLite database for SoundExchange reporting and historical analysis
- Manages album artwork sent by Myriad OCP (FTP) for web display
- Provides real-time "Now Playing" information for web display
- Tracks programming and show transitions and statistics
- Reads all configuration details from a config.ini file for easy setup

### Prerequisites

- Python 3.8 or higher
- SQLite3
- Appropriate API credentials for social media services

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
   - Set username and password in config

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

## Database Maintenance

Periodic cleanup script for old entries:

```bash
# Clean entries older than 90 days
sqlite3 /var/lib/myrcat/myrcat.db "DELETE FROM realtime WHERE timestamp < strftime('%s', 'now', '-90 days');"
```

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
