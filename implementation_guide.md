# Myrcat Implementation Guide

## Refactoring Plan Implementation

The monolithic `myrcat.py` script has been refactored into a modular package structure. Here's how to implement the changes:

### Steps to Implement

1. **Review the refactored code**
   - Examine the new package structure in the `myrcat/` directory
   - Verify that all functionality from the original script is preserved

2. **Test the new implementation**
   - Keep the original `myrcat.py` as a backup (rename it to `myrcat.py.original`)
   - Move the new entry point to `myrcat.py`:
     ```bash
     mv myrcat.py myrcat.py.original
     mv myrcat.py.new myrcat.py
     chmod +x myrcat.py
     ```

3. **Install the package in development mode**
   ```bash
   python -m pip install -e .
   ```

4. **Test the application**
   - Run the application directly using the script:
     ```bash
     ./myrcat.py -c config.ini
     ```
   - Or run it using the installed entry point:
     ```bash
     myrcat -c config.ini
     ```

5. **Verify all functionality**
   - Ensure all components are working together as expected
   - Test the socket server and track processing
   - Verify social media updates are working
   - Check database operations
   - Validate artwork processing

## Benefits of the New Structure

1. **Modularity**
   - Each component is in its own module, making it easier to understand and maintain
   - Separation of concerns with clear responsibilities for each class

2. **Testability**
   - Components can be tested in isolation
   - Dependencies are clearly defined
   - Mock objects can be used for testing

3. **Extensibility**
   - New functionality can be added with minimal changes to existing code
   - New social media platforms can be easily integrated
   - Additional features can be implemented without modifying core functionality

4. **Documentation**
   - Better organization makes it easier to document the codebase
   - Purpose and functionality of each component is clear

5. **Code Reuse**
   - Components can be reused in other projects
   - Utility functions are isolated for better reusability

## Future Enhancements

The refactored code provides a foundation for future enhancements:

1. Implement proper unit tests for each component
2. Add configuration validation and schema checking
3. Implement a web interface for monitoring and configuration
4. Add support for additional social media platforms
5. Improve error handling and recovery mechanisms
6. Add metrics and performance monitoring

## Social Media Analytics Reports

Myrcat now supports generating detailed text-based analytics reports that provide insights into social media engagement metrics. These reports show performance statistics for each platform and track engagement over time.

### Configuration

To enable analytics reports, add these settings to the `[social_analytics]` section of your config.ini file:

```ini
# Generate text-based reports after analytics tasks
generate_reports = true
# Directory to save report files
reports_directory = reports
```

### Report Features

- Timestamped reports generated after each analytics check (follows check_frequency setting)
- Each report includes a header with current time and time since the last report
- Platform-specific metrics including post counts, likes, shares, and comments
- Change indicators (↑/↓/-) showing changes in metrics since the previous report
- Formatted table of top tracks ranked by engagement metrics
- Reports are saved in the configured directory with timestamps in filenames

### Example Report Format

```
SOCIAL MEDIA ANALYTICS REPORT
===============================
Report Run: Wednesday, March 26 at 20:51 [Last run: 4 hours ago]

Report covering the last 30 days

PLATFORM STATISTICS
-------------------

Bluesky
  Posts:              42 ↑3
  Total Likes:       156 ↑18
  Total Shares:       87 ↑5
  Total Comments:     34 -
  Avg. Likes:        3.71
  Avg. Shares:       2.07
  Avg. Comments:     0.81


TOP TRACKS BY ENGAGEMENT
----------------------
Track                                      Artist                          Posts  Likes    Shares   Comments 
------------------------------------------ ------------------------------ ----- ----- ----- ----- ----- -----
Midnight City                              M83                                2    23   ↑5    12   ↑2     5   ↑1
Broken Social Scene                        Anthems for a Seventeen Year       1    18   ↑3     7   -      3   -
Genesis                                    Grimes                             2    15   ↓2     9   ↑2     2   -
```

## New Feature: Artist Repost Prevention

Myrcat now includes a feature that prevents the same artist from being posted to social media platforms multiple times within a configurable time window. This helps prevent flooding your social media feeds with content from the same artist.

### Configuration

In the `[social_analytics]` section of your config.ini file, you can set:

```ini
# Time window (in minutes) to prevent reposting the same artist
artist_repost_window = 60
```

This setting defines how long (in minutes) to wait before allowing another post from the same artist. The default is 60 minutes (1 hour).

### Behavior

- This check is applied ONLY to Facebook and Bluesky posts
- LastFM and ListenBrainz updates are NOT affected by this setting
- The check is performed at the beginning of the posting process for each platform
- The artist's name is used for matching (exact match)
- If a matching artist is found in recent posts (within the configured time window), the post is skipped
- A log message is generated to indicate when a post is skipped due to this feature