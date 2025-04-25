"""Image service for Myrcat.

This class centralizes all image processing functionality that was previously
spread across multiple manager classes. It handles artwork processing,
resizing, caching, and artist image retrieval.
"""

import logging
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from myrcat.utils.image import (
    wait_for_file,
    copy_file,
    generate_uuid_filename, 
    generate_hash,
    resize_image,
    download_image,
    PILLOW_AVAILABLE
)
from myrcat.utils.strings import normalize_artist_name, generate_artist_title_hash
from myrcat.utils.file import ensure_directory, cleanup_files


class ImageService:
    """Centralized service for all image processing operations.
    
    This service combines functionality that was previously split between
    ArtworkManager and parts of ResearchManager.
    """
    
    def __init__(
        self,
        incoming_dir: Path,
        publish_dir: Path,
        cache_dir: Optional[Path] = None,
        artists_dir: Optional[Path] = None,
        default_artwork_path: Optional[Path] = None,
    ):
        """Initialize the image service.
        
        Args:
            incoming_dir: Directory where incoming artwork files are stored
            publish_dir: Directory to publish artwork files
            cache_dir: Directory for cached artwork files (using hash-based filenames)
            artists_dir: Directory for artist images
            default_artwork_path: Path to default artwork file to use when image is missing
        """
        self.incoming_dir = incoming_dir
        self.publish_dir = publish_dir
        self.cache_dir = cache_dir
        self.artists_dir = artists_dir
        self.default_artwork_path = default_artwork_path
        self.current_image: Optional[str] = None
        
        # Create directories if they don't exist
        ensure_directory(self.publish_dir)
        if self.cache_dir:
            ensure_directory(self.cache_dir)
        if self.artists_dir:
            ensure_directory(self.artists_dir)
            
        # Check default artwork
        if self.default_artwork_path:
            if self.default_artwork_path.exists():
                logging.debug(f"🎨 Default artwork configured: {self.default_artwork_path}")
            else:
                logging.warning(f"⚠️ Default artwork file not found: {self.default_artwork_path}")
    
    # === Track Artwork Methods ===
        
    async def process_artwork(self, filename: str) -> Optional[str]:
        """Process artwork file with unique name and clean up old files.
        
        Args:
            filename: Original artwork filename
            
        Returns:
            New filename if successful, None otherwise
        """
        if not filename:
            return None
            
        incoming_path = self.incoming_dir / filename
        
        # Wait for up to 5 seconds for the file to appear
        if not await wait_for_file(incoming_path):
            logging.warning(f"⚠️ Artwork file missing: {incoming_path}")
            return None
            
        # Publish the image using the helper method
        new_filename = await self._publish_image_to_artwork_dir(
            incoming_path, remove_source=True
        )
        
        if new_filename:
            logging.debug(f"🎨 Artwork published: {new_filename}")
            
        return new_filename
    
    async def use_default_artwork(self) -> Optional[str]:
        """Use the default artwork when a track has no image.
        
        Returns:
            New filename for the default artwork if successful, None otherwise
        """
        if not self.default_artwork_path or not self.default_artwork_path.exists():
            logging.warning("⚠️ Default artwork not found or not configured")
            return None
            
        # Publish the default image using the helper method
        new_filename = await self._publish_image_to_artwork_dir(
            self.default_artwork_path, remove_source=False
        )
        
        if new_filename:
            logging.debug(f"🎨 Default artwork published: {new_filename}")
            
        return new_filename
    
    async def _publish_image_to_artwork_dir(
        self, source_path: Path, remove_source: bool = False
    ) -> Optional[str]:
        """Publish an image to the artwork directory with a unique name.
        
        Args:
            source_path: Path to the source image file
            remove_source: Whether to remove the source file after copying
            
        Returns:
            New filename if successful, None otherwise
        """
        if not source_path.exists():
            logging.warning(f"⚠️ Source artwork file missing: {source_path}")
            return None
            
        try:
            # Generate unique filename
            new_filename = generate_uuid_filename("jpg")
            publish_path = self.publish_dir / new_filename
            
            # Copy file to publish directory with unique name
            copy_success = await copy_file(
                source_path=source_path, target_path=publish_path
            )
            
            if not copy_success:
                return None
                
            # Remove source file if requested
            if remove_source:
                try:
                    source_path.unlink()
                except Exception as e:
                    logging.warning(f"⚠️ Could not remove source file {source_path}: {e}")
                    
            # Update current image
            self.current_image = new_filename
            
            # Clean up old files from publish directory
            await self.cleanup_old_artwork()
            
            return new_filename
        except Exception as e:
            logging.error(f"💥 Error publishing artwork from {source_path}: {e}")
            return None
    
    async def create_cached_artwork(
        self, filename: str, artist: str, title: str
    ) -> Optional[str]:
        """Create a cached version of the artwork using artist and title hash.
        
        Args:
            filename: The original artwork filename
            artist: The track artist
            title: The track title
            
        Returns:
            The hash used for the artwork file
        """
        if not filename or not self.cache_dir:
            return None
            
        # Generate hash from artist and title
        artwork_hash = generate_artist_title_hash(artist, title)
        
        # Path to original artwork
        original_artwork = self.publish_dir / filename
        
        # Ensure the file exists before trying to copy it
        if not original_artwork.exists():
            logging.warning(f"⚠️ Original artwork not found for caching: {original_artwork}")
            return artwork_hash
            
        try:
            # Create cached artwork filename and path
            cached_filename = f"{artwork_hash}.jpg"
            cached_artwork_path = self.cache_dir / cached_filename
            
            # Only copy if the cached file doesn't already exist
            if not cached_artwork_path.exists():
                await copy_file(
                    source_path=original_artwork,
                    target_path=cached_artwork_path,
                    log_message=f"🎨 Created cached artwork: {cached_filename}",
                )
                
            return artwork_hash
        except Exception as e:
            logging.error(f"💥 Error creating cached artwork: {e}")
            return artwork_hash  # Still return the hash even if file operation fails
    
    async def cleanup_old_artwork(self) -> None:
        """Remove old artwork files from publish directory."""
        try:
            count = cleanup_files(
                self.publish_dir, 
                "*.jpg", 
                exclude_filenames=[self.current_image] if self.current_image else []
            )
            if count > 0:
                logging.debug(f"🧹 Removed {count} old artwork files")
        except Exception as e:
            logging.error(f"💥 Error during artwork cleanup: {e}")
    
    # === Image Processing Methods ===
    
    async def resize_for_social(
        self, image_path: Path, width: int = 600, height: int = 600
    ) -> Tuple[Optional[Path], Tuple[int, int]]:
        """Resize image for social media posting.
        
        Args:
            image_path: Path to the original image
            width: Desired width
            height: Desired height
            
        Returns:
            Tuple of (resized image path, dimensions)
        """
        temp_path = await resize_image(
            image_path=image_path,
            width=width,
            height=height,
            format="JPEG",
            quality=90,
            keep_aspect_ratio=True
        )
        
        if temp_path:
            return temp_path, (width, height)
        return None, (0, 0)
    
    async def resize_and_convert(
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
        if not PILLOW_AVAILABLE:
            logging.error("❌ Pillow not available for image processing")
            return False
            
        temp_path = await resize_image(
            image_path=source_path,
            width=width,
            height=height,
            format=format,
            quality=95,
            keep_aspect_ratio=True
        )
        
        if temp_path:
            try:
                # Create target directory if it doesn't exist
                ensure_directory(target_path.parent)
                
                # Copy the temp file to the target path
                await copy_file(temp_path, target_path)
                
                # Clean up the temp file
                temp_path.unlink()
                
                logging.debug(f"🖼️ Processed image: {source_path.name} → {target_path.name} ({width}x{height})")
                return True
            except Exception as e:
                logging.error(f"💥 Error saving processed image: {e}")
                # Try to clean up any temp file
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except:
                        pass
                return False
        
        return False
    
    # === Artist Image Methods ===
    
    async def process_artist_image(
        self, image_url: str, artist_hash: str, width: int, height: int
    ) -> Optional[str]:
        """Process an artist image from URL.
        
        Args:
            image_url: URL of the artist image
            artist_hash: Hash value for the artist
            width: Target width
            height: Target height
            
        Returns:
            Filename of the processed image if successful, None otherwise
        """
        if not self.artists_dir:
            logging.error("❌ Artist images directory not configured")
            return None
            
        try:
            # Download image to temp file
            temp_path = await download_image(image_url)
            if not temp_path:
                return None
                
            # Process and resize image
            target_path = self.artists_dir / f"{artist_hash}.png"
            success = await self.resize_and_convert(
                temp_path,
                target_path,
                width=width,
                height=height,
                format="PNG",
            )
            
            # Clean up temp file
            try:
                temp_path.unlink()
            except:
                pass
                
            if success:
                return target_path.name
                
            return None
        except Exception as e:
            logging.error(f"💥 Error processing artist image: {e}")
            return None
    
    # === Hash Generation Methods ===
    
    def generate_artist_hash(self, artist: str) -> str:
        """Generate a hash for an artist name.
        
        Args:
            artist: Artist name
            
        Returns:
            Hash string for the artist
        """
        # Artist-only hash with normalization
        normalized = normalize_artist_name(artist)
        return generate_hash(normalized)
    
    def generate_track_hash(self, artist: str, title: str) -> str:
        """Generate a hash for an artist-title pair.
        
        Args:
            artist: Artist name
            title: Track title
            
        Returns:
            Hash string for the artist-title pair
        """
        return generate_artist_title_hash(artist, title)