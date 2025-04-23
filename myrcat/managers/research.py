"""Research manager for artist information."""

import logging
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import tempfile
import aiohttp
from urllib.parse import quote
import asyncio

from myrcat.models import TrackInfo
from myrcat.managers.database import DatabaseManager
from myrcat.managers.content import ContentGenerator
from myrcat.managers.artwork import ArtworkManager


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

        # Kagi API configuration
        self.kagi_api_key = config.get("artist_research", "kagi_api_key", fallback=None)
        self.kagi_max_results = config.getint(
            "artist_research", "kagi_max_results", fallback=5
        )
        self.kagi_min_width = config.getint(
            "artist_research", "kagi_min_width", fallback=500
        )
        self.kagi_min_height = config.getint(
            "artist_research", "kagi_min_height", fallback=500
        )
        self.kagi_image_filters = config.get(
            "artist_research", "kagi_image_filters", fallback="photo,face"
        )
        self.kagi_safe_search = config.get(
            "artist_research", "kagi_safe_search", fallback="moderate"
        )

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        self.cache_max_age = timedelta(days=30)  # Cache results for 30 days

        # Cache cleanup configuration
        self.cleanup_batch_size = 100  # Number of records to delete in one batch
        self.cleanup_interval = timedelta(days=7)  # Run cleanup weekly
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
        1. Removes entries older than cache_max_age from the database
        2. Processes deletions in batches to avoid locking the database
        3. Runs periodically based on cleanup_interval
        4. Removes orphaned image files from the images directory
        """
        # Check if it's time to run cleanup
        now = datetime.now()
        if self.last_cleanup and now - self.last_cleanup < self.cleanup_interval:
            return

        try:
            logging.info("🧹 Starting image search cache cleanup")
            cutoff_date = (now - self.cache_max_age).isoformat()
            total_deleted = 0

            with self.db._get_connection() as conn:
                while True:
                    # Get batch of expired entries
                    cursor = conn.execute(
                        """
                        SELECT id, search_query
                        FROM image_search_cache
                        WHERE cached_at < ?
                        LIMIT ?
                        """,
                        (cutoff_date, self.cleanup_batch_size),
                    )
                    expired_entries = cursor.fetchall()

                    if not expired_entries:
                        break

                    # Delete the batch
                    entry_ids = [entry[0] for entry in expired_entries]
                    placeholders = ",".join("?" * len(entry_ids))

                    conn.execute(
                        f"""
                        DELETE FROM image_search_cache
                        WHERE id IN ({placeholders})
                        """,
                        entry_ids,
                    )

                    batch_count = len(expired_entries)
                    total_deleted += batch_count
                    logging.debug(f"🧹 Deleted {batch_count} expired cache entries")

                    # Small delay between batches to prevent database lockup
                    await asyncio.sleep(0.1)

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
            # Generate artist hash
            artist_hash = self.artwork_manager.generate_hash(track.artist, track.title)

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
            # Get image search query from LLM
            search_info = await self._get_image_search_query(artist, title)
            if not search_info:
                return None

            query, rationale = search_info
            logging.debug(f"🔍 Image search query for {artist}: {query}")
            logging.debug(f"📝 Search rationale: {rationale}")

            # Use web search to find image URL
            image_url = await self._find_artist_image_url(query)
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

    async def _get_image_search_query(
        self, artist: str, title: str
    ) -> Optional[Tuple[str, str]]:
        """Get optimized image search query from LLM.

        Args:
            artist: Artist name

        Returns:
            Tuple of (search query, rationale) if successful, None otherwise
        """
        try:
            # Load the image search prompt template
            prompt_path = self.prompts_directory / "artist_image_search.txt"
            if not prompt_path.exists():
                logging.error("❌ Artist image search prompt template not found")
                return None

            with open(prompt_path) as f:
                prompt_template = f.read()

            # Format the prompt with artist info
            prompt = prompt_template.format(artist=artist, title=title)

            # Generate search query content
            response = await self.content_generator.generate_content(
                prompt=prompt, max_tokens=200
            )

            if not response:
                return None

            # Parse response
            query_match = re.search(r"QUERY:\s*(.+)", response)
            rationale_match = re.search(r"RATIONALE:\s*(.+)", response)

            if query_match and rationale_match:
                return query_match.group(1).strip(), rationale_match.group(1).strip()

            return None

        except Exception as e:
            logging.error(f"💥 Error generating image search query: {e}")
            return None

    async def _check_image_cache(self, search_query: str) -> Optional[Dict[str, Any]]:
        """Check if we have a cached result for this search query.

        Args:
            search_query: The search query to check

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
                    (search_query,),
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
                            (search_query,),
                        )

            return None
        except Exception as e:
            logging.error(f"💥 Error checking image cache: {e}")
            return None

    async def _cache_image_result(
        self, search_query: str, image_url: str, width: int, height: int
    ) -> None:
        """Cache an image search result.

        Args:
            search_query: The search query
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
                    (search_query, image_url, width, height),
                )
        except Exception as e:
            logging.error(f"💥 Error caching image result: {e}")

    async def _make_kagi_request(
        self, session: aiohttp.ClientSession, api_url: str, headers: Dict, params: Dict
    ) -> Optional[Dict]:
        """Make a request to the Kagi API with retry logic.

        Args:
            session: aiohttp ClientSession
            api_url: The API endpoint URL
            headers: Request headers
            params: Request parameters

        Returns:
            Response data if successful, None otherwise
        """
        for attempt in range(self.max_retries):
            try:
                async with session.get(
                    api_url, headers=headers, params=params
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:  # Rate limit
                        retry_after = int(
                            response.headers.get("Retry-After", self.retry_delay)
                        )
                        logging.warning(
                            f"⏳ Rate limited, waiting {retry_after}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(retry_after)
                    else:
                        logging.error(f"❌ Kagi API error: {response.status}")
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))

            except aiohttp.ClientError as e:
                logging.error(f"💥 Request error: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        return None

    async def _find_artist_image_url(self, search_query: str) -> Optional[str]:
        """Find best artist image URL using Kagi image search API.

        Args:
            search_query: Optimized search query from LLM

        Returns:
            URL of best matching image if found, None otherwise
        """
        if not self.kagi_api_key:
            logging.error("❌ Kagi API key not configured")
            return None

        try:
            # Check cache first
            cached_result = await self._check_image_cache(search_query)
            if cached_result:
                logging.debug("🎯 Using cached image result")
                return cached_result["url"]

            # Construct the API URL with parameters
            encoded_query = quote(search_query)
            api_url = "https://kagi.com/api/v0/image_search"

            # Prepare headers and parameters
            headers = {
                "Authorization": f"Bot {self.kagi_api_key}",
                "Content-Type": "application/json",
            }

            params = {
                "q": encoded_query,
                "limit": self.kagi_max_results,
                "filter": self.kagi_image_filters,
                "safe_search": self.kagi_safe_search,
            }

            async with aiohttp.ClientSession() as session:
                data = await self._make_kagi_request(session, api_url, headers, params)
                if not data:
                    return None

                # Process results
                if "data" in data and data["data"]:
                    # Filter and sort images by size and quality
                    valid_images = []
                    for image in data["data"]:
                        # Check image dimensions
                        width = image.get("width", 0)
                        height = image.get("height", 0)

                        if (
                            width >= self.kagi_min_width
                            and height >= self.kagi_min_height
                        ):
                            # Calculate aspect ratio similarity to target dimensions
                            target_ratio = self.image_width / self.image_height
                            image_ratio = width / height if height > 0 else 0
                            ratio_diff = abs(target_ratio - image_ratio)

                            valid_images.append(
                                {
                                    "url": image["url"],
                                    "width": width,
                                    "height": height,
                                    "ratio_diff": ratio_diff,
                                }
                            )

                    # Sort by aspect ratio difference (prefer closer to target ratio)
                    valid_images.sort(key=lambda x: x["ratio_diff"])

                    if valid_images:
                        best_image = valid_images[0]
                        logging.debug(
                            f"🖼️ Found image: {best_image['width']}x{best_image['height']}"
                        )

                        # Cache the result
                        await self._cache_image_result(
                            search_query,
                            best_image["url"],
                            best_image["width"],
                            best_image["height"],
                        )

                        return best_image["url"]

            logging.warning("⚠️ No suitable images found")
            return None

        except Exception as e:
            logging.error(f"💥 Error searching for images: {e}")
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
                    INSERT INTO artist_research (artist_hash, research_text)
                    VALUES (?, ?)
                    ON CONFLICT(artist_hash)
                    DO UPDATE SET
                        research_text = excluded.research_text,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (artist_hash, research_text),
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
                    research_data = {
                        "artist": artist,
                        "artist_hash": artist_hash,
                        "research": result[0],
                        "image": result[1] if result[1] else None,
                        "created_at": result[2],
                        "updated_at": result[3],
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

        # Run cache cleanup after config reload
        asyncio.create_task(self._cleanup_cache())
