"""Content generator for social media posts."""

import logging
import random
import asyncio
import aiohttp
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

from myrcat.models import TrackInfo
from myrcat.managers.prompt import PromptManager


class ContentGenerator:
    """Generates AI-enhanced content for social media posts.

    TODO: Potential improvements:
    - Support for multiple AI providers (OpenAI, Anthropic, etc.)
    - Implement content caching to reduce API costs
    - Add content moderation/filtering
    - Support for themed content based on genres or events
    - Implement feedback loop to improve future content
    - Add support for generating images with AI
    """

    def __init__(self, config, network_config=None):
        """Initialize with configuration.

        Args:
            config: ConfigParser object with configuration
            network_config: Optional network configuration for API calls
        """
        self.config = config
        self.network_config = network_config

        # Load settings from config
        self.load_config()

        # Load templates for non-AI posts
        self.templates = self._load_templates()

    def load_config(self):
        """Load settings from configuration.

        This method can be called to reload configuration settings when the
        config file changes without requiring re-initialization of the class.
        """
        # Get AI configuration
        self.anthropic_api_key = self.config.get(
            "ai_content", "anthropic_api_key", fallback=""
        )
        self.model = self.config.get(
            "ai_content", "model", fallback="claude-3-7-sonnet-latest"
        )
        self.max_tokens = self.config.getint("ai_content", "max_tokens", fallback=150)
        self.temperature = self.config.getfloat(
            "ai_content", "temperature", fallback=0.7
        )
        self.ai_post_ratio = self.config.getfloat(
            "ai_content", "ai_post_ratio", fallback=0.3
        )
        self.testing_mode = self.config.getboolean(
            "ai_content", "testing_mode", fallback=False
        )

        # Initialize prompt manager
        prompts_dir = Path(
            self.config.get(
                "ai_content", "prompts_directory", fallback="templates/prompts"
            )
        )
        self.prompt_manager = PromptManager(prompts_dir)

        if self.testing_mode:
            logging.warning(
                f"🧪 TESTING MODE ENABLED: AI content generation will be used for ALL posts (100%)"
            )
        elif self.anthropic_api_key:
            logging.info(
                f"🤖 AI content enabled for {int(self.ai_post_ratio * 100)}% of posts using {self.model}"
            )

    def _load_templates(self):
        """Load post templates."""
        return {
            "standard": "🎵 Now Playing on Now Wave Radio:\n{artist} - {title}",
            "with_album": "🎵 Now Playing on Now Wave Radio:\n{artist} - {title}\nFrom the album: {album}",
            "nostalgic": "Taking you back to {year} with {artist}'s '{title}' on Now Wave Radio! 🎵",
            "discovery": "Discover {artist} with their track '{title}' now playing on Now Wave Radio! 🎵",
            "dj_pick": "DJ Pick: {presenter} has selected {artist}'s '{title}' for your listening pleasure on {program}! 🎧",
        }

    async def generate_track_description(self, track: TrackInfo) -> tuple[str, dict]:
        """Generate an engaging description for a track.

        Args:
            track: TrackInfo object containing track information

        Returns:
            Tuple of (generated description string, metadata dict with source info)
        """
        template_name = "unknown"
        source_type = "template"
        prompt_name = None

        # First try using built-in templates based on track attributes
        if track.presenter and track.program:
            template = self.templates["dj_pick"]
            template_name = "dj_pick"
        elif track.year:
            # Handle both string and integer year values
            try:
                year_value = (
                    int(track.year) if isinstance(track.year, str) else track.year
                )
                if year_value < 2000:
                    template = self.templates["nostalgic"]
                    template_name = "nostalgic"
                else:
                    if track.album:
                        template = self.templates["with_album"]
                        template_name = "with_album"
                    else:
                        template = self.templates["standard"]
                        template_name = "standard"
            except (ValueError, TypeError):
                if track.album:
                    template = self.templates["with_album"]
                    template_name = "with_album"
                else:
                    template = self.templates["standard"]
                    template_name = "standard"
        elif track.album:
            template = self.templates["with_album"]
            template_name = "with_album"
        else:
            template = self.templates["standard"]
            template_name = "standard"

        # Fill in the template
        description = template.format(
            artist=track.artist,
            title=track.title,
            album=track.album or "",
            year=track.year or "",
            presenter=track.presenter or "",
            program=track.program or "",
        )

        # Create metadata for logging
        metadata = {
            "source_type": source_type,
            "template_name": template_name,
            "prompt_name": None,
        }

        # Use AI if testing mode is enabled or random chance is below threshold
        if self.anthropic_api_key and (
            self.testing_mode or random.random() < self.ai_post_ratio
        ):
            if self.testing_mode:
                logging.debug(f"🧪 Using AI for post (testing mode enabled)")

            try:
                enhanced, prompt_metadata = await self._get_ai_enhanced_description(
                    track
                )
                if enhanced:
                    metadata.update(
                        {
                            "source_type": "ai",
                            "prompt_name": prompt_metadata.get("prompt_name"),
                        }
                    )
                    return enhanced, metadata
            except Exception as e:
                logging.error(f"💥 Error generating AI description: {e}")

        return description, metadata

    async def _get_ai_enhanced_description(
        self, track: TrackInfo
    ) -> tuple[Optional[str], dict]:
        """Generate an AI-enhanced description using Anthropic's Claude.

        Args:
            track: TrackInfo object containing track information

        Returns:
            Tuple of (AI-generated description or None if generation failed,
                     metadata dict with prompt info)
        """
        prompt_name = "unknown"
        metadata = {"prompt_name": prompt_name}

        try:
            # Create track info dictionary for prompt template
            track_dict = {
                "title": track.title,
                "artist": track.artist,
                "album": track.album or "Unknown",
                "year": track.year or "Unknown",
                "program": track.program or "Now Wave Radio",
                "presenter": track.presenter or "DJ",
            }

            # Get the appropriate prompt template for this track
            prompt_template, selected_prompt_name = self.prompt_manager.select_prompt(
                track_dict
            )
            prompt_name = selected_prompt_name
            metadata["prompt_name"] = prompt_name

            # Format the prompt with track info
            prompt = self.prompt_manager.format_prompt(prompt_template, track_dict)

            logging.debug(f"🤖 Using AI prompt '{prompt_name}': {prompt[:100]}...")

            # Use Anthropic API
            async with aiohttp.ClientSession() as session:
                response = await self._call_claude_api(session, prompt)

                if response and response.get("content"):
                    for content_block in response["content"]:
                        if content_block.get("type") == "text":
                            generated_text = content_block.get("text", "").strip()
                            logging.debug(
                                f"🤖 Generated AI text with prompt '{prompt_name}' ({len(generated_text)} chars): {generated_text[:100]}..."
                            )
                            return generated_text, metadata

                return None, metadata
        except Exception as e:
            logging.error(f"💥 Error in AI description generation: {e}")
            return None, metadata

    async def _call_claude_api(self, session, prompt):
        """Call the Anthropic Claude API.

        Args:
            session: aiohttp client session
            prompt: Prompt to send to the API

        Returns:
            API response as dict or None if the call failed
        """
        api_url = "https://api.anthropic.com/v1/messages"

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        data = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }

        try:
            # Get timeout from network config or use default
            timeout = (
                self.network_config.get_aiohttp_timeout() 
                if self.network_config 
                else 30.0
            )
            
            try:
                async with session.post(
                    api_url, 
                    headers=headers, 
                    json=data,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logging.error(
                            f"💥 Claude API error ({response.status}): {error_text}"
                        )
                        return None
            except asyncio.TimeoutError:
                logging.error(f"⏱️ Claude API call timed out after {timeout}s")
                return None
        except Exception as e:
            logging.error(f"💥 Claude API call failed: {e}")
            return None

    async def generate_research_content(
        self, prompt: str, max_tokens: int = 500
    ) -> Optional[str]:
        """Generate research content using the AI model.

        Args:
            prompt: The research prompt to send to the AI
            max_tokens: Maximum number of tokens for the response

        Returns:
            Generated research text if successful, None otherwise
        """
        if not self.anthropic_api_key:
            logging.error("❌ Anthropic API key not configured")
            return None

        try:
            # Use a higher max_tokens value for research content
            original_max_tokens = self.max_tokens
            self.max_tokens = max_tokens

            async with aiohttp.ClientSession() as session:
                response = await self._call_claude_api(session, prompt)

                # Restore original max_tokens
                self.max_tokens = original_max_tokens

                if response and response.get("content"):
                    for content_block in response["content"]:
                        if content_block.get("type") == "text":
                            return content_block.get("text", "").strip()

            return None

        except Exception as e:
            logging.error(f"💥 Error generating research content: {e}")
            return None

    def generate_hashtags(self, track: TrackInfo, is_ai_content: bool = False) -> str:
        """Generate relevant hashtags for the track.

        Args:
            track: TrackInfo object containing track information
            is_ai_content: Whether the post is AI-generated

        Returns:
            String containing hashtags or empty string if AI-generated content
        """
        # If this is AI-generated content, return an empty string (no hashtags)
        if is_ai_content:
            return ""

        # Otherwise, generate hashtags for non-AI content
        hashtags = ["#NowWaveRadio"]

        # Add program hashtag if available
        if track.program:
            program_hashtag = "#" + "".join(
                word.capitalize() for word in track.program.split()
            )
            hashtags.append(program_hashtag)

        # Add artist/band hashtag
        if track.artist:
            # Clean up artist name for hashtag
            # Split by common separators and take the first part (main artist)
            main_artist = (
                track.artist.split(" feat.")[0]
                .split(" ft.")[0]
                .split(" &")[0]
                .split(" and ")[0]
            )

            # Create a clean hashtag (alphanumeric only, no spaces)
            clean_artist = "".join(
                word.capitalize() for word in main_artist.split() if word
            )

            # Remove any non-alphanumeric characters except underscores
            clean_artist = re.sub(r"[^\w]", "", clean_artist)

            # Only add if we have something meaningful
            if clean_artist:
                artist_hashtag = f"#{clean_artist}"
                hashtags.append(artist_hashtag)

        # Add new music hashtag for recent releases
        current_year = datetime.now().year
        try:
            # Convert track.year to string safely for comparison
            year_str = str(track.year) if track.year is not None else ""
            if year_str and str(current_year) in year_str:
                hashtags.append("#NewMusic")
        except Exception:
            # Silently fail if we can't compare years
            pass

        return " ".join(hashtags)
