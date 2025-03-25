"""Image generator for social media posts."""

import logging
from pathlib import Path
from typing import Optional, Dict

from myrcat.models import TrackInfo
from myrcat.exceptions import ImageGenerationError


class ImageGenerator:
    """Generates custom artwork for social media posts."""
    
    def __init__(self, config):
        """Initialize with configuration.
        
        Args:
            config: ConfigParser object with configuration
        """
        self.config = config
        
        # Get template and font directories from config
        templates_dir = config.get("bluesky", "templates_directory", fallback="templates/social")
        fonts_dir = config.get("bluesky", "fonts_directory", fallback="templates/fonts")
        
        self.template_dir = Path(templates_dir)
        self.font_dir = Path(fonts_dir)
        
        # Create directories if they don't exist
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.font_dir.mkdir(parents=True, exist_ok=True)
        
        # Load templates
        self.templates = self._load_templates()
        
    def _load_templates(self) -> Dict[str, Path]:
        """Load available template backgrounds.
        
        Returns:
            Dictionary of template names to file paths
        """
        templates = {}
        try:
            # Add a default template if no templates exist
            if not list(self.template_dir.glob("*.png")):
                logging.warning("⚠️ No template images found in template directory")
                return {"default": None}
                
            for template_file in self.template_dir.glob("*.png"):
                templates[template_file.stem] = template_file
                
            logging.debug(f"🖼 Loaded {len(templates)} image templates")
            return templates
        except Exception as e:
            logging.error(f"💥 Error loading image templates: {e}")
            return {"default": None}
        
    async def generate_track_image(self, track: TrackInfo, output_path: Path) -> Optional[Path]:
        """Generate a custom image for a track when album art isn't available.
        
        Args:
            track: TrackInfo object containing track information
            output_path: Path to save the generated image
            
        Returns:
            Path to the generated image or None if generation failed
        """
        # Check that PIL is available
        try:
            from PIL import Image, ImageDraw, ImageFont
            import textwrap
        except ImportError:
            logging.error("💥 PIL/Pillow not installed - required for image generation")
            raise ImageGenerationError("PIL/Pillow not installed")
        
        try:
            # Choose a template based on program/show if available
            template_key = "default"
            if track.program:
                sanitized_program = track.program.lower().replace(" ", "_")
                if sanitized_program in self.templates:
                    template_key = sanitized_program
                    
            # Ensure template exists
            if template_key not in self.templates or not self.templates[template_key]:
                logging.warning(f"⚠️ Template '{template_key}' not found, using placeholder image")
                return self._create_placeholder_image(track, output_path)
                
            # Create a copy of the template
            template_path = self.templates[template_key]
            img = Image.open(template_path)
            draw = ImageDraw.Draw(img)
            
            # Get font paths
            bold_font_path = self.font_dir / "bold.ttf"
            regular_font_path = self.font_dir / "regular.ttf"
            light_font_path = self.font_dir / "light.ttf"
            
            # Use default fonts if custom fonts are not available
            if not bold_font_path.exists() or not regular_font_path.exists() or not light_font_path.exists():
                # Use default fonts
                try:
                    title_font = ImageFont.truetype(size=36)
                    artist_font = ImageFont.truetype(size=30)
                    details_font = ImageFont.truetype(size=24)
                except Exception:
                    # If default fonts fail, use built-in default
                    title_font = ImageFont.load_default()
                    artist_font = ImageFont.load_default()
                    details_font = ImageFont.load_default()
            else:
                # Use custom fonts
                title_font = ImageFont.truetype(str(bold_font_path), 36)
                artist_font = ImageFont.truetype(str(regular_font_path), 30)
                details_font = ImageFont.truetype(str(light_font_path), 24)
            
            # Position text with better spacing
            width, height = img.size
            
            # Calculate better vertical spacing
            vertical_spacing = height / 10  # 10% of image height
            
            # Add artist (centered, higher on the image)
            artist_text = track.artist
            artist_width = draw.textlength(artist_text, font=artist_font)
            artist_position = ((width - artist_width) / 2, height * 0.25)  # 25% from top
            draw.text(artist_position, artist_text, font=artist_font, fill=(255, 255, 255))
            
            # Add title (centered, middle) with more space for multi-line
            title_text = track.title
            
            # Wrap title if too long - more aggressive wrapping to ensure it fits
            max_width = width * 0.7  # Use 70% of image width
            if draw.textlength(title_text, font=title_font) > max_width:
                # Calculate approximate characters per line based on average character width
                avg_char_width = draw.textlength("m", font=title_font)
                chars_per_line = int(max_width / avg_char_width)
                title_text = textwrap.fill(title_text, width=chars_per_line)
            
            # Get multiline text dimensions
            title_lines = title_text.split('\n')
            line_heights = [draw.textlength(line, font=title_font) for line in title_lines]
            title_height = len(title_lines) * title_font.size
            
            # Center title in middle of image
            title_width = max(line_heights) if line_heights else 0
            title_y = (height / 2) - (title_height / 2)  # Vertically center in middle third
            title_position = ((width - title_width) / 2, title_y)
            
            # Draw the title with proper line spacing
            draw.text(title_position, title_text, font=title_font, fill=(255, 255, 255))
            
            # Add album if available (centered, in bottom third but not too low)
            if track.album and track.album != track.title:  # Only if album differs from title
                album_text = f"From: {track.album}"
                album_width = draw.textlength(album_text, font=details_font)
                album_position = ((width - album_width) / 2, height * 0.7)  # 70% from top
                draw.text(album_position, album_text, font=details_font, fill=(200, 200, 200))
                
            # Add logo/watermark (bottom right with better margin)
            station_text = "Now Wave Radio"
            station_width = draw.textlength(station_text, font=details_font)
            # Position with a proper margin that scales with image size
            margin = min(width, height) * 0.05  # 5% of the smaller dimension
            draw.text((width - station_width - margin, height - details_font.size - margin), 
                      station_text, font=details_font, fill=(180, 180, 180))
            
            # Convert to RGB mode if the image has an alpha channel (RGBA)
            if img.mode == 'RGBA':
                # Create a black background image
                background = Image.new('RGB', img.size, (0, 0, 0))
                # Paste the image with transparency on the background
                background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                # Use the background with image for saving
                img = background
                
            # Save the image as JPEG (requires RGB mode)
            img.save(output_path, format='JPEG', quality=95)
            return output_path
            
        except Exception as e:
            logging.error(f"💥 Error generating track image: {e}")
            return None
    
    def _create_placeholder_image(self, track: TrackInfo, output_path: Path) -> Optional[Path]:
        """Create a simple placeholder image when no template is available.
        
        Args:
            track: TrackInfo object containing track information
            output_path: Path to save the generated image
            
        Returns:
            Path to the generated image or None if generation failed
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
            import textwrap
            
            # Create a blank image with the standard social media aspect ratio (1.91:1)
            width, height = 1200, 630
            img = Image.new('RGB', (width, height), color=(40, 0, 40))  # Dark purple background
            draw = ImageDraw.Draw(img)
            
            # Try to load system fonts for better appearance
            try:
                # Try to find a suitable system font
                title_font = ImageFont.truetype(size=48)
                artist_font = ImageFont.truetype(size=36)
                details_font = ImageFont.truetype(size=24)
            except Exception:
                # Fall back to default font if system fonts aren't available
                title_font = ImageFont.load_default()
                artist_font = ImageFont.load_default()
                details_font = ImageFont.load_default()
            
            # Calculate positions for better layout
            center_x = width / 2
            margin = min(width, height) * 0.1  # 10% margin
            
            # Add artist name (top third)
            artist_text = track.artist
            artist_y = height * 0.25
            try:
                # Center the text if we have advanced font metrics
                artist_width = draw.textlength(artist_text, font=artist_font)
                artist_x = center_x - (artist_width / 2)
            except:
                # Fall back to approximation if textlength not available
                artist_x = margin
            draw.text((artist_x, artist_y), artist_text, fill=(255, 255, 255), font=artist_font)
            
            # Add title (middle, possibly wrapped)
            title_text = track.title
            # Wrap text if needed
            title_lines = textwrap.wrap(title_text, width=30)
            title_y = height * 0.45  # Start in the middle
            
            # Draw each line of the wrapped title
            for line in title_lines:
                try:
                    line_width = draw.textlength(line, font=title_font)
                    line_x = center_x - (line_width / 2)
                except:
                    line_x = margin
                draw.text((line_x, title_y), line, fill=(255, 255, 255), font=title_font)
                title_y += title_font.size * 1.2  # Move down for next line with spacing
            
            # Add album if available
            if track.album and track.album != track.title:
                album_text = f"From: {track.album}"
                album_y = height * 0.75
                try:
                    album_width = draw.textlength(album_text, font=details_font)
                    album_x = center_x - (album_width / 2)
                except:
                    album_x = margin
                draw.text((album_x, album_y), album_text, fill=(200, 200, 200), font=details_font)
            
            # Add Now Wave Radio text with proper positioning
            station_text = "Now Wave Radio"
            station_y = height - details_font.size * 2  # Bottom with margin
            try:
                station_width = draw.textlength(station_text, font=details_font)
                station_x = width - station_width - margin
            except:
                station_x = width - margin * 3  # Approximate position
            draw.text((station_x, station_y), station_text, fill=(200, 200, 200), font=details_font)
            
            # Add a gradient overlay for visual interest (dark at bottom, lighter at top)
            gradient = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            gradient_draw = ImageDraw.Draw(gradient)
            for y in range(height):
                # Create a subtle gradient
                alpha = int((y / height) * 64)  # 0-64 transparency
                gradient_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
            
            # Overlay the gradient
            img = Image.alpha_composite(img.convert('RGBA'), gradient)
            
            # Save the image (already in RGB mode)
            img = img.convert('RGB')  # Convert back to RGB for JPEG
            img.save(output_path, format='JPEG', quality=95)
            return output_path
        except Exception as e:
            logging.error(f"💥 Error creating placeholder image: {e}")
            return None