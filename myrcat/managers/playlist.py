"""Playlist manager for Myrcat."""

import json
import logging
from pathlib import Path
from typing import Optional

from myrcat.models import TrackInfo
from myrcat.exceptions import MyrcatException


class PlaylistManager:
    """Manages playlist.json updates and current track information."""

    def __init__(
        self, playlist_json: Path, playlist_txt: Path, artwork_publish_path: Path
    ):
        """Handles JSON and TXT playlist files.
        
        Args:
            playlist_json: Path to the JSON playlist file
            playlist_txt: Path to the TXT playlist file
            artwork_publish_path: Path to the artwork publish directory
        """
        self.playlist_json = playlist_json
        self.playlist_txt = playlist_txt
        self.artwork_publish_path = artwork_publish_path
        self.current_track: Optional[TrackInfo] = None

        # Ensure parent directories exists
        self.playlist_json.parent.mkdir(parents=True, exist_ok=True)
        self.playlist_txt.parent.mkdir(parents=True, exist_ok=True)

    async def update_track(
        self, track: TrackInfo, artwork_hash: Optional[str] = None
    ) -> None:
        """Update current track and playlist file.

        Args:
            track: TrackInfo object containing new track information
            artwork_hash: Optional hash for the artwork
        """
        try:
            self.current_track = track
            await self.update_playlist_json(track, artwork_hash)
            await self.update_playlist_txt(track)
        except Exception as e:
            logging.error(f"💥 Error updating track: {e}")

    async def update_playlist_json(
        self, track: TrackInfo, artwork_hash: Optional[str] = None
    ) -> None:
        """Update the JSON playlist file with current track information.
        
        Args:
            track: TrackInfo object containing track information
            artwork_hash: Optional hash for the artwork
        """
        try:
            if track.is_song:
                # Standard format for songs
                playlist_data = {
                    "artist": track.artist,
                    "title": track.title,
                    "album": track.album,
                    "image": f"/player/publish/{track.image}" if track.image else None,
                    "program_title": track.program,
                    "presenter": track.presenter,
                    "type": track.type.lower(),  # Add type field with lowercase value
                }
                
                # Add image_hash if provided
                if artwork_hash:
                    playlist_data["image_hash"] = artwork_hash
            else:
                # Special format for non-song media types
                playlist_data = {
                    "artist": "",  # Clear artist value
                    "title": "",   # Clear title value
                    "album": "",   # Clear album value
                    "image": f"/player/publish/{track.image}" if track.image else None,
                    "program_title": track.program,
                    "presenter": track.presenter,
                    "type": track.type.lower(),
                    "image_hash": "",  # Clear image_hash
                }

            # Write JSON file with proper indentation for readability
            with open(self.playlist_json, "w") as f:
                json.dump(playlist_data, f, indent=4)

            logging.debug("💾 Saved new JSON playlist file")
        except Exception as e:
            logging.error(f"💥 Error updating JSON playlist: {e}")

    async def update_playlist_txt(self, track: TrackInfo) -> None:
        """Update the TXT playlist file with current track information.
        
        Args:
            track: TrackInfo object containing track information
        """
        try:
            if track.is_song:
                # Standard format for songs
                with open(self.playlist_txt, "w") as txt_file:
                    txt_file.write(f"{track.artist} - {track.title}\n")
            else:
                # Fixed text for non-song media types
                with open(self.playlist_txt, "w") as txt_file:
                    txt_file.write("The Next Wave Today - Now Wave Radio\n")

            logging.debug("💾 Saved new TXT playlist file")
        except Exception as e:
            logging.error(f"💥 Error updating TXT playlist: {e}")