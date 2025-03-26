"""
Patched content generator for the test prompt utility.
This adds token usage and cost tracking to the content generator.
"""

import logging
from typing import Dict, Optional, Any, Tuple
import aiohttp
import json

from myrcat.models import TrackInfo
from myrcat.managers.content import ContentGenerator
from utils.prompt_patch import PatchedPromptManager


class PatchedContentGenerator(ContentGenerator):
    """Patched content generator with token usage and cost tracking."""
    
    def __init__(self, config):
        """Initialize with configuration.
        
        Args:
            config: ConfigParser object with configuration
        """
        super().__init__(config)
        
        # Check for simulated hour in config
        simulated_hour = None
        if config.has_section("test_options") and "simulated_hour" in config["test_options"]:
            try:
                simulated_hour = config.getint("test_options", "simulated_hour")
            except (ValueError, TypeError):
                pass
        
        # Replace prompt manager with our patched version if we have a simulated hour
        if simulated_hour is not None:
            self.prompt_manager = PatchedPromptManager(self.prompt_manager.prompts_dir, simulated_hour)
    
    async def _get_ai_enhanced_description(self, track: TrackInfo) -> tuple[Optional[str], dict]:
        """Generate an AI-enhanced description using Anthropic's Claude.
        
        This is a patched version that captures token usage information.

        Args:
            track: TrackInfo object containing track information

        Returns:
            Tuple of (AI-generated description or None if generation failed, 
                     metadata dict with prompt info and token usage)
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
            prompt_template, selected_prompt_name = self.prompt_manager.select_prompt(track_dict)
            prompt_name = selected_prompt_name
            metadata["prompt_name"] = prompt_name

            # Format the prompt with track info
            prompt = self.prompt_manager.format_prompt(prompt_template, track_dict)
            
            # Store model from configuration in metadata
            metadata["model"] = self.model
            
            # Store raw prompt for token estimation if needed
            metadata["prompt_raw"] = prompt

            # Use Anthropic API
            async with aiohttp.ClientSession() as session:
                response = await self._call_claude_api(session, prompt)

                if response:
                    try:
                        # Only update model from response if it's present explicitly
                        # Otherwise keep the model we set from config
                        if isinstance(response, dict) and "model" in response:
                            metadata["model"] = response["model"]
                        elif hasattr(response, "model") and response.model:
                            metadata["model"] = response.model
                        
                        # Try to extract usage data from various possible formats
                        # 1. Dictionary with usage key
                        if isinstance(response, dict) and "usage" in response:
                            if isinstance(response["usage"], dict):
                                metadata["input_tokens"] = response["usage"].get("input_tokens", 0)
                                metadata["output_tokens"] = response["usage"].get("output_tokens", 0)
                        
                        # 2. Object with usage attribute
                        elif hasattr(response, "usage"):
                            usage = response.usage
                            if hasattr(usage, "input_tokens"):
                                metadata["input_tokens"] = usage.input_tokens
                                metadata["output_tokens"] = usage.output_tokens
                            elif isinstance(usage, dict):
                                metadata["input_tokens"] = usage.get("input_tokens", 0)
                                metadata["output_tokens"] = usage.get("output_tokens", 0)
                        
                        # 3. Direct token counts on the response
                        elif isinstance(response, dict) and "input_tokens" in response:
                            metadata["input_tokens"] = response.get("input_tokens", 0)
                            metadata["output_tokens"] = response.get("output_tokens", 0)
                            
                        # Extract content - handle different formats
                        generated_text = None
                        
                        # 1. Dictionary with content list
                        if isinstance(response, dict) and "content" in response:
                            for content_block in response["content"]:
                                if content_block.get("type") == "text":
                                    generated_text = content_block.get("text", "").strip()
                                    break
                        
                        # 2. Object with content attribute and message format
                        elif hasattr(response, "content") and response.content:
                            # Usually a string or list
                            if isinstance(response.content, str):
                                generated_text = response.content.strip()
                            elif isinstance(response.content, list):
                                for block in response.content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        generated_text = block.get("text", "").strip()
                                        break
                            
                        # 3. Try direct text attribute
                        elif hasattr(response, "text"):
                            generated_text = response.text.strip()
                        
                        # If content was found, return it
                        if generated_text:
                            # Add debugging information about token extraction
                            metadata["token_source"] = "successfully extracted" 
                            return generated_text, metadata
                    except Exception as extract_err:
                        # If there's an error extracting data, add it to metadata but continue
                        metadata["extraction_error"] = str(extract_err)
                    
                    # Fallback - try basic content extraction if the above failed
                    try:
                        if isinstance(response, dict) and "content" in response:
                            for content_block in response["content"]:
                                if content_block.get("type") == "text":
                                    generated_text = content_block.get("text", "").strip()
                                    # Mark as fallback extraction
                                    metadata["token_source"] = "fallback extraction"
                                    return generated_text, metadata
                    except:
                        pass

                return None, metadata
        except Exception as e:
            # No logging, let it bubble up
            return None, metadata