# Myrcat Developer Guidelines

## Project Overview
Myrcat (Myriad Cataloger) is Now Wave Radio's playout publisher for stations running Myriad Playout software. It integrates track management, social media updates, and analytics in one comprehensive tool.

## Features
- Monitors Myriad OCP playout via Web API for track changes
- Publishes to social platforms (Last.FM, Listenbrainz, Facebook, Bluesky)
- Enhanced Bluesky integration with AI-generated content and images
- Records plays in SQLite for reporting and analysis
- Manages album artwork for web display
- Provides real-time "Now Playing" information
- Tracks programming transitions and statistics
- Monitors social media engagement

## Setup & Commands
- Setup: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Install in dev mode: `python -m pip install -e .`
- Run: `python myrcat.py` or `python myrcat.py -c /path/to/config.ini`
- Test: `./test/test.sh` (all tests) or `python ./test/lastfm.py` (Last.FM auth)
- Test prompts: `./testprompt.sh -c utils/testprompt.ini.example`

## Project Architecture
- **Core Components**:
  - `Config`: Configuration management with auto-reload
  - `MyriadServer`: Socket server for receiving playout data
  - `TrackInfo`: Data model for track information
  - `Managers`: Specialized components for specific functionality

- **Manager Classes**:
  - `DatabaseManager`: SQLite database operations
  - `ArtworkManager`: Image processing and storage
  - `PlaylistManager`: Current playlist management
  - `HistoryManager`: Track history management
  - `SocialMediaManager`: Social media platform integration
  - `ContentGenerator`: AI-enhanced content creation
  - `SocialMediaAnalytics`: Engagement tracking and reporting
  - `ShowHandler`: Program/show transition management

## Code Style Guidelines
- **Formatting**: 4-space indentation, ~88-100 char line length, PEP 8 compliant
- **Imports**: Standard library first, third-party next, local imports last, alphabetically sorted
- **Types**: Use type hints (`Optional[str]`, `Dict[str, Any]`), return types in signatures
- **Naming**: PascalCase for classes, snake_case for functions/variables, _leading_underscore for private
- **Strings**: Prefer f-strings for formatting
- **Documentation**: Triple double-quotes (`"""`) for docstrings
- **Error Handling**: Use try/except with appropriate logging, graceful recovery when possible
- **Logging**: Use built-in logging module with appropriate levels and descriptive emoji prefixes

## Code Organization
- Use dataclasses for structured data
- Modular design with clear separation of concerns
- Each class should have a single responsibility
- Use async/await for asynchronous operations
- Leverage configuration for customization
- Follow dependency injection pattern
- Implement proper error handling and logging

## Testing Recommendations
- Create unit tests for individual components
- Use mock objects for external dependencies
- Test with various configuration scenarios
- Validate social media post content generation
- Test error handling and recovery

## Development Workflow
1. Review existing code to understand patterns
2. Make changes in feature branches
3. Test thoroughly before submitting PRs
4. Keep the CLAUDE.md guide updated with new patterns
5. Maintain consistency with existing code style