-- Myrcat Database Schema
-- Run with: cat schema.sql | sqlite3 myrcat.db

-- Database version table for schema compatibility checks
CREATE TABLE IF NOT EXISTS db_version (
    id INTEGER PRIMARY KEY CHECK (id = 1), -- Ensures only one row
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

-- Insert the current version (initial insert or replace existing)
INSERT OR REPLACE INTO db_version (id, version, updated_at)
VALUES (1, 4, datetime('now'));

-- Main playout tracks table
CREATE TABLE IF NOT EXISTS playouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    album TEXT,
    year INTEGER,
    publisher TEXT,
    isrc TEXT,
    starttime TEXT,
    duration INTEGER,
    media_id TEXT,
    program TEXT,
    presenter TEXT,
    timestamp DATETIME NOT NULL
);

-- Artist research table
CREATE TABLE IF NOT EXISTS artist_research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT NOT NULL,
    artist_hash TEXT NOT NULL UNIQUE,
    research_text TEXT NOT NULL,
    image_filename TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(artist_hash COLLATE NOCASE)
);

-- Image search cache table
CREATE TABLE IF NOT EXISTS image_search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_query TEXT NOT NULL UNIQUE,
    image_url TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    cached_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(search_query COLLATE NOCASE)
);

-- Facebook tokens table
CREATE TABLE IF NOT EXISTS facebook_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    access_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    metadata TEXT,
    token_type TEXT
);

-- Social media posts table
CREATE TABLE IF NOT EXISTS social_media_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    track_id INTEGER,
    posted_at DATETIME NOT NULL,
    message TEXT,
    post_url TEXT,
    has_image INTEGER DEFAULT 0,
    deleted INTEGER DEFAULT 0,
    FOREIGN KEY (track_id) REFERENCES playouts(id)
);

-- Social media engagement metrics table
CREATE TABLE IF NOT EXISTS social_media_engagement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    checked_at DATETIME NOT NULL,
    likes INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    FOREIGN KEY (post_id) REFERENCES social_media_posts(id)
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_posts_platform ON social_media_posts (platform, post_id);
CREATE INDEX IF NOT EXISTS idx_engagement_post_id ON social_media_engagement (post_id);
CREATE INDEX IF NOT EXISTS idx_image_search_query ON image_search_cache (search_query COLLATE NOCASE);
