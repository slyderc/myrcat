"""History manager for Myrcat."""

import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from myrcat.models import TrackInfo
from myrcat.exceptions import MyrcatException


class HistoryManager:
    """Manages track history and history.json file."""
    
    def __init__(self, history_json_path: Path, max_tracks: int = 30):
        """Initialize the history manager.
        
        Args:
            history_json_path: Path to the history.json file
            max_tracks: Maximum number of tracks to keep in history
        """
        self.history_json_path = history_json_path
        self.max_tracks = max_tracks
        self.track_history = deque(maxlen=max_tracks)
        
        # Ensure parent directory exists
        self.history_json_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing history if available
        self.load_history()
        
    def load_history(self):
        """Load track history from existing history.json file."""
        try:
            if self.history_json_path.exists():
                with open(self.history_json_path, 'r') as f:
                    history_data = json.load(f)
                    
                if isinstance(history_data, list):
                    # Only keep up to max_tracks
                    self.track_history = deque(history_data[:self.max_tracks], maxlen=self.max_tracks)
                    logging.debug(f"📋 Loaded {len(self.track_history)} tracks from history.json")
                else:
                    logging.warning("⚠️ history.json exists but is not a list, creating new history")
        except Exception as e:
            logging.error(f"💥 Error loading history.json: {e}")
    
    async def add_track(self, track: TrackInfo, artwork_hash: Optional[str] = None) -> None:
        """Add a track to the history and update the history.json file.
        
        Args:
            track: TrackInfo object containing track information
            artwork_hash: Optional hash for the artwork
        """
        try:
            # Create track entry in the format needed for history.json
            track_entry = {
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "artwork_url": f"/player/publish/{track.image}" if track.image else None,
                "played_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Add image_hash if provided - this will be used by the embeds
            if artwork_hash:
                track_entry["image_hash"] = artwork_hash
                # Add the hashed artwork URL path that points to the ca directory
                track_entry["hashed_artwork_url"] = f"/player/publish/ca/{artwork_hash}.jpg"
            
            # Check if this is the same as the most recent track (avoid duplicates)
            if (self.track_history and 
                self.track_history[0].get("title") == track_entry["title"] and 
                self.track_history[0].get("artist") == track_entry["artist"]):
                # Update timestamp and any other changed fields
                self.track_history[0].update(track_entry)
                logging.debug("📋 Updated existing track in history (same track played again)")
            else:
                # Add to the front of the history
                self.track_history.appendleft(track_entry)
                logging.debug("📋 Added new track to history")
            
            # Write updated history to file
            await self.save_history()
            
        except Exception as e:
            logging.error(f"💥 Error adding track to history: {e}")
    
    async def save_history(self) -> None:
        """Write track history to history.json file."""
        try:
            with open(self.history_json_path, 'w') as f:
                # Convert deque to list for JSON serialization
                json.dump(list(self.track_history), f, indent=2)
            
            logging.debug(f"📋 Saved {len(self.track_history)} tracks to history.json")
        except Exception as e:
            logging.error(f"💥 Error saving history.json: {e}")
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get track history, optionally limited to a number of tracks.
        
        Args:
            limit: Optional limit of tracks to return
            
        Returns:
            List of track history entries
        """
        if limit and limit > 0:
            return list(self.track_history)[:limit]
        return list(self.track_history)