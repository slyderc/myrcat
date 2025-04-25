"""Artwork manager for Myrcat."""

import logging
from pathlib import Path
from typing import Optional

from myrcat.services.image_service import ImageService


class ArtworkManager:
    """Manages artwork file operations.
    
    This is a wrapper around the ImageService that maintains backward compatibility
    with the rest of the codebase while delegating actual image operations to the
    centralized ImageService.
    """

    def __init__(
        self,
        incoming_dir: Path,
        publish_dir: Path,
        hashed_artwork_dir: Optional[Path] = None,
        default_artwork_path: Optional[Path] = None,
    ):
        """Initialize the artwork manager.

        Args:
            incoming_dir: Directory where incoming artwork files are stored
            publish_dir: Directory to publish artwork files
            hashed_artwork_dir: Directory for cached artwork files (using hash-based filenames)
            default_artwork_path: Path to default artwork file to use when track image is missing
        """
        # Create and store ImageService instance
        self.image_service = ImageService(
            incoming_dir=incoming_dir,
            publish_dir=publish_dir,
            cache_dir=hashed_artwork_dir,
            default_artwork_path=default_artwork_path
        )
        
        # Keep references for backward compatibility
        self.incoming_dir = incoming_dir
        self.publish_dir = publish_dir
        self.cached_artwork_dir = hashed_artwork_dir  # renamed but kept parameter name for backward compatibility
        self.default_artwork_path = default_artwork_path
        self.current_image = None

    async def process_artwork(self, filename: str) -> Optional[str]:
        """Process artwork file with unique name and clean up old files.

        Args:
            filename: Original artwork filename

        Returns:
            New filename if successful, None otherwise
        """
        result = await self.image_service.process_artwork(filename)
        if result:
            self.current_image = result
        return result

    async def use_default_artwork(self) -> Optional[str]:
        """Use the default artwork when a track has no image or for non-song media types.

        Returns:
            New filename for the default artwork if successful, None otherwise
        """
        result = await self.image_service.use_default_artwork()
        if result:
            self.current_image = result
        return result

    async def create_hashed_artwork(
        self, filename: str, artist: str, title: str
    ) -> Optional[str]:
        """Create a cached version of the artwork using artist and title hash.

        Args:
            filename: The original artwork filename
            artist: The track artist
            title: The track title

        Returns:
            str: The hash used for the artwork file
        """
        return await self.image_service.create_cached_artwork(filename, artist, title)

    async def wait_for_file(self, incoming_path: Path) -> bool:
        """Wait for file to appear, return True if found.

        Args:
            incoming_path: Path to the file to wait for

        Returns:
            True if the file exists, False otherwise
        """
        from myrcat.utils.image import wait_for_file
        return await wait_for_file(incoming_path)

    def generate_hash(self, artist, title=None):
        """
        Generate a hash from artist and optionally title.
        
        When title is provided, generates a hash for the specific artist-title pair.
        When title is None or omitted, generates a hash only for the artist, 
        suitable for artist-level lookups.
        
        Args:
            artist: Track artist
            title: Track title (optional)
            
        Returns:
            Hash string
        """
        if title is None:
            return self.image_service.generate_artist_hash(artist)
        else:
            return self.image_service.generate_track_hash(artist, title)

    async def cleanup_old_artwork(self) -> None:
        """Remove old artwork files from publish directory."""
        await self.image_service.cleanup_old_artwork()

    async def resize_for_social(
        self, image_path: Path, size: tuple = (600, 600)
    ) -> tuple[Optional[Path], tuple]:
        """Resize image to specified dimensions while maintaining aspect ratio.

        Creates a square image with the specified dimensions, centering the original image
        and filling any empty space with white. Ideal for social media posts where
        consistent image sizes are preferred.

        Args:
            image_path: Path to the original image
            size: Desired output size (width, height)

        Returns:
            Tuple of (Path to resized image or None if resizing failed, actual dimensions (width, height))
        """
        return await self.image_service.resize_for_social(
            image_path, width=size[0], height=size[1]
        )

    async def resize_and_convert_image(
        self,
        source_path: Path,
        target_path: Path,
        width: int,
        height: int,
        format: str = "PNG",
    ) -> bool:
        """Resize and convert an image to the specified format.

        Args:
            source_path: Path to source image
            target_path: Path to save the processed image
            width: Target width
            height: Target height
            format: Target format (e.g. 'PNG', 'JPEG')

        Returns:
            True if successful, False otherwise
        """
        return await self.image_service.resize_and_convert(
            source_path, target_path, width, height, format
        )