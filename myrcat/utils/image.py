"""Image processing utilities for Myrcat."""

import logging
import shutil
import uuid
import tempfile
from pathlib import Path
from typing import Optional, Tuple

# Import Pillow conditionally to handle environments without it
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logging.warning("⚠️ Pillow not available. Image processing is disabled.")


async def wait_for_file(incoming_path: Path, max_attempts: int = 10, wait_time: float = 0.5) -> bool:
    """Wait for file to appear, return True if found.

    Args:
        incoming_path: Path to the file to wait for
        max_attempts: Maximum number of attempts to check for file
        wait_time: Time to wait between attempts in seconds

    Returns:
        True if the file exists, False otherwise
    """
    import asyncio
    
    for _ in range(max_attempts):
        if incoming_path.exists():
            return True
        await asyncio.sleep(wait_time)
    
    logging.debug(f"⚠️ wait_for_file failed on {incoming_path}")
    return False


async def copy_file(source_path: Path, target_path: Path, log_message: str = None) -> bool:
    """Copy a file with proper error handling.

    Args:
        source_path: Path to the source file
        target_path: Path to the target destination
        log_message: Optional message to log on success

    Returns:
        True if the copy was successful, False otherwise
    """
    try:
        # Ensure the source file exists
        if not source_path.exists():
            logging.warning(f"⚠️ Source file not found: {source_path}")
            return False

        # Ensure the target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy the file
        shutil.copy2(str(source_path), str(target_path))

        # Log success message if provided
        if log_message:
            logging.debug(log_message)

        return True
    except Exception as e:
        logging.error(f"💥 Error copying file from {source_path} to {target_path}: {e}")
        return False


def generate_uuid_filename(extension: str = "jpg") -> str:
    """Generate a unique filename using UUID.
    
    Args:
        extension: File extension (without dot)
        
    Returns:
        Unique filename with extension
    """
    return f"{uuid.uuid4()}.{extension}"


def generate_hash(text: str) -> str:
    """Generate a hash string from text input.
    
    This function creates a hash suitable for file naming and lookups.
    The algorithm is compatible with JavaScript's string hashing approach.
    
    Args:
        text: Text to hash
        
    Returns:
        Hexadecimal hash string
    """
    # Generate hash value
    hash_val = 0
    for i in range(len(text)):
        hash_val = ((hash_val << 5) - hash_val) + ord(text[i])
        hash_val = hash_val & 0xFFFFFFFF  # Convert to 32bit integer
        
    return format(abs(hash_val), "x")  # Convert to hex string


async def resize_image(
    image_path: Path, 
    width: int, 
    height: int, 
    format: str = "JPEG",
    quality: int = 90,
    keep_aspect_ratio: bool = True,
    background_color: Tuple[int, int, int] = (255, 255, 255)
) -> Optional[Path]:
    """Resize an image to specified dimensions.

    Args:
        image_path: Path to the source image
        width: Target width
        height: Target height
        format: Output format (JPEG, PNG, etc.)
        quality: Image quality (0-100, only for JPEG)
        keep_aspect_ratio: Whether to preserve aspect ratio
        background_color: RGB color tuple for background fill

    Returns:
        Path to resized image temp file, or None if resizing failed
    """
    if not PILLOW_AVAILABLE:
        logging.warning("⚠️ Cannot resize image: Pillow library not available")
        return None

    if not image_path.exists():
        logging.error(f"💥 Cannot resize image: File not found: {image_path}")
        return None

    try:
        # Create a temp file with the appropriate extension
        suffix = f".{format.lower()}" if format.lower() != "jpeg" else ".jpg"
        temp_fd, temp_path_str = tempfile.mkstemp(suffix=suffix)
        temp_path = Path(temp_path_str)

        # Open and resize image
        with Image.open(image_path) as img:
            # Convert to RGB if has transparency (RGBA)
            if img.mode == "RGBA":
                img = img.convert("RGB")

            # Create a copy of the image to avoid modifying the original
            img_copy = img.copy()
            
            if keep_aspect_ratio:
                # Calculate the resize dimensions while preserving aspect ratio
                img_width, img_height = img_copy.size
                ratio = min(width / img_width, height / img_height)
                new_width = int(img_width * ratio)
                new_height = int(img_height * ratio)

                # Resize the image (preserving aspect ratio)
                img_resized = img_copy.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )

                # Create a new blank image with the target size and specified background
                new_img = Image.new("RGB", (width, height), background_color)

                # Paste the resized image centered on the background
                paste_x = (width - new_width) // 2
                paste_y = (height - new_height) // 2
                new_img.paste(img_resized, (paste_x, paste_y))
                
                # Save the result
                new_img.save(temp_path, format=format, quality=quality)
            else:
                # Resize directly to target dimensions without preserving aspect ratio
                img_resized = img_copy.resize(
                    (width, height), Image.Resampling.LANCZOS
                )
                img_resized.save(temp_path, format=format, quality=quality)

        logging.debug(
            f"🖼️ Resized image: {image_path.name} → {width}x{height}"
        )
        return temp_path
    except Exception as e:
        logging.error(f"💥 Error resizing image: {e}")
        # Try to clean up any temp file that might have been created
        if "temp_path" in locals() and Path(temp_path).exists():
            try:
                Path(temp_path).unlink()
            except:
                pass
        return None


async def download_image(url: str, output_path: Optional[Path] = None) -> Optional[Path]:
    """Download an image from a URL.
    
    Args:
        url: URL of the image to download
        output_path: Optional path to save the image (if None, uses a temporary file)
        
    Returns:
        Path to the downloaded image, or None if download failed
    """
    import aiohttp
    
    try:
        # Create temporary file if no output path is provided
        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                output_path = temp_path
        
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"💥 Failed to download image: {url} (status: {response.status})")
                    return None

                content = await response.read()
                output_path.write_bytes(content)
                
        logging.debug(f"📥 Downloaded image: {url} → {output_path}")
        return output_path
        
    except Exception as e:
        logging.error(f"💥 Error downloading image: {e}")
        # Clean up temp file if it exists and we created it
        if output_path is None and "temp_path" in locals() and temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        return None