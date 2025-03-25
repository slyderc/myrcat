"""Social media analytics manager for Myrcat."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from myrcat.models import TrackInfo
from myrcat.managers.database import DatabaseManager


class SocialMediaAnalytics:
    """Tracks and analyzes social media engagement."""
    
    def __init__(self, config, db_manager: DatabaseManager):
        """Initialize with config and database manager.
        
        Args:
            config: ConfigParser object with configuration
            db_manager: DatabaseManager instance for data persistence
        """
        self.config = config
        self.db = db_manager
        
        # Get analytics settings
        self.enabled = config.getboolean("social_analytics", "enable_analytics", fallback=True)
        self.check_frequency = config.getint("social_analytics", "check_frequency", fallback=6)
        self.retention_period = config.getint("social_analytics", "retention_period", fallback=90)
        
        if self.enabled:
            self.ensure_tables()
            logging.info(f"✅ Social media analytics enabled (check frequency: {self.check_frequency}h)")
        else:
            logging.info(f"⛔️ Social media analytics disabled")
        
    def ensure_tables(self) -> None:
        """Ensure analytics tables exist in the database."""
        try:
            with self.db._get_connection() as conn:
                # Create table for post tracking
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS social_media_posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        post_id TEXT NOT NULL,
                        track_id INTEGER,
                        posted_at DATETIME NOT NULL,
                        message TEXT,
                        FOREIGN KEY (track_id) REFERENCES playouts(id)
                    )
                """)
                
                # Create table for engagement metrics
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS social_media_engagement (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id INTEGER NOT NULL,
                        checked_at DATETIME NOT NULL,
                        likes INTEGER DEFAULT 0,
                        shares INTEGER DEFAULT 0,
                        comments INTEGER DEFAULT 0,
                        clicks INTEGER DEFAULT 0,
                        FOREIGN KEY (post_id) REFERENCES social_media_posts(id)
                    )
                """)
                
                # Create index for faster queries
                conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_platform ON social_media_posts (platform, post_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_post_id ON social_media_engagement (post_id)")
        except Exception as e:
            logging.error(f"💥 Error creating analytics tables: {e}")
    
    async def record_post(self, platform: str, post_id: str, track: TrackInfo, message: str) -> Optional[int]:
        """Record a social media post for tracking.
        
        Args:
            platform: Social media platform name
            post_id: Platform-specific post ID
            track: TrackInfo object for the posted track
            message: Content of the post
            
        Returns:
            Internal post ID if successful, None otherwise
        """
        if not self.enabled:
            logging.debug(f"📊 Analytics disabled - not recording post for {platform}")
            return None
            
        try:
            # Get the track ID from the database
            track_id = self._get_track_id(track)
            logging.debug(f"📊 Found track ID for {track.artist} - {track.title}: {track_id}")
            
            with self.db._get_connection() as conn:
                # Log the full message for debugging
                message_preview = message[:50] + "..." if len(message) > 50 else message
                logging.debug(f"📊 Recording {platform} post: {post_id} with message: {message_preview}")
                
                cursor = conn.execute(
                    """
                    INSERT INTO social_media_posts (
                        platform, post_id, track_id, posted_at, message
                    ) VALUES (?, ?, ?, ?, ?)
                    RETURNING id
                    """,
                    (
                        platform,
                        post_id,
                        track_id,
                        datetime.now().isoformat(),
                        message
                    )
                )
                result = cursor.fetchone()
                if result:
                    logging.debug(f"📊 Successfully recorded {platform} post: {post_id}, internal ID: {result[0]}")
                    return result[0]
                else:
                    logging.warning(f"⚠️ Failed to get ID after recording {platform} post: {post_id}")
                    return None
        except Exception as e:
            logging.error(f"💥 Error recording post: {e}")
            # Print more detailed error information
            if hasattr(e, '__dict__'):
                logging.error(f"💥 Error details: {vars(e)}")
            return None
            
    def _get_track_id(self, track: TrackInfo) -> Optional[int]:
        """Get database ID for a track.
        
        Args:
            track: TrackInfo object
            
        Returns:
            Track ID from database or None if not found
        """
        try:
            logging.debug(f"📊 Looking up track ID for: {track.artist} - {track.title}")
            with self.db._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT id FROM playouts
                    WHERE artist = ? AND title = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (track.artist, track.title)
                )
                result = cursor.fetchone()
                
                if result:
                    logging.debug(f"📊 Found track ID: {result[0]}")
                    return result[0]
                else:
                    logging.debug(f"📊 No track ID found in database for: {track.artist} - {track.title}")
                    return None
        except Exception as e:
            logging.error(f"💥 Error getting track ID: {e}")
            # Add more detailed error info
            if hasattr(e, '__dict__'):
                logging.error(f"💥 Error details: {vars(e)}")
            return None
            
    async def update_engagement(self, platform: str, post_id: str, metrics: Dict[str, int]) -> bool:
        """Update engagement metrics for a post.
        
        Args:
            platform: Social media platform name
            post_id: Platform-specific post ID
            metrics: Dictionary of engagement metrics (likes, shares, comments, clicks)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
            
        try:
            with self.db._get_connection() as conn:
                # Get internal post ID
                cursor = conn.execute(
                    "SELECT id FROM social_media_posts WHERE platform = ? AND post_id = ?",
                    (platform, post_id)
                )
                result = cursor.fetchone()
                if not result:
                    logging.warning(f"⚠️ Post not found for engagement update: {platform} {post_id}")
                    return False
                    
                internal_id = result[0]
                
                # Insert engagement record
                conn.execute(
                    """
                    INSERT INTO social_media_engagement (
                        post_id, checked_at, likes, shares, comments, clicks
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        internal_id,
                        datetime.now().isoformat(),
                        metrics.get("likes", 0),
                        metrics.get("shares", 0),
                        metrics.get("comments", 0),
                        metrics.get("clicks", 0)
                    )
                )
                return True
        except Exception as e:
            logging.error(f"💥 Error updating engagement: {e}")
            return False
            
    async def get_top_tracks(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top tracks by social media engagement.
        
        Args:
            days: Number of days to look back
            limit: Maximum number of tracks to return
            
        Returns:
            List of track dictionaries with engagement data
        """
        if not self.enabled:
            return []
            
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            with self.db._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT 
                        p.artist, p.title, p.album,
                        COUNT(DISTINCT smp.id) as post_count,
                        SUM(sme.likes) as total_likes,
                        SUM(sme.shares) as total_shares,
                        SUM(sme.comments) as total_comments
                    FROM playouts p
                    JOIN social_media_posts smp ON p.id = smp.track_id
                    JOIN social_media_engagement sme ON smp.id = sme.post_id
                    WHERE smp.posted_at > ?
                    GROUP BY p.artist, p.title, p.album
                    ORDER BY (total_likes + total_shares * 2 + total_comments * 3) DESC
                    LIMIT ?
                    """,
                    (cutoff_date, limit)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"💥 Error getting top tracks: {e}")
            return []
            
    async def cleanup_old_data(self) -> None:
        """Clean up old analytics data based on retention period."""
        if not self.enabled:
            return
            
        try:
            cutoff_date = (datetime.now() - timedelta(days=self.retention_period)).isoformat()
            
            with self.db._get_connection() as conn:
                # Find posts to delete
                cursor = conn.execute(
                    "SELECT id FROM social_media_posts WHERE posted_at < ?",
                    (cutoff_date,)
                )
                post_ids = [row[0] for row in cursor.fetchall()]
                
                if not post_ids:
                    return
                    
                # Delete engagement data for these posts
                for post_id in post_ids:
                    conn.execute(
                        "DELETE FROM social_media_engagement WHERE post_id = ?",
                        (post_id,)
                    )
                
                # Delete the posts themselves
                conn.execute(
                    "DELETE FROM social_media_posts WHERE id IN ({})".format(
                        ','.join('?' for _ in post_ids)
                    ),
                    post_ids
                )
                
                deleted_count = len(post_ids)
                if deleted_count > 0:
                    logging.info(f"🧹 Cleaned up {deleted_count} old social media analytics records")
        except Exception as e:
            logging.error(f"💥 Error cleaning up old analytics data: {e}")
            
    async def get_platform_stats(self, platform: str, days: int = 30) -> Dict[str, Any]:
        """Get engagement statistics for a specific platform.
        
        Args:
            platform: Social media platform name
            days: Number of days to look back
            
        Returns:
            Dictionary of platform statistics
        """
        if not self.enabled:
            return {}
            
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            with self.db._get_connection() as conn:
                # Get total posts
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) as post_count
                    FROM social_media_posts
                    WHERE platform = ? AND posted_at > ?
                    """,
                    (platform, cutoff_date)
                )
                result = cursor.fetchone()
                post_count = result[0] if result else 0
                
                # Get engagement metrics
                cursor = conn.execute(
                    """
                    SELECT 
                        SUM(sme.likes) as total_likes,
                        SUM(sme.shares) as total_shares,
                        SUM(sme.comments) as total_comments,
                        AVG(sme.likes) as avg_likes,
                        AVG(sme.shares) as avg_shares,
                        AVG(sme.comments) as avg_comments
                    FROM social_media_posts smp
                    JOIN social_media_engagement sme ON smp.id = sme.post_id
                    WHERE smp.platform = ? AND smp.posted_at > ?
                    """,
                    (platform, cutoff_date)
                )
                result = cursor.fetchone()
                
                return {
                    "platform": platform,
                    "days": days,
                    "post_count": post_count,
                    "total_likes": result[0] if result and result[0] else 0,
                    "total_shares": result[1] if result and result[1] else 0,
                    "total_comments": result[2] if result and result[2] else 0,
                    "avg_likes": round(result[3], 2) if result and result[3] else 0,
                    "avg_shares": round(result[4], 2) if result and result[4] else 0,
                    "avg_comments": round(result[5], 2) if result and result[5] else 0
                }
        except Exception as e:
            logging.error(f"💥 Error getting platform stats: {e}")
            return {
                "platform": platform,
                "days": days,
                "error": str(e)
            }