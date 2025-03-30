# Myrcat Architecture Documentation

This document provides a comprehensive overview of the Myrcat system architecture, design patterns, data flow, and extension points.

## System Overview

Myrcat (Myriad Cataloger) is a specialized service that processes radio track playouts from the Myriad playout system. It provides track metadata publishing, artwork processing, social media integration, and analytics in a modular, extensible architecture.

## Architecture Diagram

```mermaid
graph TD
    subgraph "Core Components"
        A[Myrcat Core] --> |initializes| B[Config]
        A --> |runs| C[MyriadServer]
        A --> |registers callbacks| C
        A --> |manages| D[Background Tasks]
    end

    subgraph "Data Flow"
        C --> |receives data| E[JSON Validation]
        E --> |validates| F[Track Processing]
        F --> |processes| G[TrackInfo]
    end

    subgraph "Manager Components"
        A --> |initializes| H[DatabaseManager]
        A --> |initializes| I[ArtworkManager]
        A --> |initializes| J[PlaylistManager]
        A --> |initializes| K[HistoryManager]
        A --> |initializes| L[SocialMediaManager]
        A --> |initializes| M[ShowHandler]
    end

    subgraph "Social Media"
        L --> |initializes| N[ContentGenerator]
        L --> |initializes| O[SocialMediaAnalytics]
        N --> |uses| P[PromptManager]
    end

    G --> |updates| J
    G --> |adds to| K
    G --> |posts to| L
    G --> |logs to| H
    G --> |processes art| I
    G --> |checks| M

    subgraph "External Systems"
        Q[Myriad Playout] --> |sends data| C
        L --> |posts to| R[LastFM]
        L --> |posts to| S[ListenBrainz]
        L --> |posts to| T[Bluesky]
        L --> |posts to| U[Facebook]
        N --> |requests content| V[Claude AI]
    end

    subgraph "Output"
        J --> |writes| W[playlist.json]
        J --> |writes| X[playlist.txt]
        K --> |maintains| Y[history.json]
        I --> |processes| Z[Artwork Files]
        O --> |generates| AA[Analytics Reports]
    end

    class A,B,C,D,E,F,G primary
    class H,I,J,K,L,M,N,O,P secondary
    class Q,R,S,T,U,V external
    class W,X,Y,Z,AA output

    classDef primary fill:#f9f,stroke:#333,stroke-width:2px
    classDef secondary fill:#bbf,stroke:#333,stroke-width:1px
    classDef external fill:#fbb,stroke:#333,stroke-width:1px
    classDef output fill:#bfb,stroke:#333,stroke-width:1px
```

## Directory Structure and Key Components

```
myrcat/
├── __init__.py           # Package definition with version info
├── main.py               # Entry point with argument parsing
├── core.py               # Central application class
├── server.py             # Socket server implementation
├── config.py             # Configuration management
├── models.py             # Data model definitions
├── utils.py              # Utility functions
├── exceptions.py         # Custom exception classes
└── managers/             # Specialized component managers
    ├── artwork.py        # Artwork processing
    ├── database.py       # SQLite database operations
    ├── history.py        # Track history management
    ├── playlist.py       # Playlist file generation
    ├── social_media.py   # Social platform integration
    ├── content.py        # AI content generation
    ├── analytics.py      # Social media analytics
    ├── prompt.py         # AI prompt management
    └── show.py           # Radio show management
```

## Core Architecture

Myrcat follows a component-based architecture with clean dependency management and asynchronous execution:

1. **Entry Point**: `myrcat.py` invokes the `main()` function from `myrcat/main.py`
2. **Application Core**: The `Myrcat` class in `core.py` serves as the central coordinator
3. **Component Managers**: Specialized classes handle specific aspects of functionality
4. **Data Flow**: Socket server → JSON validation → Track processing → Multi-component handling

### Initialization Flow

```python
def main():
    args = parse_arguments()
    app = Myrcat(args.config)  # Load config and initialize components
    asyncio.run(app.run())     # Start async event loop
```

The main `Myrcat` class initializes all components with appropriate dependencies:

```python
def _initialize_components(self):
    # Load configuration settings
    
    # Initialize components
    self.db = DatabaseManager(self.config.get("general", "database_path"))
    self.playlist = PlaylistManager(self.playlist_json, self.playlist_txt, self.artwork_publish)
    self.history = HistoryManager(self.history_json, self.history_max_tracks)
    self.artwork = ArtworkManager(self.artwork_incoming, self.artwork_publish, 
                                  self.artwork_cache_dir, self.default_artwork_path)
    self.social = SocialMediaManager(self.config_parser, self.artwork, self.db)
    self.show_handler = ShowHandler(self.config_parser)
    
    # Create server with callbacks
    self.server = MyriadServer(
        host=self.config.get("server", "host"),
        port=self.config.getint("server", "port"),
        validator=self.validate_track_json,
        processor=self.process_new_track,
    )
```

## Design Patterns

The codebase implements several key design patterns:

### 1. Dependency Injection

Components receive dependencies through constructor parameters rather than creating them internally:

```python
class SocialMediaManager:
    def __init__(self, config, artwork_manager, db_manager):
        self.config = config
        self.artwork_manager = artwork_manager
        self.db_manager = db_manager
```

This approach improves testability and decouples component implementations.

### 2. Asynchronous Programming

The system uses Python's `asyncio` for non-blocking I/O operations:

```python
async def process_new_track(self, track_json: Dict[str, Any]):
    # Process track data asynchronously
    
    # Publish with configurable delay
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    
    # Parallel operations
    await self.playlist.update_track(track, artwork_hash)
    await self.history.add_track(track, artwork_hash)
    await self.show_handler.check_show_transition(track)
    
    # Social media posting (unless skipped)
    if not self.should_skip_track(track.title, track.artist):
        await self.social.update_social_media(track)
```

### 3. Observer Pattern

Configuration hot-reloading and event-based handling:

```python
async def check_config_task(self):
    while True:
        await asyncio.sleep(check_seconds)
        if self.config.reload_if_changed():
            self._apply_config_changes()
```

### 4. Strategy Pattern

Content generation with dynamically selected strategies:

```python
def generate_content(self, track, platform):
    if self._should_use_ai(platform):
        return self._generate_ai_content(track, platform)
    else:
        return self._generate_template_content(track, platform)
```

### 5. Factory Methods

AI prompts are selected based on context:

```python
def select_prompt(self, track, current_hour):
    # Try program-specific prompt first
    if track.program and self._prompt_exists_for_program(track.program):
        return self._get_program_prompt(track.program)
    
    # Otherwise, use time-of-day prompt
    if self._prompt_exists_for_hour(current_hour):
        return self._get_time_prompt(current_hour)
    
    # Fall back to default prompt
    return self._get_default_prompt()
```

## Data Models

Myrcat uses Python's `dataclasses` for clean, type-annotated data modeling:

```python
@dataclass
class TrackInfo:
    """Track information storage."""
    artist: str
    title: str
    album: Optional[str]
    year: Optional[str]
    publisher: Optional[str]
    isrc: Optional[str]
    image: Optional[str]
    starttime: str
    duration: int
    type: str
    is_song: bool
    media_id: str
    program: Optional[str]
    presenter: Optional[str]
    timestamp: datetime = datetime.now()
```

## Data Flow

The data flows through the system as follows:

1. **Socket Server**: Receives JSON data from Myriad playout system
2. **Validation**: Validates required fields and data types
3. **Track Processing**:
   - Creates `TrackInfo` object
   - Processes artwork if present
   - Updates playlist files (JSON/TXT)
   - Adds to track history
   - Checks for show transitions
   - Posts to social media platforms
   - Logs to SQLite database

### Socket Server

```python
class MyriadServer:
    async def handle_connection(self, reader, writer):
        data = await reader.read()
        track_data = decode_json_data(data)
        
        # Validate using callback
        is_valid, message = self.validator(track_data)
        if not is_valid:
            return
            
        # Process using callback
        await self.processor(track_data)
```

### Track Processing

```python
async def process_new_track(self, track_json):
    # Create TrackInfo object
    track = TrackInfo(
        artist=track_json.get("artist", ""),
        title=clean_title(track_json.get("title", "")),
        # ... other fields
    )
    
    # Process artwork
    if track.image:
        new_filename = await self.artwork.process_artwork(track.image)
        if new_filename:
            track.image = new_filename
            artwork_hash = await self.artwork.create_hashed_artwork(
                new_filename, track.artist, track.title
            )
    
    # Update playlist, history, etc.
    await self.playlist.update_track(track, artwork_hash)
    await self.history.add_track(track, artwork_hash)
    await self.show_handler.check_show_transition(track)
    
    # Post to social media
    if not self.should_skip_track(track.title, track.artist):
        await self.social.update_social_media(track)
    
    # Log to database
    await self.db.log_db_playout(track)
```

## Configuration System

The configuration system uses INI files with hot-reloading capabilities:

```python
class Config:
    def __init__(self, config_path):
        self.config_parser = configparser.ConfigParser()
        self.config_path = Path(config_path)
        self.last_modified_time = self.config_path.stat().st_mtime
        self._load_config()
    
    def reload_if_changed(self) -> bool:
        """Check if config file has changed and reload if necessary."""
        current_time = self.config_path.stat().st_mtime
        if current_time > self.last_modified_time:
            self._load_config()
            self.last_modified_time = current_time
            return True
        return False
```

Configuration sections include:
- `general`: Basic settings like logging, database path, timezone
- `server`: Socket server host and port
- `artwork`: Paths for artwork processing
- `web`: Output file locations
- `lastfm`, `listenbrainz`, `facebook`, `bluesky`: Social media configuration
- `ai_content`: Settings for AI-enhanced content generation
- `publish_exceptions`: Rules for skipping certain tracks
- `social_analytics`: Engagement tracking and reporting settings

## Background Tasks

The system runs two main background tasks:

1. **Configuration Monitoring**: Checks for config file changes every 60 seconds
2. **Social Media Analytics**: Periodically checks engagement metrics based on the configured frequency

```python
async def run(self):
    # Start analytics task if enabled
    if analytics_enabled:
        engagement_task = asyncio.create_task(self.check_engagement_task())
    
    # Start config monitoring task
    config_check_task = asyncio.create_task(self.check_config_task())
    
    # Start server
    await self.server.start()
```

## Extension Points

The codebase has several well-defined extension points for adding new features:

### 1. Social Media Platforms

New platforms can be added by extending the `SocialMediaManager`:

```python
# In social_media.py
def setup_new_platform(self):
    # Initialize client for new platform
    self.new_platform = NewPlatformClient(self.config["new_platform"])

async def update_new_platform(self, track: TrackInfo):
    # Implementation for posting to new platform
    if not self._should_post_now("NewPlatform"):
        return
    
    # Prepare content
    content = await self.content_generator.generate_content(track, "NewPlatform")
    
    # Post to platform
    response = await self.new_platform.post(content)
    
    # Track the post
    await self.analytics.track_post("NewPlatform", track, post_id=response.id)
```

### 2. AI Content Generation

The prompt system can be extended with new prompt types:

```python
# In prompt.py
def _get_special_prompt(self, criteria):
    # Logic to select special prompts based on custom criteria
    prompt_path = self.prompts_dir / f"special_{criteria}.txt"
    if prompt_path.exists():
        return self._load_prompt_file(prompt_path)
    return None
```

### 3. Database Schemas

The database schema can be extended for new data collection:

```python
# In database.py
async def create_new_table(self):
    query = """
    CREATE TABLE IF NOT EXISTS new_feature (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        feature_data TEXT NOT NULL
    )
    """
    conn = sqlite3.connect(self.db_path)
    conn.execute(query)
    conn.commit()
    conn.close()
```

## Limitations and Optimization Opportunities

### Current Limitations

1. **Socket Server**: Single-threaded design limits concurrent connection handling
2. **Configuration**: No schema validation for config values
3. **Error Recovery**: Limited retry logic for API failures
4. **Social API Rate Limiting**: Basic time-based limiting could be enhanced

### Optimization Opportunities

1. **Connection Pooling**

```python
# Current approach
async def log_db_playout(self, track: TrackInfo):
    conn = sqlite3.connect(self.db_path)
    # Operations...
    conn.close()

# Improved approach using connection pooling
def __init__(self, db_path):
    self.pool = await aiosqlite.create_pool(db_path, minsize=5, maxsize=10)

async def log_db_playout(self, track: TrackInfo):
    async with self.pool.acquire() as conn:
        # Operations using connection from pool
```

2. **Parallel Processing**

```python
# Current sequential approach
await self.playlist.update_track(track)
await self.history.add_track(track)
await self.show_handler.check_show_transition(track)

# Parallel execution with gather
await asyncio.gather(
    self.playlist.update_track(track),
    self.history.add_track(track),
    self.show_handler.check_show_transition(track)
)
```

3. **Caching Enhancement**

Implement more sophisticated caching for artwork and API responses using TTL-based caching:

```python
def get_cached_item(self, key, max_age_seconds=3600):
    if key in self.cache:
        item, timestamp = self.cache[key]
        age = time.time() - timestamp
        if age < max_age_seconds:
            return item
    return None
```

4. **Structured Logging**

Enhance logging with structured data for better analysis:

```python
logging.info("Track processed", extra={
    "track_id": track.media_id,
    "artist": track.artist,
    "title": track.title,
    "processing_time_ms": (time.time() - start_time) * 1000
})
```

## Development Roadmap

Based on code analysis and TODOs, these improvements would benefit the system:

1. **Enhanced Testing**
   - Comprehensive unit tests for all components
   - Integration tests for the full pipeline
   - Mock services for testing social media integrations

2. **Security Enhancements**
   - TLS/SSL support for socket server
   - Authentication for incoming connections
   - Secure storage for API credentials

3. **Monitoring and Metrics**
   - Performance tracking for key operations
   - Health monitoring dashboard
   - Alerting for critical failures

4. **Deployment Improvements**
   - Containerization with Docker
   - CI/CD pipeline setup
   - Configuration management for different environments

5. **Feature Extensions**
   - Support for additional social media platforms
   - Enhanced analytics and reporting
   - Web-based administration interface

## Sequence Diagram

The following sequence diagram illustrates the track processing flow:

```mermaid
sequenceDiagram
    participant Myriad as Myriad Playout
    participant Server as MyriadServer
    participant Core as Myrcat Core
    participant Validator as JSON Validator
    participant Artwork as ArtworkManager
    participant Playlist as PlaylistManager
    participant History as HistoryManager
    participant Social as SocialMediaManager
    participant AI as ContentGenerator
    participant DB as DatabaseManager
    
    Myriad->>Server: Send Track JSON
    Server->>Validator: Validate JSON
    Validator-->>Server: Validation Result
    
    alt is valid track
        Server->>Core: process_new_track()
        
        opt delayed publishing enabled
            Core->>Core: wait for delay_seconds
        end
        
        Core->>Artwork: process_artwork()
        Artwork-->>Core: processed_artwork_path
        
        par Update various components
            Core->>Playlist: update_track()
            Core->>History: add_track()
            Core->>Social: update_social_media()
            Core->>DB: log_db_playout()
        end
        
        opt social media enabled
            Social->>AI: generate_content()
            AI-->>Social: post_content
            
            par Post to platforms
                Social->>Social: update_lastfm()
                Social->>Social: update_listenbrainz()
                Social->>Social: update_bluesky()
                Social->>Social: update_facebook() 
            end
        end
    else invalid track
        Server->>Server: Log validation failure
    end
```

## Component State Diagram

This state diagram shows how the configuration system impacts component states:

```mermaid
stateDiagram-v2
    [*] --> Initializing: Start application
    Initializing --> Running: Initialize components
    Running --> ConfigChanged: Config file modified
    ConfigChanged --> ApplyingChanges: Reload config
    ApplyingChanges --> Running: Update components
    Running --> CleaningUp: Shutdown signal
    CleaningUp --> [*]: Exit application
    
    state Running {
        [*] --> Waiting
        Waiting --> ProcessingTrack: Receive track
        ProcessingTrack --> ArtworkProcessing
        ArtworkProcessing --> PublishingTrack
        PublishingTrack --> SocialPosting
        SocialPosting --> DBLogging
        DBLogging --> Waiting
    }
```

## Conclusion

Myrcat's architecture demonstrates a well-designed, component-based system with clear separation of concerns. Its modular design allows for easy extension and maintenance, while the asynchronous programming model provides efficient I/O handling suitable for a service that bridges multiple external systems.

The combination of dependency injection, strategy patterns, and observer patterns creates a flexible framework that can adapt to changing requirements while maintaining code quality and testability.

The visual diagrams above help illustrate:
1. The hierarchical component structure and dependencies
2. The sequential flow of track data through the system
3. The runtime state management and configuration handling

This architecture provides a solid foundation for future development, allowing for expansion of features while maintaining a maintainable and testable codebase.