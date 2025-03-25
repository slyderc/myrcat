"""Content generator for social media posts."""

import logging
import random
import asyncio
import aiohttp
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

from myrcat.models import TrackInfo
from myrcat.managers.prompt import PromptManager


class ContentGenerator:
    """Generates AI-enhanced content for social media posts."""

    def __init__(self, config):
        """Initialize with configuration.

        Args:
            config: ConfigParser object with configuration
        """
        self.config = config

        # Get AI configuration
        self.anthropic_api_key = config.get(
            "ai_content", "anthropic_api_key", fallback=""
        )
        self.model = config.get(
            "ai_content", "model", fallback="claude-3-7-sonnet-latest"
        )
        self.max_tokens = config.getint("ai_content", "max_tokens", fallback=150)
        self.temperature = config.getfloat("ai_content", "temperature", fallback=0.7)
        self.ai_post_ratio = config.getfloat(
            "ai_content", "ai_post_ratio", fallback=0.3
        )
        self.testing_mode = config.getboolean(
            "ai_content", "testing_mode", fallback=False
        )

        # Initialize prompt manager
        prompts_dir = Path(
            config.get("ai_content", "prompts_directory", fallback="templates/prompts")
        )
        self.prompt_manager = PromptManager(prompts_dir)

        # For tracking when to reload prompts
        self.last_prompt_reload_time = time.time()
        self.prompt_reload_interval = 60  # Check for prompt changes every 60 seconds

        if self.testing_mode:
            logging.warning(
                f"🧪 TESTING MODE ENABLED: AI content generation will be used for ALL posts (100%)"
            )
        elif self.anthropic_api_key:
            logging.info(
                f"🤖 AI content enabled for {int(self.ai_post_ratio * 100)}% of posts using {self.model}"
            )

        # Load templates for non-AI posts
        self.templates = self._load_templates()

    def _check_prompt_reload(self):
        """Check if we should reload all prompt files based on time interval."""
        current_time = time.time()
        if current_time - self.last_prompt_reload_time > self.prompt_reload_interval:
            logging.debug(f"🔄 Checking for prompt file changes (periodic check)")
            self.prompt_manager.reload_all_prompts()
            self.last_prompt_reload_time = current_time

    def _load_templates(self):
        """Load post templates."""
        return {
            "standard": "🎵 Now Playing on Now Wave Radio:\n{artist} - {title}",
            "with_album": "🎵 Now Playing on Now Wave Radio:\n{artist} - {title}\nFrom the album: {album}",
            "nostalgic": "Taking you back to {year} with {artist}'s '{title}' on Now Wave Radio! 🎵 #ThrowbackTunes",
            "discovery": "Discover {artist} with their track '{title}' now playing on Now Wave Radio! 🎵 #NewMusicDiscovery",
            "dj_pick": "DJ Pick: {presenter} has selected {artist}'s '{title}' for your listening pleasure on {program}! 🎧",
        }

    async def generate_track_description(self, track: TrackInfo) -> str:
        """Generate an engaging description for a track.

        Args:
            track: TrackInfo object containing track information

        Returns:
            Generated description as string
        """
        # First try using built-in templates based on track attributes
        if track.presenter and track.program:
            template = self.templates["dj_pick"]
        elif track.year:
            # Handle both string and integer year values
            try:
                year_value = (
                    int(track.year) if isinstance(track.year, str) else track.year
                )
                if year_value < 2000:
                    template = self.templates["nostalgic"]
                else:
                    template = (
                        self.templates["with_album"]
                        if track.album
                        else self.templates["standard"]
                    )
            except (ValueError, TypeError):
                template = (
                    self.templates["with_album"]
                    if track.album
                    else self.templates["standard"]
                )
        elif track.album:
            template = self.templates["with_album"]
        else:
            template = self.templates["standard"]

        # Fill in the template
        description = template.format(
            artist=track.artist,
            title=track.title,
            album=track.album or "",
            year=track.year or "",
            presenter=track.presenter or "",
            program=track.program or "",
        )

        # Use AI if testing mode is enabled or random chance is below threshold
        if self.anthropic_api_key and (
            self.testing_mode or random.random() < self.ai_post_ratio
        ):
            if self.testing_mode:
                logging.debug(f"🧪 Using AI for post (testing mode enabled)")

            try:
                enhanced = await self._get_ai_enhanced_description(track)
                if enhanced:
                    return enhanced
            except Exception as e:
                logging.error(f"💥 Error generating AI description: {e}")

        return description

    async def _get_ai_enhanced_description(self, track: TrackInfo) -> Optional[str]:
        """Generate an AI-enhanced description using Anthropic's Claude.

        Args:
            track: TrackInfo object containing track information

        Returns:
            AI-generated description or None if generation failed
        """
        try:
            # Check if we should reload all prompts (periodically)
            self._check_prompt_reload()

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
            prompt_template = self.prompt_manager.select_prompt(track_dict)

            # Format the prompt with track info
            prompt = self.prompt_manager.format_prompt(prompt_template, track_dict)

            logging.debug(f"🤖 Using AI prompt: {prompt[:100]}...")

            # Use Anthropic API
            async with aiohttp.ClientSession() as session:
                response = await self._call_claude_api(session, prompt)

                if response and response.get("content"):
                    for content_block in response["content"]:
                        if content_block.get("type") == "text":
                            generated_text = content_block.get("text", "").strip()
                            logging.debug(
                                f"🤖 Generated AI text ({len(generated_text)} chars): {generated_text[:100]}..."
                            )
                            return generated_text

                return None
        except Exception as e:
            logging.error(f"💥 Error in AI description generation: {e}")
            return None

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

        # Use a smaller max_tokens value for Bluesky posts to ensure we stay within character limits
        ai_max_tokens = min(
            self.max_tokens, 100
        )  # 100 tokens is approximately 75-100 words

        data = {
            "model": self.model,
            "max_tokens": ai_max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }

        try:
            async with session.post(api_url, headers=headers, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logging.error(
                        f"💥 Claude API error ({response.status}): {error_text}"
                    )
                    return None
        except Exception as e:
            logging.error(f"💥 Claude API call failed: {e}")
            return None

    def generate_hashtags(self, track: TrackInfo) -> str:
        """Generate relevant hashtags for the track.

        Args:
            track: TrackInfo object containing track information

        Returns:
            String containing hashtags
        """
        hashtags = ["#NowWaveRadio"]

        # Add program hashtag if available
        if track.program:
            program_hashtag = "#" + "".join(
                word.capitalize() for word in track.program.split()
            )
            hashtags.append(program_hashtag)

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
