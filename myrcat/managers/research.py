"""Research manager for artist information."""

import logging
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import tempfile
import aiohttp
from urllib.parse import quote, urlencode
import asyncio
from bs4 import BeautifulSoup

from myrcat.models import TrackInfo
from myrcat.managers.database import DatabaseManager
from myrcat.managers.content import ContentGenerator
from myrcat.managers.artwork import ArtworkManager
from myrcat.utils import normalize_artist_name, clean_artist_name


class ResearchManager:
    """Manages LLM research for artist information."""

    def __init__(
        self,
        config: Dict[str, Any],
        db_manager: DatabaseManager,
        content_generator: ContentGenerator,
        artwork_manager: ArtworkManager,
    ):
        """Initialize the research manager.

        Args:
            config: Configuration dictionary
            db_manager: DatabaseManager instance for data persistence
            content_generator: ContentGenerator instance for LLM prompts
            artwork_manager: ArtworkManager instance for hash generation
        """
        self.config = config
        self.db = db_manager
        self.content_generator = content_generator
        self.artwork_manager = artwork_manager

        # Load configuration
        self.enabled = config.getboolean("artist_research", "enabled", fallback=True)
        self.research_max_age = config.getint(
            "artist_research", "research_max_age", fallback=90
        )
        self.prompts_directory = Path(
            config.get("ai_content", "prompts_directory", fallback="templates/prompts")
        )
        self.images_directory = Path(
            config.get(
                "artist_research",
                "images",
                fallback="templates/artwork/artists",
            )
        )
        self.research_json_path = Path(
            config.get("web", "research_json", fallback="research.json")
        )

        # Image configuration
        self.image_width = config.getint("artist_research", "image_width", fallback=300)
        self.image_height = config.getint(
            "artist_research", "image_height", fallback=300
        )

        # Image sizing configuration
        self.min_image_width = config.getint(
            "artist_research", "min_image_width", fallback=500
        )
        self.min_image_height = config.getint(
            "artist_research", "min_image_height", fallback=500
        )

        # Retry configuration
        self.max_retries = config.getint("artist_research", "max_retries", fallback=3)
        self.retry_delay = config.getint("artist_research", "retry_delay", fallback=1)
        
        # Cache configuration
        cache_max_age_days = config.getint("artist_research", "cache_max_age", fallback=30)
        self.cache_max_age = timedelta(days=cache_max_age_days)  # Cache results for specified days
        
        # Cache cleanup configuration
        cleanup_interval_days = config.getint("artist_research", "cleanup_interval", fallback=7)
        self.cleanup_interval = timedelta(days=cleanup_interval_days)  # Run cleanup weekly
        self.last_cleanup: Optional[datetime] = None

        # Create directories if they don't exist
        self.images_directory.mkdir(parents=True, exist_ok=True)
        self.research_json_path.parent.mkdir(parents=True, exist_ok=True)

        if self.enabled:
            logging.info("✅ Artist research enabled")
        else:
            logging.info("⛔️ Artist research disabled")

        # Don't run initial cache cleanup in __init__
        # It will be handled by the first process_track call
        self.last_cleanup = None

    async def _cleanup_cache(self) -> None:
        """Clean up expired entries from the image search cache and orphaned image files.

        This method:
        1. Removes all entries older than cache_max_age from the database
        2. Runs periodically based on cleanup_interval
        3. Removes orphaned image files from the images directory
        """
        # Check if it's time to run cleanup
        now = datetime.now()
        if self.last_cleanup and now - self.last_cleanup < self.cleanup_interval:
            return

        try:
            logging.info("🧹 Starting image search cache cleanup")
            cutoff_date = (now - self.cache_max_age).isoformat()

            with self.db._get_connection() as conn:
                # Delete all expired entries at once
                cursor = conn.execute(
                    """
                    DELETE FROM image_search_cache
                    WHERE cached_at < ?
                    """,
                    (cutoff_date,),
                )
                
                total_deleted = cursor.rowcount
                
                if total_deleted > 0:
                    logging.info(f"✨ Cleaned up {total_deleted} expired cache entries")
                else:
                    logging.debug("✨ No expired cache entries found")

            # Clean up orphaned image files
            await self._cleanup_orphaned_images()

            # Update last cleanup timestamp
            self.last_cleanup = now

        except Exception as e:
            logging.error(f"💥 Error during cache cleanup: {e}")

    async def _cleanup_orphaned_images(self) -> None:
        """Clean up orphaned image files from the images directory.

        This method:
        1. Gets list of all valid image hashes from the database
        2. Scans the images directory for PNG files
        3. Removes any files that don't correspond to valid hashes
        """
        try:
            # Get all valid image hashes from the database
            with self.db._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT DISTINCT artist_hash
                    FROM artist_research
                    WHERE image_filename IS NOT NULL
                    """
                )
                valid_hashes = {row[0] for row in cursor.fetchall()}

            # Scan images directory
            total_removed = 0
            for image_file in self.images_directory.glob("*.png"):
                # Extract hash from filename (remove .png extension)
                file_hash = image_file.stem

                # If file doesn't correspond to a valid hash, remove it
                if file_hash not in valid_hashes:
                    try:
                        image_file.unlink()
                        total_removed += 1
                        logging.debug(f"🗑️ Removed orphaned image: {image_file.name}")
                    except Exception as e:
                        logging.error(
                            f"💥 Error removing orphaned image {image_file.name}: {e}"
                        )

            if total_removed > 0:
                logging.info(f"🧹 Removed {total_removed} orphaned image files")
            else:
                logging.debug("✨ No orphaned image files found")

        except Exception as e:
            logging.error(f"💥 Error cleaning up orphaned images: {e}")

    async def process_track(self, track: TrackInfo) -> None:
        """Process a track for artist research.

        Args:
            track: TrackInfo object containing track metadata
        """
        if not self.enabled:
            return

        try:
            # Generate artist hash (using artist name only for consistent lookup)
            artist_hash = self.artwork_manager.generate_hash(track.artist, None)

            # Check if we need to do research
            research_needed = await self._check_research_needed(
                track.artist, artist_hash
            )

            if research_needed:
                logging.info(f"🔍 Conducting research for artist: {track.artist}")
                research_text = await self._conduct_research(track)

                if research_text:
                    # Store research text
                    await self._store_research(track.artist, artist_hash, research_text)
                    logging.info(f"✅ Stored research for: {track.artist}")

                    # Find and store artist image
                    image_filename = await self._process_artist_image(
                        track.artist, track.title, artist_hash
                    )
                    if image_filename:
                        await self._update_research_image(artist_hash, image_filename)
                        logging.info(f"🖼️ Updated artist image for: {track.artist}")

            # Update the research JSON file regardless of new research
            await self._update_research_json(track.artist, artist_hash)

        except Exception as e:
            logging.error(f"💥 Error processing artist research: {e}")

        # Run cache cleanup after processing each track
        asyncio.create_task(self._cleanup_cache())

    async def _process_artist_image(
        self, artist: str, title: str, artist_hash: str
    ) -> Optional[str]:
        """Process artist image research and storage.

        Args:
            artist: Artist name
            title: Title of the track
            artist_hash: Hash value for the artist

        Returns:
            Filename of stored image if successful, None otherwise
        """
        try:
            # Clean up the artist name by removing featuring artists
            clean_artist = self._clean_artist_name(artist)
            
            # Find artist image URL using fallback chain
            image_url = await self._find_artist_image_url(clean_artist)
            if not image_url:
                return None

            # Download and process image
            image_filename = await self._download_and_process_image(
                image_url, artist_hash
            )
            return image_filename

        except Exception as e:
            logging.error(f"💥 Error processing artist image: {e}")
            return None

    def _clean_artist_name(self, artist: str) -> str:
        """Clean artist name by removing featuring artists, etc.

        Args:
            artist: Original artist name

        Returns:
            Cleaned artist name
        """
        # Use the utility function for artist name cleaning
        clean_artist = clean_artist_name(artist)
        
        logging.debug(f"🔍 Using artist name for search: '{clean_artist}'")
        return clean_artist

    async def _check_artist_image_cache(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """Check if we have a cached result for this artist.

        Args:
            artist_name: The artist name to check

        Returns:
            Dict with cached image data if found and valid, None otherwise
        """
        try:
            # Run cleanup if needed
            await self._cleanup_cache()

            with self.db._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT image_url, width, height, cached_at
                    FROM image_search_cache
                    WHERE search_query = ? COLLATE NOCASE
                    """,
                    (artist_name,),
                )
                result = cursor.fetchone()

                if result:
                    cached_at = datetime.fromisoformat(result[3])
                    if datetime.now() - cached_at <= self.cache_max_age:
                        return {
                            "url": result[0],
                            "width": result[1],
                            "height": result[2],
                        }
                    else:
                        # Cache is too old, remove it
                        conn.execute(
                            "DELETE FROM image_search_cache WHERE search_query = ?",
                            (artist_name,),
                        )

            return None
        except Exception as e:
            logging.error(f"💥 Error checking image cache: {e}")
            return None

    async def _cache_artist_image(
        self, artist_name: str, image_url: str, width: int, height: int
    ) -> None:
        """Cache an artist image result.

        Args:
            artist_name: The artist name
            image_url: URL of the found image
            width: Image width
            height: Image height
        """
        try:
            with self.db._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO image_search_cache (search_query, image_url, width, height)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(search_query)
                    DO UPDATE SET
                        image_url = excluded.image_url,
                        width = excluded.width,
                        height = excluded.height,
                        cached_at = CURRENT_TIMESTAMP
                    """,
                    (artist_name, image_url, width, height),
                )
        except Exception as e:
            logging.error(f"💥 Error caching image result: {e}")


    async def _find_artist_image_url(self, artist_name: str) -> Optional[str]:
        """Find best artist image URL using multiple sources with fallback chain.

        Args:
            artist_name: Clean artist name to search for

        Returns:
            URL of best matching image if found, None otherwise
        """
        try:
            # Check cache first
            cached_result = await self._check_artist_image_cache(artist_name)
            if cached_result:
                logging.debug("🎯 Using cached image result")
                return cached_result["url"]
            
            # Try each source in order until we find an image
            
            # 1. Try Spotify API if configured
            spotify_image = await self._try_spotify_artist_image(artist_name)
            if spotify_image:
                logging.info(f"✅ Found artist image from Spotify for: {artist_name}")
                await self._cache_artist_image(
                    artist_name,
                    spotify_image,
                    self.min_image_width,  # Using minimum as default
                    self.min_image_height,  # Using minimum as default
                )
                return spotify_image
                
            # 2. Try Last.fm API if configured
            lastfm_image = await self._try_lastfm_artist_image(artist_name)
            if lastfm_image:
                logging.info(f"✅ Found artist image from Last.fm for: {artist_name}")
                await self._cache_artist_image(
                    artist_name,
                    lastfm_image,
                    self.min_image_width,  # Using minimum as default
                    self.min_image_height,  # Using minimum as default
                )
                return lastfm_image
            
            # No images found through any source
            logging.warning(f"⚠️ No artist images found for: {artist_name}")
            return None

        except Exception as e:
            logging.error(f"💥 Error searching for images: {e}")
            return None
            
    async def _try_spotify_artist_image(self, artist_name: str) -> Optional[str]:
        """Try to get artist image from Spotify API.
        
        Args:
            artist_name: Name of the artist
            
        Returns:
            URL of artist image if found, None otherwise
        """
        # Spotify is not implemented yet - placeholder for future implementation
        # This would require Spotify API credentials and OAuth flow
        # For now, we'll just log and return None
        logging.debug(f"ℹ️ Spotify API image search not implemented yet for: {artist_name}")
        return None
        
    async def _try_lastfm_artist_image(self, artist_name: str) -> Optional[str]:
        """Get artist image from Last.fm website by direct scraping.
        
        Args:
            artist_name: Name of the artist
            
        Returns:
            URL of artist image if found, None otherwise
        """
        try:
            # Skip empty artist names
            if not artist_name:
                logging.debug("ℹ️ Empty artist name provided for Last.fm lookup")
                return None
            
            # Check cache first
            cache_result = await self._check_artist_image_cache(artist_name)
            if cache_result:
                logging.debug(f"🎯 Using cached image for {artist_name}")
                return cache_result["url"]
                
            logging.info(f"🔍 Searching Last.fm website for artist: '{artist_name}'")
            
            # Try the direct artist search approach first as it's most reliable
            image_url = await self._scrape_lastfm_artist_search(artist_name)
            if image_url:
                # Cache the result
                await self._cache_artist_image(
                    artist_name,
                    image_url,
                    self.min_image_width,  # Default value
                    self.min_image_height  # Default value
                )
                return image_url
                
            # If direct search fails, try related artist names
            related_searches = self._generate_related_artist_searches(artist_name)
            for related_name, related_desc in related_searches:
                logging.debug(f"🔍 Trying related artist: '{related_name}' ({related_desc})")
                
                image_url = await self._scrape_lastfm_artist_search(related_name)
                if image_url:
                    logging.info(f"✅ Found image using related artist: '{related_name}' ({related_desc})")
                    # Cache with original artist name
                    await self._cache_artist_image(
                        artist_name,
                        image_url,
                        self.min_image_width,
                        self.min_image_height
                    )
                    return image_url
            
            # As a last resort, try to get album covers
            logging.debug(f"🔍 Trying album covers for: {artist_name}")
            image_url = await self._scrape_lastfm_artist_albums(artist_name)
            if image_url:
                logging.info(f"✅ Found album cover for artist: {artist_name}")
                await self._cache_artist_image(
                    artist_name,
                    image_url,
                    self.min_image_width,
                    self.min_image_height
                )
                return image_url
                
            # If still no luck, try album covers for related artists
            for related_name, related_desc in related_searches:
                logging.debug(f"🔍 Trying album covers for related artist: '{related_name}'")
                image_url = await self._scrape_lastfm_artist_albums(related_name)
                if image_url:
                    logging.info(f"✅ Found album cover for related artist: '{related_name}'")
                    await self._cache_artist_image(
                        artist_name,
                        image_url,
                        self.min_image_width,
                        self.min_image_height
                    )
                    return image_url
            
            logging.debug(f"ℹ️ No artist images found on Last.fm for: {artist_name}")
            return None
            
        except Exception as e:
            logging.error(f"💥 Error getting Last.fm image: {e}")
            return None
            
    def _generate_related_artist_searches(self, artist_name: str) -> list:
        """Generate related search terms for an artist.
        
        Args:
            artist_name: Original artist name
            
        Returns:
            List of tuples with (search_term, description)
        """
        related_searches = []
        
        # Common patterns to try
        # Add "The" prefix if not present
        if not artist_name.lower().startswith("the "):
            related_searches.append((f"The {artist_name}", "with 'The' prefix"))
        
        # Remove "The" prefix if present
        if artist_name.lower().startswith("the "):
            without_the = artist_name[4:].strip()
            related_searches.append((without_the, "without 'The' prefix"))
            
        # Add common band suffixes for solo artists
        if " & " not in artist_name.lower() and " and " not in artist_name.lower():
            related_searches.append((f"{artist_name} & The Band", "with '& The Band' suffix"))
            related_searches.append((f"{artist_name} Band", "with 'Band' suffix"))
            
        # For artists like "Noel Gallagher", check their well-known bands
        lower_name = artist_name.lower()
        if "gallagher" in lower_name and "noel" in lower_name:
            related_searches.append(("Noel Gallagher's High Flying Birds", "well-known project"))
            related_searches.append(("Oasis", "well-known band"))
            
        # For other specific artist patterns
        # Add more special cases as needed
            
        return related_searches
    
    async def _scrape_lastfm_artist_search(self, artist_name: str) -> Optional[str]:
        """Scrape Last.fm artist search results to find the best artist image.
        
        Args:
            artist_name: Name of the artist to search for
            
        Returns:
            URL of the best artist image found, or None if no suitable image
        """
        try:
            # Build the URL for artist search
            params = {
                'q': artist_name
            }
            search_url = f"https://www.last.fm/search/artists?{urlencode(params)}"
            logging.debug(f"🔍 Scraping Last.fm artist search: {search_url}")
            
            # Use a browser-like User-Agent to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers) as response:
                    if response.status != 200:
                        logging.debug(f"⚠️ Last.fm search returned status: {response.status}")
                        return None
                    
                    html_content = await response.text()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Store all found image candidates with their scores
                    found_images = []
                    
                    # Look for the grid items in the artist search results
                    # These are the main artist cards in the search results
                    grid_items = soup.select('div.grid-items-item')
                    
                    # Process each artist grid item
                    for i, item in enumerate(grid_items):
                        # Get artist name for comparison
                        name_elem = item.select_one('.grid-items-item-main-text')
                        result_name = name_elem.text.strip() if name_elem else "Unknown"
                        
                        # Find the image
                        img_elem = item.select_one('.grid-items-item-image img')
                        if img_elem and img_elem.get('src'):
                            img_url = img_elem['src']
                            
                            # Skip placeholder images
                            if self._is_valid_image_url(img_url):
                                img_url = self._ensure_absolute_url(img_url)
                                
                                # Calculate match score - position and name similarity
                                # First position gets higher score, exact name match gets bonus
                                match_score = 1.0 / (i + 1)  # Position score
                                
                                # Exact name match gets a big bonus
                                if result_name.lower() == artist_name.lower():
                                    match_score += 10.0
                                # Partial match gets a smaller bonus
                                elif artist_name.lower() in result_name.lower() or result_name.lower() in artist_name.lower():
                                    match_score += 2.0
                                
                                found_images.append((img_url, match_score, result_name))
                                logging.debug(f"Found image for '{result_name}' at position {i+1} (score: {match_score:.1f})")
                    
                    # If we didn't find any grid items, look for other artist result items
                    if not found_images:
                        artist_items = soup.select('.artist-result')
                        for i, item in enumerate(artist_items):
                            name_elem = item.select_one('.artist-name')
                            result_name = name_elem.text.strip() if name_elem else "Unknown"
                            
                            img_elem = item.select_one('img')
                            if img_elem and img_elem.get('src'):
                                img_url = img_elem['src']
                                
                                if self._is_valid_image_url(img_url):
                                    img_url = self._ensure_absolute_url(img_url)
                                    match_score = 1.0 / (i + 1)
                                    
                                    if result_name.lower() == artist_name.lower():
                                        match_score += 5.0
                                    
                                    found_images.append((img_url, match_score, result_name))
                    
                    # Sort all found images by match score (higher is better)
                    found_images.sort(key=lambda x: x[1], reverse=True)
                    
                    # Return the best match if we found any
                    if found_images:
                        best_image, score, found_name = found_images[0]
                        logging.info(f"✅ Found Last.fm search image for '{found_name}' (score: {score:.1f})")
                        return best_image
            
            return None
            
        except Exception as e:
            logging.error(f"💥 Error scraping Last.fm artist search: {e}")
            return None
            
    def _is_valid_image_url(self, url: str) -> bool:
        """Check if an image URL is valid (not a placeholder).
        
        Args:
            url: Image URL to check
            
        Returns:
            True if the URL is valid, False if it's a placeholder
        """
        # Common placeholder patterns to filter out
        placeholder_patterns = [
            "/placeholder/",
            "/default_",
            "/2a96cbd8b46e442fc41c2b86b821562f",
            "/noimage",
            "/star",
            "/avatar/",
            "default_artist_"
        ]
        
        # Check that URL is not empty and doesn't match any placeholder patterns
        if not url or url == "":
            return False
            
        for pattern in placeholder_patterns:
            if pattern in url:
                return False
                
        return True
        
    def _ensure_absolute_url(self, url: str) -> str:
        """Make sure URL is absolute by adding domain if necessary.
        Also tries to get larger version of the image when possible.
        
        Args:
            url: Image URL (possibly relative)
            
        Returns:
            Absolute URL with largest image version available
        """
        # First make the URL absolute
        if url.startswith(('http://', 'https://')):
            absolute_url = url
        elif url.startswith('//'):
            absolute_url = f"https:{url}"
        else:
            absolute_url = f"https://www.last.fm{url if url.startswith('/') else '/' + url}"
        
        # Now try to get larger image version if available
        # Last.fm usually has images like:
        # https://lastfm.freetls.fastly.net/i/u/34s/2a96cbd8b46e442fc41c2b86b821562f.jpg
        # We can replace the size part (34s) with larger versions:
        # 300x300: 300x300
        # 174s: 174x174
        # 64s: 64x64
        # 34s: 34x34
        
        # Try to replace size portion with larger size
        try:
            if '/i/u/' in absolute_url:
                # Find size pattern like /i/u/34s/ and replace with larger version
                size_patterns = ['34s', '64s', '174s']
                for pattern in size_patterns:
                    if f'/i/u/{pattern}/' in absolute_url:
                        # Replace with 300x300 (largest standard size)
                        return absolute_url.replace(f'/i/u/{pattern}/', '/i/u/300x300/')
                        
                # If we reach here, no standard size found, check for other patterns
                if '/i/u/avatar' in absolute_url:
                    # Avatar images have larger versions too
                    return absolute_url.replace('/i/u/avatar', '/i/u/300x300')
        except Exception:
            # If any error processing URL, just return the original absolute URL
            pass
            
        # Return original absolute URL if no larger version found
        return absolute_url
    
    async def _scrape_lastfm_artist_albums(self, artist_name: str) -> Optional[str]:
        """Scrape artist's album covers from Last.fm as a fallback.
        
        Args:
            artist_name: Name of the artist to search for
            
        Returns:
            URL of album cover image if found, None otherwise
        """
        try:
            # Build the URL for artist's albums page
            encoded_artist = quote(artist_name.replace(' ', '+'))
            albums_url = f"https://www.last.fm/music/{encoded_artist}/+albums"
            
            logging.debug(f"🔍 Scraping Last.fm albums for artist: '{artist_name}'")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(albums_url, headers=headers) as response:
                    if response.status != 200:
                        return None
                    
                    html_content = await response.text()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Look for album covers
                    album_images = soup.select('.cover-art img')
                    
                    for img in album_images:
                        if img.get('src') and self._is_valid_image_url(img['src']):
                            img_url = self._ensure_absolute_url(img['src'])
                            logging.info(f"✅ Found album cover image for {artist_name}")
                            return img_url
            
            return None
                
        except Exception as e:
            logging.error(f"💥 Error scraping Last.fm album covers: {e}")
            return None

    async def _download_and_process_image(
        self, image_url: str, artist_hash: str
    ) -> Optional[str]:
        """Download and process artist image.

        Args:
            image_url: URL of the image to download
            artist_hash: Hash value for the artist

        Returns:
            Filename of processed image if successful, None otherwise
        """
        try:
            # Create temporary file for download
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_path = Path(temp_file.name)

            # Download image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        return None

                    content = await response.read()
                    temp_path.write_bytes(content)

            # Process and resize image
            target_path = self.images_directory / f"{artist_hash}.png"
            success = await self.artwork_manager.resize_and_convert_image(
                temp_path,
                target_path,
                width=self.image_width,
                height=self.image_height,
                format="PNG",
            )

            # Clean up temp file
            temp_path.unlink()

            if success:
                return target_path.name

            return None

        except Exception as e:
            logging.error(f"💥 Error downloading/processing image: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return None

    async def _update_research_image(
        self, artist_hash: str, image_filename: str
    ) -> None:
        """Update the image filename in the research record.

        Args:
            artist_hash: Hash value for the artist
            image_filename: Name of the processed image file
        """
        try:
            with self.db._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE artist_research
                    SET image_filename = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE artist_hash = ?
                    """,
                    (image_filename, artist_hash),
                )

        except Exception as e:
            logging.error(f"💥 Error updating research image: {e}")

    async def _check_research_needed(self, artist: str, artist_hash: str) -> bool:
        """Check if research is needed for an artist.

        Args:
            artist: Artist name to check
            artist_hash: Hash value for the artist

        Returns:
            True if research is needed, False otherwise
        """
        try:
            with self.db._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT created_at FROM artist_research
                    WHERE artist_hash = ? COLLATE NOCASE
                    """,
                    (artist_hash,),
                )
                result = cursor.fetchone()

                if not result:
                    return True

                # Check if research is too old
                created_at = datetime.fromisoformat(result[0])
                age_limit = datetime.now() - timedelta(days=self.research_max_age)

                return created_at < age_limit

        except Exception as e:
            logging.error(f"💥 Error checking research status: {e}")
            return False

    async def _conduct_research(self, track: TrackInfo) -> Optional[str]:
        """Conduct LLM research for an artist.

        Args:
            track: TrackInfo object containing track metadata

        Returns:
            Research text if successful, None otherwise
        """
        try:
            # Load the research prompt template
            prompt_path = self.prompts_directory / "artist_research.txt"
            if not prompt_path.exists():
                logging.error("❌ Artist research prompt template not found")
                return None

            with open(prompt_path) as f:
                prompt_template = f.read()

            # Format the prompt with track info
            prompt = prompt_template.format(artist=track.artist, title=track.title)

            # Generate research content
            research_text = await self.content_generator.generate_research_content(
                prompt=prompt, max_tokens=500
            )

            return research_text

        except Exception as e:
            logging.error(f"💥 Error conducting research: {e}")
            return None

    async def _store_research(
        self, artist: str, artist_hash: str, research_text: str
    ) -> None:
        """Store artist research in the database.

        Args:
            artist: Artist name
            artist_hash: Hash value for the artist
            research_text: Research content to store
        """
        try:
            with self.db._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO artist_research (artist, artist_hash, research_text)
                    VALUES (?, ?, ?)
                    ON CONFLICT(artist_hash)
                    DO UPDATE SET
                        artist = excluded.artist,
                        research_text = excluded.research_text,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (artist, artist_hash, research_text),
                )

        except Exception as e:
            logging.error(f"💥 Error storing research: {e}")

    async def _update_research_json(self, artist: str, artist_hash: str) -> None:
        """Update the research JSON file for web display.

        Args:
            artist: Artist name
            artist_hash: Hash value for the artist
        """
        try:
            with self.db._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT research_text, image_filename, created_at, updated_at
                    FROM artist_research
                    WHERE artist_hash = ? COLLATE NOCASE
                    """,
                    (artist_hash,),
                )
                result = cursor.fetchone()

                if result:
                    # Only include fields relevant for website display
                    research_data = {
                        "artist": artist,
                        "research": result[0],
                        "image": result[1] if result[1] else None
                    }

                    # Write to JSON file
                    with open(self.research_json_path, "w") as f:
                        json.dump(research_data, f, indent=2)

        except Exception as e:
            logging.error(f"💥 Error updating research JSON: {e}")

    def load_config(self) -> None:
        """Reload configuration settings."""
        self.enabled = self.config.getboolean(
            "artist_research", "enabled", fallback=True
        )
        self.research_max_age = self.config.getint(
            "artist_research", "research_max_age", fallback=90
        )
        self.prompts_directory = Path(
            self.config.get(
                "ai_content", "prompts_directory", fallback="templates/prompts"
            )
        )
        self.images_directory = Path(
            self.config.get(
                "artist_research",
                "images",
                fallback="templates/artwork/artists",
            )
        )
        self.research_json_path = Path(
            self.config.get("web", "research_json", fallback="research.json")
        )
        # Image sizing configuration
        self.min_image_width = self.config.getint(
            "artist_research", "min_image_width", fallback=500
        )
        self.min_image_height = self.config.getint(
            "artist_research", "min_image_height", fallback=500
        )
        
        # Retry configuration
        self.max_retries = self.config.getint("artist_research", "max_retries", fallback=3)
        self.retry_delay = self.config.getint("artist_research", "retry_delay", fallback=1)
        
        # Cache configuration
        cache_max_age_days = self.config.getint("artist_research", "cache_max_age", fallback=30)
        self.cache_max_age = timedelta(days=cache_max_age_days)
        
        # Cache cleanup configuration
        cleanup_interval_days = self.config.getint("artist_research", "cleanup_interval", fallback=7)
        self.cleanup_interval = timedelta(days=cleanup_interval_days)

        # Run cache cleanup after config reload
        asyncio.create_task(self._cleanup_cache())
