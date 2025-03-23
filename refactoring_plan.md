# Myrcat Refactoring Plan

## Overview
This document outlines a plan to refactor the Myrcat codebase from a monolithic script into a modular package structure.

## Proposed Structure
```
myrcat/
├── __init__.py           # Package initialization, version info
├── main.py               # Entry point, argument parsing
├── core.py               # Main Myrcat application class
├── models.py             # Data models (TrackInfo, ShowInfo)
├── config.py             # Configuration handling
├── utils.py              # Utility functions
├── server.py             # Socket server implementation
├── exceptions.py         # Custom exceptions
├── managers/
│   ├── __init__.py       # Managers package initialization
│   ├── social_media.py   # SocialMediaManager class
│   ├── database.py       # DatabaseManager class
│   ├── artwork.py        # ArtworkManager class
│   ├── playlist.py       # PlaylistManager class
│   ├── history.py        # HistoryManager class
│   └── show.py           # ShowHandler class
```

## Files Breakdown

### 1. `__init__.py`
- Package initialization
- Version information
- Import essential components

### 2. `main.py`
- Command-line argument parsing
- Application entry point
- Configuration loading

### 3. `core.py`
- Main `Myrcat` class implementation
- Component initialization and coordination
- Track processing logic

### 4. `models.py`
- `TrackInfo` dataclass
- `ShowInfo` dataclass
- Other data structures

### 5. `config.py`
- Configuration loading and validation
- Defaults handling
- Configuration utilities

### 6. `utils.py`
- Helper functions
- Common utilities used across modules
- Logging setup

### 7. `server.py`
- Socket server implementation
- Connection handling
- JSON data processing

### 8. `exceptions.py`
- Custom exception classes

### 9. `managers/social_media.py`
- `SocialMediaManager` class
- Social media platform integrations (Last.FM, ListenBrainz, Bluesky, Facebook)

### 10. `managers/database.py`
- `DatabaseManager` class
- Database operations
- Schema setup

### 11. `managers/artwork.py`
- `ArtworkManager` class
- Artwork file processing
- Hashing functions

### 12. `managers/playlist.py`
- `PlaylistManager` class
- Playlist file updates

### 13. `managers/history.py`
- `HistoryManager` class
- Track history management
- History file operations

### 14. `managers/show.py`
- `ShowHandler` class
- Show information management
- Show transitions

## Implementation Strategy
1. Create package directory structure
2. Extract models and data classes first
3. Move each manager class to its own file
4. Extract server logic to server.py
5. Create core module with main application logic
6. Update imports across all files
7. Create main entry point script
8. Test functionality to ensure equivalence