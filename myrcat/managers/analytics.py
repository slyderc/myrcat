"""Social media analytics manager for Myrcat."""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from myrcat.models import TrackInfo
from myrcat.managers.database import DatabaseManager


class SocialMediaAnalytics:
    """Tracks and analyzes social media engagement.
    
    TODO: Potential improvements:
    - Add more advanced analytics (engagement trends, peak times)
    - Implement anomaly detection for unusual engagement spikes
    - Support for exporting data to external analytics platforms
    - Add visualizations (charts, graphs) for reports
    - Implement A/B testing for post effectiveness
    - Support for scheduled/periodic report generation
    """
    
    def __init__(self, config, db_manager: DatabaseManager):
        """Initialize with config and database manager.
        
        Args:
            config: ConfigParser object with configuration
            db_manager: DatabaseManager instance for data persistence
        """
        self.config = config
        self.db = db_manager
        
        # Track previous analytics values for change indicators
        self.previous_analytics = {}
        self.last_report_time = None
        
        # Load settings from config
        self.load_config()
        
    def load_config(self):
        """Load settings from configuration.
        
        This method can be called to reload configuration settings when the
        config file changes without requiring re-initialization of the class.
        """
        # Get analytics settings
        self.enabled = self.config.getboolean("social_analytics", "enable_analytics", fallback=True)
        self.check_frequency = self.config.getint("social_analytics", "check_frequency", fallback=6)
        self.retention_period = self.config.getint("social_analytics", "retention_period", fallback=90)
        
        # Report settings
        self.generate_reports = self.config.getboolean("social_analytics", "generate_reports", fallback=False)
        self.reports_directory = Path(self.config.get("social_analytics", "reports_directory", fallback="reports"))
        
        if self.enabled:
            self.ensure_tables()
            logging.info(f"✅ Social media analytics enabled (check frequency: {self.check_frequency}h)")
            
            # Create reports directory if enabled
            if self.generate_reports:
                os.makedirs(self.reports_directory, exist_ok=True)
                logging.info(f"📊 Analytics reports enabled - directory: {self.reports_directory}")
        else:
            logging.info(f"⛔️ Social media analytics disabled")
        
    def ensure_tables(self) -> None:
        """Verify analytics tables exist in the database."""
        try:
            with self.db._get_connection() as conn:
                # Verify analytics tables exist
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('social_media_posts', 'social_media_engagement')"
                )
                tables = [row[0] for row in cursor.fetchall()]
                
                if len(tables) < 2:
                    missing = []
                    if 'social_media_posts' not in tables:
                        missing.append('social_media_posts')
                    if 'social_media_engagement' not in tables:
                        missing.append('social_media_engagement')
                        
                    logging.error(f"💥 Missing required tables: {', '.join(missing)}")
                    logging.error("💥 Please initialize the database with schema.sql")
                    
                # Verify indexes exist
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_posts_platform', 'idx_engagement_post_id')"
                )
                indexes = [row[0] for row in cursor.fetchall()]
                
                if len(indexes) < 2:
                    logging.warning("⚠️ Analytics indexes may be missing. Performance could be affected.")
                    
        except Exception as e:
            logging.error(f"💥 Error verifying analytics tables: {e}")
    
    async def record_post(self, platform: str, post_id: str, track: TrackInfo, content: str, 
                      post_url: str = None, has_image: bool = False) -> Optional[int]:
        """Record a social media post for tracking.
        
        Args:
            platform: Social media platform name
            post_id: Platform-specific post ID
            track: TrackInfo object for the posted track
            content: Content of the post
            post_url: URL to the post (optional)
            has_image: Whether the post has an image (optional)
            
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
                content_preview = content[:50] + "..." if len(content) > 50 else content
                logging.debug(f"📊 Recording {platform} post: {post_id} with content: {content_preview}")
                
                # Convert boolean has_image to integer
                has_image_int = 1 if has_image else 0
                
                # Insert with the new schema that includes post_url and has_image
                cursor = conn.execute(
                    """
                    INSERT INTO social_media_posts (
                        platform, post_id, track_id, posted_at, message, post_url, has_image
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                    """,
                    (
                        platform,
                        post_id,
                        track_id,
                        datetime.now().isoformat(),
                        content,
                        post_url,
                        has_image_int
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
                    "SELECT id FROM social_media_posts WHERE platform = ? AND post_id = ? AND deleted = 0",
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
            
    async def mark_post_as_deleted(self, platform: str, post_id: str) -> bool:
        """Mark a post as deleted in the database.
        
        Args:
            platform: Social media platform name
            post_id: Platform-specific post ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
            
        try:
            with self.db._get_connection() as conn:
                # Update the post with deleted flag
                cursor = conn.execute(
                    """
                    UPDATE social_media_posts 
                    SET deleted = 1
                    WHERE platform = ? AND post_id = ?
                    """,
                    (platform, post_id)
                )
                
                # Check if any rows were affected
                if cursor.rowcount > 0:
                    logging.info(f"🗑️ Marked {platform} post {post_id} as deleted")
                    return True
                else:
                    logging.warning(f"⚠️ No post found to mark as deleted: {platform} {post_id}")
                    return False
        except Exception as e:
            logging.error(f"💥 Error marking post as deleted: {e}")
            return False
            
    async def track_error(self, platform: str, track: TrackInfo, error_message: str) -> bool:
        """Track an error that occurred during social media posting.
        
        Args:
            platform: Social media platform name
            track: TrackInfo object for the track that was being posted
            error_message: Error message or description
            
        Returns:
            True if successfully tracked, False otherwise
        """
        if not self.enabled:
            return False
            
        try:
            # Log the error with proper emoji categorization
            logging.error(f"💥 {platform} error with track [{track.artist} - {track.title}]: {error_message}")
            
            # For now, we just log the error but don't store it in the database
            # In the future, we could add a social_media_errors table
            
            return True
        except Exception as e:
            logging.error(f"💥 Error tracking error (meta-error): {e}")
            return False
            
    async def get_top_tracks(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top tracks by social media engagement with previous period comparison.
        
        Args:
            days: Number of days to look back
            limit: Maximum number of tracks to return
            
        Returns:
            List of track dictionaries with engagement data and change metrics
        """
        if not self.enabled:
            return []
            
        try:
            now = datetime.now()
            cutoff_date = (now - timedelta(days=days)).isoformat()
            
            # For comparison, get previous period
            previous_cutoff_end = cutoff_date  # Current period starts where previous ends
            previous_cutoff_start = (now - timedelta(days=days*2)).isoformat()
            
            with self.db._get_connection() as conn:
                # Get current period top tracks
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
                    AND smp.deleted = 0
                    GROUP BY p.artist, p.title, p.album
                    ORDER BY (total_likes + total_shares * 2 + total_comments * 3) DESC
                    LIMIT ?
                    """,
                    (cutoff_date, limit)
                )
                current_tracks = [dict(row) for row in cursor.fetchall()]
                
                # Create a lookup dictionary for previous period data
                previous_data = {}
                cursor = conn.execute(
                    """
                    SELECT 
                        p.artist, p.title,
                        SUM(sme.likes) as total_likes,
                        SUM(sme.shares) as total_shares,
                        SUM(sme.comments) as total_comments
                    FROM playouts p
                    JOIN social_media_posts smp ON p.id = smp.track_id
                    JOIN social_media_engagement sme ON smp.id = sme.post_id
                    WHERE smp.posted_at > ? 
                    AND smp.posted_at <= ?
                    AND smp.deleted = 0
                    GROUP BY p.artist, p.title
                    """,
                    (previous_cutoff_start, previous_cutoff_end)
                )
                for row in cursor.fetchall():
                    key = f"{row['artist']}||{row['title']}"
                    previous_data[key] = {
                        'likes': row['total_likes'] if row['total_likes'] else 0,
                        'shares': row['total_shares'] if row['total_shares'] else 0,
                        'comments': row['total_comments'] if row['total_comments'] else 0
                    }
                
                # Add previous period data and calculate changes
                for track in current_tracks:
                    key = f"{track['artist']}||{track['title']}"
                    
                    # Set defaults 
                    track['prev_likes'] = 0
                    track['prev_shares'] = 0
                    track['prev_comments'] = 0
                    track['likes_change'] = 0
                    track['shares_change'] = 0 
                    track['comments_change'] = 0
                    track['likes_change_pct'] = 0
                    track['engagement_trend'] = 'new'  # Default to 'new' if no previous data
                    
                    # If we have previous data for this track
                    if key in previous_data:
                        prev = previous_data[key]
                        track['prev_likes'] = prev['likes']
                        track['prev_shares'] = prev['shares']
                        track['prev_comments'] = prev['comments']
                        
                        # Calculate changes
                        track['likes_change'] = track['total_likes'] - prev['likes']
                        track['shares_change'] = track['total_shares'] - prev['shares']
                        track['comments_change'] = track['total_comments'] - prev['comments']
                        
                        # Calculate percentage changes
                        if prev['likes'] > 0:
                            track['likes_change_pct'] = round((track['likes_change'] / prev['likes']) * 100, 1)
                        
                        # Determine trend
                        current_engagement = track['total_likes'] + track['total_shares']*2 + track['total_comments']*3
                        previous_engagement = prev['likes'] + prev['shares']*2 + prev['comments']*3
                        
                        if current_engagement > previous_engagement:
                            track['engagement_trend'] = 'up'
                        elif current_engagement < previous_engagement:
                            track['engagement_trend'] = 'down'
                        else:
                            track['engagement_trend'] = 'flat'
                
                return current_tracks
                
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
            Dictionary of platform statistics including historical comparison
        """
        if not self.enabled:
            return {}
            
        try:
            now = datetime.now()
            cutoff_date = (now - timedelta(days=days)).isoformat()
            
            # For comparison, get previous period stats
            previous_cutoff_end = cutoff_date  # Current period starts where previous ends
            previous_cutoff_start = (now - timedelta(days=days*2)).isoformat()
            
            with self.db._get_connection() as conn:
                # Get total posts for current period
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) as post_count
                    FROM social_media_posts
                    WHERE platform = ? AND posted_at > ? AND deleted = 0
                    """,
                    (platform, cutoff_date)
                )
                result = cursor.fetchone()
                post_count = result[0] if result else 0
                
                # Get total posts for previous period
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) as post_count
                    FROM social_media_posts
                    WHERE platform = ? 
                    AND posted_at > ? 
                    AND posted_at <= ? 
                    AND deleted = 0
                    """,
                    (platform, previous_cutoff_start, previous_cutoff_end)
                )
                result = cursor.fetchone()
                previous_post_count = result[0] if result else 0
                
                # Get engagement metrics for current period
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
                    WHERE smp.platform = ? AND smp.posted_at > ? AND smp.deleted = 0
                    """,
                    (platform, cutoff_date)
                )
                current = cursor.fetchone()
                
                # Get engagement metrics for previous period
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
                    WHERE smp.platform = ? 
                    AND smp.posted_at > ? 
                    AND smp.posted_at <= ? 
                    AND smp.deleted = 0
                    """,
                    (platform, previous_cutoff_start, previous_cutoff_end)
                )
                previous = cursor.fetchone()
                
                # Get engagement growth over time (last 5 data points)
                cursor = conn.execute(
                    """
                    SELECT 
                        DATE(sme.checked_at) as check_date,
                        SUM(sme.likes) as total_likes
                    FROM social_media_posts smp
                    JOIN social_media_engagement sme ON smp.id = sme.post_id
                    WHERE smp.platform = ? AND smp.posted_at > ? AND smp.deleted = 0
                    GROUP BY DATE(sme.checked_at)
                    ORDER BY check_date DESC
                    LIMIT 5
                    """,
                    (platform, previous_cutoff_start)
                )
                trend_data = cursor.fetchall()
                trend_dates = [row[0] for row in trend_data]
                trend_likes = [row[1] if row[1] else 0 for row in trend_data]
                
                # Create comparison metrics
                current_likes = current[0] if current and current[0] else 0
                previous_likes = previous[0] if previous and previous[0] else 0
                likes_change = current_likes - previous_likes
                likes_change_pct = (likes_change / previous_likes * 100) if previous_likes > 0 else 0
                
                current_shares = current[1] if current and current[1] else 0
                previous_shares = previous[1] if previous and previous[1] else 0
                shares_change = current_shares - previous_shares
                shares_change_pct = (shares_change / previous_shares * 100) if previous_shares > 0 else 0
                
                current_comments = current[2] if current and current[2] else 0
                previous_comments = previous[2] if previous and previous[2] else 0
                comments_change = current_comments - previous_comments
                comments_change_pct = (comments_change / previous_comments * 100) if previous_comments > 0 else 0
                
                post_change = post_count - previous_post_count
                post_change_pct = (post_change / previous_post_count * 100) if previous_post_count > 0 else 0
                
                return {
                    "platform": platform,
                    "days": days,
                    "post_count": post_count,
                    "previous_post_count": previous_post_count,
                    "post_change": post_change,
                    "post_change_pct": round(post_change_pct, 1),
                    "total_likes": current_likes,
                    "previous_likes": previous_likes,
                    "likes_change": likes_change,
                    "likes_change_pct": round(likes_change_pct, 1),
                    "total_shares": current_shares,
                    "previous_shares": previous_shares,
                    "shares_change": shares_change, 
                    "shares_change_pct": round(shares_change_pct, 1),
                    "total_comments": current_comments,
                    "previous_comments": previous_comments,
                    "comments_change": comments_change,
                    "comments_change_pct": round(comments_change_pct, 1),
                    "avg_likes": round(current[3], 2) if current and current[3] else 0,
                    "avg_shares": round(current[4], 2) if current and current[4] else 0,
                    "avg_comments": round(current[5], 2) if current and current[5] else 0,
                    "trend_dates": trend_dates,
                    "trend_likes": trend_likes
                }
        except Exception as e:
            logging.error(f"💥 Error getting platform stats: {e}")
            return {
                "platform": platform,
                "days": days,
                "error": str(e)
            }
            
    def _format_change_indicator(self, change: int, change_pct: float = None) -> str:
        """Format a change indicator (↑/↓/-) with value and optional percentage.
        
        Args:
            change: The change value
            change_pct: Optional percentage change
            
        Returns:
            Formatted change indicator string
        """
        if change == 0:
            return "-"
            
        if change > 0:
            if change_pct is not None:
                return f"↑{change} (+{change_pct:.1f}%)"
            return f"↑{change}"
        else:
            if change_pct is not None:
                return f"↓{abs(change)} ({change_pct:.1f}%)"
            return f"↓{abs(change)}"
            
    async def generate_text_report(self, analytics_data: Dict[str, Any]) -> None:
        """Generate a text-based analytics report.
        
        Args:
            analytics_data: Analytics data from get_social_analytics
        """
        if not self.enabled or not self.generate_reports:
            return
            
        try:
            now = datetime.now()
            timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
            report_file = self.reports_directory / f"social_analytics_{timestamp}.txt"
            
            # Calculate time since last report
            time_ago = ""
            if self.last_report_time:
                time_diff = now - self.last_report_time
                hours = int(time_diff.total_seconds() / 3600)
                if hours < 24:
                    time_ago = f"[Last run: {hours} hours ago]"
                else:
                    days = int(hours / 24)
                    time_ago = f"[Last run: {days} days ago]"
            
            with open(report_file, "w") as f:
                # Write report header
                day_name = now.strftime("%A")
                date_time = now.strftime("%B %d at %H:%M")
                f.write(f"SOCIAL MEDIA ANALYTICS REPORT\n")
                f.write(f"===============================\n")
                f.write(f"Report Run: {day_name}, {date_time} {time_ago}\n\n")
                
                if not analytics_data.get("enabled", False):
                    f.write("Analytics are currently disabled.\n")
                    return
                    
                report_days = analytics_data.get('days', 30)
                f.write(f"Report covering the last {report_days} days compared to previous {report_days} days\n\n")
                
                # Platform statistics
                f.write("PLATFORM STATISTICS\n")
                f.write("-------------------\n")
                platforms = analytics_data.get("platforms", {})
                
                for platform_name, stats in platforms.items():
                    f.write(f"\n{platform_name}\n")
                    
                    # Posts
                    post_count = stats.get("post_count", 0)
                    post_change = stats.get("post_change", 0)
                    post_change_pct = stats.get("post_change_pct", 0.0)
                    post_indicator = self._format_change_indicator(post_change, post_change_pct)
                    f.write(f"  Posts:           {post_count:4d} {post_indicator}\n")
                    
                    # Likes
                    likes = stats.get("total_likes", 0)
                    likes_change = stats.get("likes_change", 0)
                    likes_change_pct = stats.get("likes_change_pct", 0.0)
                    likes_indicator = self._format_change_indicator(likes_change, likes_change_pct)
                    f.write(f"  Total Likes:     {likes:4d} {likes_indicator}\n")
                    
                    # Shares 
                    shares = stats.get("total_shares", 0)
                    shares_change = stats.get("shares_change", 0) 
                    shares_change_pct = stats.get("shares_change_pct", 0.0)
                    shares_indicator = self._format_change_indicator(shares_change, shares_change_pct)
                    f.write(f"  Total Shares:    {shares:4d} {shares_indicator}\n")
                    
                    # Comments
                    comments = stats.get("total_comments", 0)
                    comments_change = stats.get("comments_change", 0)
                    comments_change_pct = stats.get("comments_change_pct", 0.0)
                    comments_indicator = self._format_change_indicator(comments_change, comments_change_pct)
                    f.write(f"  Total Comments:  {comments:4d} {comments_indicator}\n")
                    
                    # Average engagement
                    avg_likes = stats.get("avg_likes", 0)
                    f.write(f"  Avg. Likes:      {avg_likes:.2f}\n")
                    
                    avg_shares = stats.get("avg_shares", 0)
                    f.write(f"  Avg. Shares:     {avg_shares:.2f}\n")
                    
                    avg_comments = stats.get("avg_comments", 0)
                    f.write(f"  Avg. Comments:   {avg_comments:.2f}\n")
                    
                    # Display trend data if available
                    trend_dates = stats.get("trend_dates", [])
                    trend_likes = stats.get("trend_likes", [])
                    
                    if trend_dates and trend_likes and len(trend_dates) == len(trend_likes):
                        f.write("\n  Likes Trend (past days):\n")
                        for i in range(min(len(trend_dates), 5)):
                            date_str = trend_dates[i]
                            # Convert date string to more readable format
                            try:
                                date_obj = datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d")
                            except:
                                date_obj = date_str
                            f.write(f"    {date_obj}: {trend_likes[i]}\n")
                
                # Top tracks
                f.write("\n\nTOP TRACKS BY ENGAGEMENT\n")
                f.write("----------------------\n")
                
                top_tracks = analytics_data.get("top_tracks", [])
                if not top_tracks:
                    f.write("No track data available for this period.\n")
                else:
                    # Column headers with indicators for trend analysis
                    f.write(f"{'Track':42s} {'Artist':30s} {'Posts':5s} {'Likes':5s} {'Change':18s} {'Trend':6s}\n")
                    f.write(f"{'-'*42} {'-'*30} {'-'*5} {'-'*5} {'-'*18} {'-'*6}\n")
                    
                    # Track data
                    for track in top_tracks:
                        title = track.get("title", "Unknown")[:40]
                        artist = track.get("artist", "Unknown")[:28]
                        post_count = track.get("post_count", 0)
                        likes = track.get("total_likes", 0)
                        
                        # Get trend indicators
                        likes_change = track.get("likes_change", 0)
                        likes_change_pct = track.get("likes_change_pct", 0)
                        
                        # Format the change indicator
                        change_indicator = self._format_change_indicator(likes_change, likes_change_pct)
                        
                        # Format the engagement trend indicator
                        trend = track.get("engagement_trend", "")
                        if trend == "up":
                            trend_indicator = "↑"
                        elif trend == "down":
                            trend_indicator = "↓"  
                        elif trend == "flat":
                            trend_indicator = "→"
                        elif trend == "new":
                            trend_indicator = "NEW"
                        else:
                            trend_indicator = ""
                            
                        f.write(f"{title:42s} {artist:30s} {post_count:5d} {likes:5d} {change_indicator:18s} {trend_indicator:6s}\n")
                
            # Update last report time
            self.last_report_time = now
            logging.info(f"📊 Generated analytics report: {report_file}")
            
        except Exception as e:
            logging.error(f"💥 Error generating analytics report: {e}")
            logging.error(f"💥 Error details: {str(e)}")
            if hasattr(e, '__traceback__'):
                import traceback
                logging.error(f"💥 Traceback: {traceback.format_tb(e.__traceback__)}")