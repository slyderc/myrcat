# Myrcat Database Schema Documentation

## Overview

Myrcat uses SQLite for persistent storage of track data, social media posts, and engagement metrics. The schema is centralized in `schema.sql` at the root of the project.

## Database Initialization

To initialize or update the database schema, use one of these methods:

1. Using the initialization script (recommended):
   ```bash
   ./utils/init_database.sh
   ```
   This script offers options for backup, force reinitialization, and custom database paths.

2. Directly with SQLite:
   ```bash
   cat schema.sql | sqlite3 myrcat.db
   ```

## Schema Version

The database tracks its schema version in the `db_version` table. The application checks this version at startup to ensure compatibility. If the schema version doesn't match what the code expects, an error is raised.

To update the schema version when making changes:
1. Modify the schema.sql file with your changes
2. Increment the version number in the INSERT statement at the top of schema.sql
3. Update the EXPECTED_VERSION constant in DatabaseManager.setup_database()

## Table Descriptions

### db_version

Stores the current database schema version.

| Column     | Type    | Description                         |
|------------|---------|-------------------------------------|
| id         | INTEGER | Primary key (always 1)              |
| version    | INTEGER | Schema version number               |
| updated_at | TEXT    | When the schema was last updated    |

### playouts

Stores track playback information for reporting and tracking.

| Column     | Type    | Description                          |
|------------|---------|--------------------------------------|
| id         | INTEGER | Primary key                          |
| artist     | TEXT    | Track artist                         |
| title      | TEXT    | Track title                          |
| album      | TEXT    | Album name (optional)                |
| year       | INTEGER | Release year (optional)              |
| publisher  | TEXT    | Publisher (optional)                 |
| isrc       | TEXT    | ISRC code (optional)                 |
| starttime  | TEXT    | When the track started playing       |
| duration   | INTEGER | Track duration in seconds            |
| media_id   | TEXT    | Media ID from source system          |
| program    | TEXT    | Show/program name (optional)         |
| presenter  | TEXT    | DJ/presenter name (optional)         |
| timestamp  | DATETIME| When the record was created          |

### facebook_tokens

Stores Facebook authentication tokens for the Facebook API integration.

| Column       | Type    | Description                        |
|--------------|-------  |----------------------------------- |
| id           | INTEGER | Primary key                        |
| access_token | TEXT    | Facebook API access token          |
| created_at   | TEXT    | When the token was created/stored  |
| expires_at   | TEXT    | When the token expires (if known)  |
| metadata     | TEXT    | JSON metadata (app_id, page_id)    |
| token_type   | TEXT    | Token type (optional)              |

### social_media_posts

Tracks posts made to social media platforms.

| Column     | Type    | Description                           |
|------------|---------|---------------------------------------|
| id         | INTEGER | Primary key                           |
| platform   | TEXT    | Social media platform name            |
| post_id    | TEXT    | Platform-specific post ID             |
| track_id   | INTEGER | Foreign key to playouts.id            |
| posted_at  | DATETIME| When the post was created             |
| message    | TEXT    | Post content                          |
| post_url   | TEXT    | URL to the post (optional)            |
| has_image  | INTEGER | Whether post includes image (0/1)     |
| deleted    | INTEGER | Whether post is deleted (0/1)         |

### social_media_engagement

Tracks engagement metrics for social media posts.

| Column     | Type    | Description                           |
|------------|---------|---------------------------------------|
| id         | INTEGER | Primary key                           |
| post_id    | INTEGER | Foreign key to social_media_posts.id  |
| checked_at | DATETIME| When metrics were last checked        |
| likes      | INTEGER | Number of likes/reactions             |
| shares     | INTEGER | Number of shares/reposts              |
| comments   | INTEGER | Number of comments/replies            |
| clicks     | INTEGER | Number of clicks (if available)       |

## Indexes

The following indexes improve query performance:

- `idx_posts_platform`: On social_media_posts (platform, post_id)
- `idx_engagement_post_id`: On social_media_engagement (post_id)

## Schema Management Practices

1. Never modify the database schema directly in code with CREATE TABLE statements
2. Always update the schema.sql file when making schema changes
3. Increment the version number when changing the schema
4. Update the EXPECTED_VERSION constant in code to match
5. Use the init_database.sh script to safely apply schema changes