# Myrcat - Now Wave Radio's Playout Publisher

Myrcat is an automation script that interfaces with Myriad Playout to publish track information to various social media platforms and manage web integration for Now Wave Radio.

## Features

- Monitors Myriad OCP playout info. via a Web API for track changes
- Publishes to social media platforms (Last.FM, Listenbrainz, Facebook, Bluesky)
- Records plays in a SQLite database for SoundExchange reporting
- Manages album artwork sent by Myriad OCP (FTP) for web display
- Provides real-time "Now Playing" information for web display
- Tracks program transitions and statistics
- Reads all configuration details from a config.ini file for easy setup
- Logs all activity to a log file based on a level as defined in the configuration file

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
sudo cp config/pubnwr_MYRIAD.ini /etc/pubnwr_MYRIAD.ini
```

### System Service Installation

```bash
# Copy service file
sudo cp system/pubnwr.service /etc/systemd/system/

# Create system user
sudo useradd -r -s /bin/false pubnwr

# Create required directories
sudo mkdir -p /opt/pubnwr
sudo mkdir -p /var/lib/pubnwr
sudo mkdir -p /var/log/pubnwr

# Set permissions
sudo chown -R pubnwr:pubnwr /opt/pubnwr
sudo chown -R pubnwr:pubnwr /var/lib/pubnwr
sudo chown -R pubnwr:pubnwr /var/log/pubnwr

# Initialize database
sudo -u pubnwr sqlite3 /var/lib/pubnwr/pubnwr.db < db/schema.sql

# Enable and start service
sudo systemctl enable pubnwr
sudo systemctl start pubnwr
```

## Configuration

Edit `/etc/pubnwr_MYRIAD.ini` and set your configuration:

```ini
[main]
debug_log = false
verbose_log = true
logfile = /var/log/pubnwr/pubnwr.log
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
pubnwr

# Run with custom config
pubnwr /path/to/config.ini
```

### Service Management

```bash
# Start service
sudo systemctl start pubnwr

# Check status
sudo systemctl status pubnwr

# View logs
sudo journalctl -u pubnwr
```

## Database Maintenance

Periodic cleanup script for old entries:

```bash
# Clean entries older than 90 days
sqlite3 /var/lib/pubnwr/pubnwr.db "DELETE FROM realtime WHERE timestamp < strftime('%s', 'now', '-90 days');"
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

- Application log: `./log/pubnwr/pubnwr.log`
- System service log: `journalctl -u pubnwr`

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
# myrcat
