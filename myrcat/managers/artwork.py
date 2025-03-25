"""Artwork manager for Myrcat."""

import logging
import shutil
import uuid
import asyncio
import tempfile
from pathlib import Path
from typing import Optional

# Import Pillow conditionally to handle environments without it
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logging.warning("⚠️ Pillow not available. Image resizing for social media disabled.")

from myrcat.exceptions import ArtworkError


class ArtworkManager:
    """Manages artwork file operations."""

    def __init__(
        self,
        incoming_dir: Path,
        publish_dir: Path,
        hashed_artwork_dir: Optional[Path] = None,
    ):
        """Initialize the artwork manager.
        
        Args:
            incoming_dir: Directory where incoming artwork files are stored
            publish_dir: Directory to publish artwork files
            hashed_artwork_dir: Optional directory for hashed artwork files
        """
        self.incoming_dir = incoming_dir
        self.publish_dir = publish_dir
        self.hashed_artwork_dir = hashed_artwork_dir
        self.current_image: Optional[str] = None

        # Create directories if they don't exist
        self.publish_dir.mkdir(parents=True, exist_ok=True)
        if self.hashed_artwork_dir:
            self.hashed_artwork_dir.mkdir(parents=True, exist_ok=True)

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
        if not await self.wait_for_file(incoming_path):
            logging.warning(f"⚠️ Artwork file missing: {incoming_path}")
            return None

        try:
            # Generate unique filename
            new_filename = f"{uuid.uuid4()}.jpg"
            publish_path = self.publish_dir / new_filename

            # Copy file to web server with unique name
            shutil.copy2(str(incoming_path), str(publish_path))
            # Remove original MYR12345.jpg from Myriad FTP
            incoming_path.unlink()
            # Update current image
            self.current_image = new_filename
            # Clean up old files from web server directory
            await self.cleanup_old_artwork()

            logging.debug(f"🎨 Artwork published: {new_filename}")
            return new_filename
        except Exception as e:
            logging.error(f"💥 Error processing artwork: {e}")
            return None

    async def create_hashed_artwork(
        self, filename: str, artist: str, title: str
    ) -> Optional[str]:
        """Create a hashed version of the artwork using artist and title.

        Args:
            filename: The original artwork filename
            artist: The track artist
            title: The track title

        Returns:
            str: The hash used for the artwork file
        """
        if not filename or not self.hashed_artwork_dir:
            return None

        # Generate hash from artist and title
        artwork_hash = self.generate_hash(artist, title)

        # Path to original artwork
        original_artwork = self.publish_dir / filename

        # Ensure the file exists before trying to copy it
        if not original_artwork.exists():
            logging.warning(
                f"⚠️ Original artwork not found for hashing: {original_artwork}"
            )
            return artwork_hash

        try:
            # Create hashed artwork filename
            hashed_filename = f"{artwork_hash}.jpg"
            hashed_artwork_path = self.hashed_artwork_dir / hashed_filename

            # Only copy if the hashed file doesn't already exist
            if not hashed_artwork_path.exists():
                shutil.copy2(str(original_artwork), str(hashed_artwork_path))
                logging.debug(f"🎨 Created hashed artwork: {hashed_filename}")

            return artwork_hash
        except Exception as e:
            logging.error(f"💥 Error creating hashed artwork: {e}")
            return artwork_hash  # Still return the hash even if file operation fails

    async def wait_for_file(self, incoming_path: Path) -> bool:
        """Wait for file to appear, return True if found.
        
        Args:
            incoming_path: Path to the file to wait for
            
        Returns:
            True if the file exists, False otherwise
        """
        for _ in range(10):
            if incoming_path.exists():
                return True
            await asyncio.sleep(0.5)
        logging.debug(f"⚠️ wait_for_file failed on {incoming_path}")
        return False

    def generate_hash(self, artist, title):
        """
        Generate a hash from artist and title that matches the JavaScript implementation.
        This ensures compatibility between the web player and the server.
        
        Args:
            artist: Track artist
            title: Track title
            
        Returns:
            Hash string
        """
        str_to_hash = f"{artist}-{title}".lower()
        hash_val = 0
        for i in range(len(str_to_hash)):
            hash_val = ((hash_val << 5) - hash_val) + ord(str_to_hash[i])
            hash_val = (
                hash_val & 0xFFFFFFFF
            )  # Convert to 32bit integer (equivalent to |= 0 in JS)

        return format(abs(hash_val), "x")  # Convert to hex string like in JS

    async def cleanup_old_artwork(self) -> None:
        """Remove old artwork files from publish directory."""
        try:
            for file in self.publish_dir.glob("*.jpg"):
                # Don't delete the current image file
                if self.current_image and file.name == self.current_image:
                    continue
                try:
                    file.unlink()
                    logging.debug(f"🧹 Removed old artwork: {file.name}")
                except Exception as e:
                    logging.error(f"Error removing old artwork {file.name}: {e}")
        except Exception as e:
            logging.error(f"💥 Error during artwork cleanup: {e}")
            
    async def resize_for_social(self, image_path: Path, size: tuple = (600, 600)) -> tuple[Optional[Path], tuple]:
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
        if not PILLOW_AVAILABLE:
            logging.warning("⚠️ Cannot resize image: Pillow library not available")
            return None, (0, 0)
        
        if not image_path.exists():
            logging.error(f"💥 Cannot resize image: File not found: {image_path}")
            return None, (0, 0)
            
        try:
            # Create a temp file with the same extension as the original
            suffix = image_path.suffix
            temp_fd, temp_path_str = tempfile.mkstemp(suffix=suffix)
            temp_path = Path(temp_path_str)
            
            # Open and resize image
            with Image.open(image_path) as img:
                # Convert to RGB if has transparency (RGBA)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                    
                # Create a copy of the image to avoid modifying the original
                img_copy = img.copy()
                
                # Calculate the resize dimensions while preserving aspect ratio
                img_width, img_height = img_copy.size
                ratio = min(size[0] / img_width, size[1] / img_height)
                new_width = int(img_width * ratio)
                new_height = int(img_height * ratio)
                
                # Resize the image (preserving aspect ratio)
                img_resized = img_copy.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Create a new blank square image with the target size (white background)
                new_img = Image.new("RGB", size, (255, 255, 255))
                
                # Paste the resized image centered on the white canvas
                paste_x = (size[0] - new_width) // 2
                paste_y = (size[1] - new_height) // 2
                new_img.paste(img_resized, (paste_x, paste_y))
                
                # Save the result
                new_img.save(temp_path, format='JPEG', quality=90)
            
            logging.debug(f"🖼️ Resized image for social media: {image_path.name} → {size[0]}x{size[1]}")
            return temp_path, size
        except Exception as e:
            logging.error(f"💥 Error resizing image for social media: {e}")
            # Try to clean up any temp file that might have been created
            if 'temp_path' in locals() and Path(temp_path).exists():
                try:
                    Path(temp_path).unlink()
                except:
                    pass
            return None, (0, 0)