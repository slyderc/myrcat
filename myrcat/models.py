"""Data models for Myrcat."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


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


@dataclass
class ShowInfo:
    """Show information storage."""

    title: str
    presenter: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    artwork: Optional[str] = None
    genre: Optional[str] = None
    social_tags: Optional[List[str]] = None