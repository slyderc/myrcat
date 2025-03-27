#!/usr/bin/env python3
"""
Test AI prompts for social media posts without posting to social platforms.

This utility allows testing how different track metadata and prompts generate
social media posts, helping to refine prompt templates for better results.

Usage:
    ./testprompt.py -c config.ini
"""

import sys
import os
import argparse
import configparser
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

# Add parent directory to path to import myrcat modules
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))

from myrcat.models import TrackInfo
from myrcat.managers.content import ContentGenerator
from myrcat.managers.social_media import SocialMediaManager

# Import our patched content generator if it exists
try:
    from utils.content_patch import PatchedContentGenerator
    USE_PATCHED_GENERATOR = True
except ImportError:
    USE_PATCHED_GENERATOR = False


def setup_logging():
    """Configure logging for the utility.
    
    This completely disables logging to keep the terminal clean for 
    the utility's own formatted output.
    """
    # Set highest level to effectively disable logging
    logging.basicConfig(
        level=logging.CRITICAL + 1,  # Above CRITICAL to disable all logging
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.NullHandler()],  # Don't output anywhere
    )
    
    # Disable all other loggers that might be noisy
    for logger_name in [
        'root', 'httpx', 'httpcore', 'urllib3', 'aiohttp', 'asyncio',
        'myrcat', 'myrcat.managers', 'myrcat.managers.content'
    ]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL + 1)
        logger.addHandler(logging.NullHandler())
        logger.propagate = False


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test AI prompts for social media posts")
    parser.add_argument(
        "-c", "--config", 
        required=True, 
        help="Path to configuration file"
    )
    return parser.parse_args()


def load_config(config_path: str) -> configparser.ConfigParser:
    """Load configuration from the specified file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        ConfigParser object with loaded configuration
    """
    config = configparser.ConfigParser()
    
    # Handle relative paths
    config_path_obj = Path(config_path)
    if not config_path_obj.is_absolute():
        # First try relative to current directory
        if not config_path_obj.exists():
            # Then try relative to script location
            config_path_obj = Path(__file__).parent / config_path_obj
    
    if not config_path_obj.exists():
        print(f"Error: Configuration file '{config_path}' not found.")
        sys.exit(1)
        
    try:
        config.read(str(config_path_obj))
        
        # Adjust paths to be absolute if they aren't already
        if "ai_content" in config and "prompts_directory" in config["ai_content"]:
            prompts_dir = Path(config["ai_content"]["prompts_directory"])
            
            # Don't try to create any directories or files, just use what's provided
            if not prompts_dir.is_absolute():
                # Check a few common locations
                possible_paths = [
                    prompts_dir,  # Relative to current directory
                    Path(__file__).parent / prompts_dir,  # Relative to script directory
                    parent_dir / prompts_dir,  # Relative to project root
                ]
                
                # Use the first path that exists
                for path in possible_paths:
                    if path.exists() and path.is_dir():
                        config["ai_content"]["prompts_directory"] = str(path)
                        break
                
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)


def create_track_info(config: configparser.ConfigParser) -> TrackInfo:
    """Create a TrackInfo object from configuration.
    
    Args:
        config: ConfigParser object with track information
        
    Returns:
        TrackInfo object with track data
    """
    if not config.has_section("track"):
        print("Error: Configuration file missing [track] section")
        sys.exit(1)
        
    track_config = config["track"]
    
    # Required fields
    required_fields = ["artist", "title"]
    for field in required_fields:
        if field not in track_config:
            print(f"Error: Missing required field '{field}' in [track] section")
            sys.exit(1)
    
    # Create TrackInfo with required and optional fields
    return TrackInfo(
        artist=track_config["artist"],
        title=track_config["title"],
        album=track_config.get("album", ""),
        year=track_config.get("year", ""),
        program=track_config.get("program", ""),
        presenter=track_config.get("presenter", ""),
        media_id="test123",
        type="Song",  # Default to Song type
        is_song=True, # Set is_song flag to true for testprompt
        starttime="2023-01-01T08:30:00",
        duration=180,
        image=None,
        publisher=track_config.get("publisher", ""),
        isrc=track_config.get("isrc", "")
    )


async def generate_sample_post(config: configparser.ConfigParser, track: TrackInfo, model_from_config: str = None) -> Tuple[str, Dict, Optional[Union[ContentGenerator, 'PatchedContentGenerator']]]:
    """Generate a sample post using the ContentGenerator.
    
    Args:
        config: ConfigParser object with AI configuration
        track: TrackInfo object with track data
        model_from_config: Model name from the configuration, as fallback
        
    Returns:
        Tuple of (generated post text, metadata dictionary, content generator instance)
    """
    # Use patched generator if available, otherwise use the standard one
    if USE_PATCHED_GENERATOR:
        content_generator = PatchedContentGenerator(config)
    else:
        content_generator = ContentGenerator(config)
        # Print warning only when we might expect costs
        if config.get("ai_content", "anthropic_api_key", fallback="") not in ["", "YOUR_API_KEY_HERE"]:
            print("\n⚠️  Token usage tracking not available. Install patched content generator for cost details.")
    
    # Model will be passed from the main function
    
    # Force AI content generation regardless of config
    original_testing_mode = config.getboolean("ai_content", "testing_mode", fallback=False)
    if "ai_content" not in config:
        config.add_section("ai_content")
    config["ai_content"]["testing_mode"] = "true"
    
    try:
        # Check for API key
        api_key = config.get("ai_content", "anthropic_api_key", fallback="")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            print("\n⚠️  Warning: Missing or invalid Anthropic API key")
            print("   Using fallback template instead of AI-generated content")
            print("   To use AI generation, set a valid anthropic_api_key in your config file")
            
            # Generate a template-based post as fallback
            fallback_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
            if track.album:
                fallback_text += f"\nFrom the album: {track.album}"
            
            metadata = {
                "source_type": "template",
                "template_name": "fallback",
                "prompt_name": None
            }
            
            # Add hashtags
            hashtags = content_generator.generate_hashtags(track, is_ai_content=False)
            if hashtags:
                fallback_text = fallback_text.strip() + f"\n\n{hashtags}"
                
            return fallback_text, metadata, content_generator
            
        # Generate the post
        try:
            # Set a shorter timeout for the API call to prevent long waits on overloaded servers
            if "ai_content" in config:
                original_timeout = config.get("ai_content", "api_timeout", fallback="30")
                config["ai_content"]["api_timeout"] = "15"  # 15 second timeout
            
            # Try with retries for overloaded API
            max_retries = 2
            retry_count = 0
            retry_delay = 2  # seconds
            last_error = None
            
            while retry_count <= max_retries:
                try:
                    if retry_count > 0:
                        print(f"   Retry attempt {retry_count}/{max_retries}...")
                        await asyncio.sleep(retry_delay)
                        # Increase delay for next retry
                        retry_delay *= 2
                        
                    post_text, metadata = await content_generator.generate_track_description(track)
                    # Success - break out of retry loop
                    break
                    
                except Exception as retry_error:
                    last_error = retry_error
                    error_str = str(retry_error).lower()
                    
                    # Only retry on overloaded errors
                    if "overloaded" in error_str:
                        retry_count += 1
                        if retry_count <= max_retries:
                            print(f"\n⚠️  Claude API overloaded. Will retry in {retry_delay} seconds...")
                        continue
                    else:
                        # Don't retry other types of errors
                        raise
            
            # If we exhausted all retries, raise the last error
            if retry_count > max_retries and last_error:
                raise last_error
                
            # Reset timeout if it was changed
            if "ai_content" in config and original_timeout:
                config["ai_content"]["api_timeout"] = original_timeout
                
        except Exception as e:
            error_message = str(e)
            print(f"\n❌ API Error: {error_message}")
            
            # Handle common errors
            if "overloaded" in error_message.lower():
                print("   Claude API is currently overloaded. Try again later.")
            elif "rate limit" in error_message.lower():
                print("   You've reached your API rate limit. Try again later.")
            elif "invalid api key" in error_message.lower():
                print("   Your API key appears to be invalid. Check your configuration.")
            else:
                print("   Failed to generate AI content. Using fallback template.")
            
            # Generate a template-based post as fallback
            fallback_text = f"🎵 Now Playing on Now Wave Radio:\n{track.artist} - {track.title}"
            if track.album:
                fallback_text += f"\nFrom the album: {track.album}"
            
            metadata = {
                "source_type": "template",
                "template_name": "fallback_after_error",
                "prompt_name": None,
                "error": error_message,
                "model": model_from_config  # Include model from config
            }
            
            # Add hashtags
            hashtags = content_generator.generate_hashtags(track, is_ai_content=False)
            if hashtags:
                fallback_text = fallback_text.strip() + f"\n\n{hashtags}"
                
            return fallback_text, metadata, content_generator
        
        # Generate additional hashtags
        is_ai_content = metadata.get("source_type") == "ai"
        hashtags = content_generator.generate_hashtags(track, is_ai_content=is_ai_content)
        
        # Handle hashtag merge as done in the SocialMediaManager
        if is_ai_content:
            # For AI-generated content, don't add system hashtags unless needed
            # The ContentGenerator handles this already
            pass
        else:
            # For template content, add hashtags
            if hashtags:
                if "\n\n" in post_text:
                    post_text = post_text.strip() + f"\n\n{hashtags}"
                else:
                    post_text = post_text.strip() + f"\n\n{hashtags}"
        
        # Ensure model is always set in metadata
        if model_from_config and (not metadata.get('model') or metadata.get('model') == 'unknown'):
            metadata['model'] = model_from_config
            
        return post_text, metadata, content_generator
    finally:
        # Restore original testing mode setting
        if original_testing_mode is not None:
            config["ai_content"]["testing_mode"] = str(original_testing_mode).lower()


async def process_post_for_display(text: str, config: configparser.ConfigParser) -> str:
    """Process the post for display, handling hashtags as the SocialMediaManager would.
    
    Args:
        text: The post text to process
        config: Configuration settings
        
    Returns:
        Processed text ready for display
    """
    # This is a simplified version of the social media manager's hashtag handling
    # For demonstration purposes, we're just formatting the text for display
    
    # Check post length for platform limitations (e.g., 300 chars for Bluesky)
    if len(text) > 300:
        print(f"\n⚠️  Warning: Post exceeds 300 characters ({len(text)} chars)")
        print("    This would be trimmed for platforms like Bluesky")
    
    # Extract hashtags for display
    hashtags = []
    if "\n\n#" in text:
        main_content, hashtag_section = text.split("\n\n#", 1)
        hashtag_section = "#" + hashtag_section
        hashtags = hashtag_section.split()
    
    # Return the same text, but we've extracted info for display
    return text, hashtags


async def main():
    """Main entry point for the script."""
    setup_logging()
    args = parse_arguments()
    
    config = load_config(args.config)
    track = create_track_info(config)
    
    print("\n" + "=" * 80)
    print(f"Test Prompt Utility - Sample Post Generator")
    print("=" * 80)
    
    print(f"\n📋 Track Information:")
    print(f"   Artist:    {track.artist}")
    print(f"   Title:     {track.title}")
    if track.album:
        print(f"   Album:     {track.album}")
    if track.year:
        print(f"   Year:      {track.year}")
    if track.program:
        print(f"   Program:   {track.program}")
    if track.presenter:
        print(f"   Presenter: {track.presenter}")
    
    try:
        # Get model from config for use in display and estimation
        model_from_config = config.get("ai_content", "model", fallback="claude-3-sonnet-20240229")
        
        # Check for simulated time
        simulated_hour = None
        if config.has_section("test_options") and "simulated_hour" in config["test_options"]:
            try:
                simulated_hour = config.getint("test_options", "simulated_hour")
                # Ensure it's in valid range
                simulated_hour = max(0, min(23, simulated_hour))
                
                # Map the hour to a time segment for display
                if 5 <= simulated_hour < 10:
                    time_segment = "morning"
                elif 10 <= simulated_hour < 15:
                    time_segment = "daytime"
                elif 15 <= simulated_hour < 19:
                    time_segment = "afternoon"
                elif 19 <= simulated_hour < 23:
                    time_segment = "evening"
                else:
                    time_segment = "late night"
                
                print(f"\n⏰ Time Simulation:")
                print(f"   Hour: {simulated_hour:02d}:00 ({time_segment} prompt)")
            except (ValueError, TypeError):
                pass
        
        # Get prompt directory information
        prompts_dir = config["ai_content"].get("prompts_directory", "unknown")
        prompts_dir_path = Path(prompts_dir)
        available_prompts = []
        
        print(f"\n📂 Prompt Directory:")
        print(f"   Path: {prompts_dir}")
        
        if not prompts_dir_path.exists():
            print(f"   ⚠️  Directory does not exist!")
            print(f"   Prompts will not work until this directory is created.")
        elif not prompts_dir_path.is_dir():
            print(f"   ⚠️  Not a directory!")
        else:
            # Directory exists, check if it has prompt files
            available_prompts = [p.stem for p in prompts_dir_path.glob("*.txt")]
            if available_prompts:
                print(f"   Available prompts: {', '.join(available_prompts)}")
            else:
                print(f"   ⚠️  No prompt files found! Create at least one .txt file in this directory.")
        
        post_text, metadata, content_generator = await generate_sample_post(config, track, model_from_config)
        processed_text, hashtags = await process_post_for_display(post_text, config)
        
        print("\n🤖 AI Generation Information:")
        print(f"   Source:  {metadata.get('source_type', 'unknown')}")
        if metadata.get('source_type') == 'ai':
            prompt_name = metadata.get('prompt_name', 'unknown')
            print(f"   Prompt:  {prompt_name}")
            
            # Show selection reason if available
            if hasattr(content_generator.prompt_manager, 'selection_reason'):
                reason = content_generator.prompt_manager.selection_reason
                if reason == "program_specific":
                    print(f"   Selected: Based on program name (highest priority)")
                elif reason == "time_based":
                    time_segment = getattr(content_generator.prompt_manager, 'time_segment', None)
                    if time_segment:
                        print(f"   Selected: Based on time of day - {time_segment} (medium priority)")
                    else:
                        print(f"   Selected: Based on time of day (medium priority)")
                elif reason == "default_fallback":
                    print(f"   Selected: Default prompt (fallback)")
                elif reason == "minimal_fallback":
                    print(f"   Selected: Built-in minimal template (last resort)")
                else:
                    print(f"   Selected: {reason}")
            
            # Display usage and cost information if available
            input_tokens = metadata.get('input_tokens', 0)
            output_tokens = metadata.get('output_tokens', 0)
            total_tokens = input_tokens + output_tokens
            
            # Show model information - prefer what's in metadata, fall back to config
            model_name = metadata.get('model', model_from_config)
            if model_name == 'unknown' or not model_name:
                model_name = model_from_config
            print(f"   Model:   {model_name}")
            
            if total_tokens > 0:
                # Get model name (lowercase for comparison)
                model = model_name.lower()
                
                # Set pricing based on the model (as of April 2024)
                # https://www.anthropic.com/api/pricing
                if "claude-3-opus" in model:
                    input_rate = 0.000015  # $15 per million input tokens
                    output_rate = 0.000075  # $75 per million output tokens
                elif "claude-3-sonnet" in model:
                    input_rate = 0.000003  # $3 per million input tokens
                    output_rate = 0.000015  # $15 per million output tokens
                elif "claude-3-haiku" in model:
                    input_rate = 0.00000025  # $0.25 per million input tokens
                    output_rate = 0.00000125  # $1.25 per million output tokens
                elif "claude-2" in model or "claude-2.1" in model:
                    input_rate = 0.000008  # $8 per million input tokens
                    output_rate = 0.000024  # $24 per million output tokens
                elif "claude-instant" in model:
                    input_rate = 0.0000008  # $0.80 per million input tokens
                    output_rate = 0.0000024  # $2.40 per million output tokens
                else:
                    # Default to Sonnet pricing if model is unknown
                    input_rate = 0.000003  # $3 per million input tokens
                    output_rate = 0.000015  # $15 per million output tokens
                
                input_cost = input_tokens * input_rate
                output_cost = output_tokens * output_rate
                total_cost = input_cost + output_cost
                
                print(f"   Tokens:  {input_tokens} input + {output_tokens} output = {total_tokens} total")
                print(f"   Cost:    ${total_cost:.4f} (${input_cost:.4f} input + ${output_cost:.4f} output)")
                
                # Add source information if available (for debugging)
                if 'token_source' in metadata:
                    source = metadata['token_source']
                    if source != "successfully extracted":
                        print(f"   Note:    Token information via {source}")
            else:
                # No token information available - explain why
                if 'extraction_error' in metadata:
                    print(f"   Tokens:  Information not available")
                    print(f"   Note:    Unable to extract token usage from API response")
                elif USE_PATCHED_GENERATOR:
                    # Provide estimated token counts based on rules of thumb
                    # Typically, 1 token ≈ 4 characters for English text
                    prompt_length = len(metadata.get('prompt_raw', ''))
                    response_length = len(processed_text)
                    
                    est_input_tokens = max(1, round(prompt_length / 4))
                    est_output_tokens = max(1, round(response_length / 4))
                    
                    # Use model from config if metadata one is unknown
                    if model_name == 'unknown' or not model_name:
                        model_name = model_from_config
                    
                    # Estimate costs - get model name (lowercase for comparison)
                    model = model_name.lower()
                    
                    # Set pricing based on the model
                    if "claude-3-opus" in model:
                        input_rate = 0.000015  # $15 per million input tokens
                        output_rate = 0.000075  # $75 per million output tokens
                    elif "claude-3-sonnet" in model:
                        input_rate = 0.000003  # $3 per million input tokens
                        output_rate = 0.000015  # $15 per million output tokens
                    elif "claude-3-haiku" in model:
                        input_rate = 0.00000025  # $0.25 per million input tokens
                        output_rate = 0.00000125  # $1.25 per million output tokens
                    else:
                        # Default to Sonnet pricing
                        input_rate = 0.000003  # $3 per million input tokens
                        output_rate = 0.000015  # $15 per million output tokens
                    
                    est_input_cost = est_input_tokens * input_rate
                    est_output_cost = est_output_tokens * output_rate
                    est_total_cost = est_input_cost + est_output_cost
                    
                    print(f"   Tokens:  ~{est_input_tokens} input + ~{est_output_tokens} output = ~{est_input_tokens + est_output_tokens} total (estimated)")
                    print(f"   Cost:    ~${est_total_cost:.4f} (estimated)")
                    print(f"   Note:    API didn't provide token data, these are rough estimates based on text length")
                else:
                    print(f"   Tokens:  Information not available")
                    print(f"   Note:    Enable patched content generator for token tracking")
        else:
            print(f"   Template: {metadata.get('template_name', 'unknown')}")
            if metadata.get('error'):
                print(f"   Error:   API error occurred - using fallback template")
        
        print("\n📝 Generated Post:")
        print("-" * 80)
        print(processed_text)
        print("-" * 80)
        
        # Print some additional stats
        char_count = len(processed_text)
        word_count = len(processed_text.split())
        hashtag_count = len(hashtags)
        
        print(f"\n📊 Post Statistics:")
        print(f"   Character count: {char_count}/300 ({'✅ OK' if char_count <= 300 else '⚠️ TOO LONG'})")
        print(f"   Word count:      {word_count}")
        print(f"   Hashtags:        {hashtag_count}")
        
        if hashtags:
            print(f"\n🔖 Extracted Hashtags:")
            for hashtag in hashtags:
                print(f"   {hashtag}")
        
    except Exception as e:
        error_message = str(e)
        print(f"\n❌ Error: {error_message}")
        
        # No logging, just show error on console
        
        # Give more helpful information based on error type
        if "api key" in error_message.lower():
            print("\nPlease check your API key in the configuration file.")
            print("You can still use the utility without an API key, but it will")
            print("fall back to template-based posts instead of AI generation.")
        elif "connection" in error_message.lower() or "timeout" in error_message.lower():
            print("\nThere was a network connection issue. Please check your internet connection.")
        elif "file" in error_message.lower() and "not found" in error_message.lower():
            print("\nA required file was not found. Please check your configuration paths.")
        
        # Show full traceback for debugging purposes
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())