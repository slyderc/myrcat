"""Prompt manager for AI content generation."""

import os
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Union


class PromptManager:
    """Manages prompt templates for AI content generation."""

    def __init__(self, prompts_dir: Union[str, Path]):
        """Initialize the prompt manager.

        Args:
            prompts_dir: Directory containing prompt templates
        """
        self.prompts_dir = Path(prompts_dir)
        self.prompts = {}
        self.file_mtimes = {}  # Stores file modification times

        # Create directory if it doesn't exist
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        # If no default prompt exists, create one
        default_path = self.prompts_dir / "default.txt"
        if not default_path.exists():
            self._create_default_prompt(default_path)

        # Load all prompts
        self.load_all_prompts()

    def _create_default_prompt(self, path: Path) -> None:
        """Create a default prompt file if none exists.

        Args:
            path: Path to create the default prompt at
        """
        default_content = """Create a SHORT, engaging social media post about a song playing on a radio station.

Song: "{title}" by {artist}
Album: {album}
Year: {year}
Show: {program}
Presenter: {presenter}

IMPORTANT RESTRICTIONS:
- MUST be under 200 characters total (this is critical)
- Feel conversational and include 1-2 emojis only
- Mention "Now Wave Radio"
- NEVER include hashtags - they will be added separately
- Focus on being concise yet engaging"""

        try:
            with open(path, "w") as f:
                f.write(default_content)
            logging.info(f"📝 Created default prompt template at {path}")
        except Exception as e:
            logging.error(f"💥 Error creating default prompt: {e}")

    def load_all_prompts(self) -> None:
        """Load all prompt templates from the prompts directory."""
        try:
            prompt_files = list(self.prompts_dir.glob("*.txt"))
            if not prompt_files:
                logging.warning(f"⚠️ No prompt templates found in {self.prompts_dir}")
                return

            loaded_count = 0
            for file_path in prompt_files:
                try:
                    self.load_prompt(file_path.stem)
                    loaded_count += 1
                except Exception as e:
                    logging.error(f"💥 Error loading prompt {file_path.name}: {e}")

            logging.info(
                f"📝 Loaded {loaded_count} prompt templates from {self.prompts_dir}"
            )
        except Exception as e:
            logging.error(f"💥 Error loading prompt templates: {e}")
            

    def load_prompt(self, name: str) -> bool:
        """Load a specific prompt template.

        Args:
            name: Name of the prompt template (without .txt extension)

        Returns:
            True if prompt was loaded successfully, False otherwise
        """
        file_path = self.prompts_dir / f"{name}.txt"
        if not file_path.exists():
            logging.warning(f"⚠️ Prompt template not found: {file_path}")
            return False

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Store the prompt content
            self.prompts[name] = content

            # Store the file modification time
            self.file_mtimes[name] = os.path.getmtime(file_path)

            logging.debug(f"📝 Loaded prompt template: {name}")
            return True
        except Exception as e:
            logging.error(f"💥 Error loading prompt {name}: {e}")
            return False

    def get_prompt(
        self, name: str = "default"
    ) -> Optional[str]:
        """Get a prompt template by name, always checking for modifications.

        Args:
            name: Name of the prompt template

        Returns:
            Prompt template content or None if not found
        """
        file_path = self.prompts_dir / f"{name}.txt"
        
        # Always check if the file has been modified if it's already loaded
        if name in self.prompts:
            reloaded = self._check_and_reload_if_modified(name)
            if reloaded:
                logging.debug(f"📝 Reloaded modified prompt: {name}.txt")
            
        # If prompt is not loaded, try to load it
        if name not in self.prompts:
            if file_path.exists():
                # File exists but not loaded yet
                if self.load_prompt(name):
                    logging.debug(f"📝 Loaded prompt from file: {name}.txt")
                    return self.prompts.get(name)
            else:
                # File doesn't exist
                logging.debug(f"📝 Prompt file not found: {name}.txt")
                # Fall back to default prompt if the requested one doesn't exist
                if name != "default" and "default" in self.prompts:
                    logging.debug(f"📝 Falling back to default prompt")
                    return self.prompts["default"]
                return None
                
        return self.prompts.get(name)

    def _check_and_reload_if_modified(self, name: str) -> bool:
        """Check if a prompt file has been modified and reload it if necessary.

        Args:
            name: Name of the prompt template

        Returns:
            True if the prompt was reloaded, False otherwise
        """
        try:
            file_path = self.prompts_dir / f"{name}.txt"
            if not file_path.exists():
                logging.debug(f"📝 File no longer exists: {file_path}")
                # Remove from prompts if it was previously loaded
                if name in self.prompts:
                    del self.prompts[name]
                    logging.info(f"📝 Removed prompt that no longer exists: {name}")
                return False

            # Force stat refresh to get the current modification time
            file_path.stat()  # This refreshes file stats from the filesystem
            current_mtime = os.path.getmtime(file_path)
            stored_mtime = self.file_mtimes.get(name, 0)

            logging.debug(f"📝 Checking prompt file: {name}.txt (Current mtime: {current_mtime}, Stored mtime: {stored_mtime})")

            if current_mtime > stored_mtime:
                # File has been modified
                logging.warning(f"🔄 Prompt file changed, reloading: {name}.txt")
                
                # Read file content directly to verify it's accessible
                try:
                    with open(file_path, 'r') as f:
                        new_content = f.read()
                        content_preview = new_content[:50] + "..." if len(new_content) > 50 else new_content
                        logging.debug(f"📝 New content preview: {content_preview}")
                except Exception as read_error:
                    logging.error(f"💥 Error reading modified prompt file: {read_error}")
                    return False
                
                # Reload the prompt
                reload_success = self.load_prompt(name)
                if reload_success:
                    logging.info(f"✅ Successfully reloaded prompt: {name}.txt")
                else:
                    logging.error(f"❌ Failed to reload prompt: {name}.txt")
                return reload_success
            else:
                # File hasn't changed
                logging.debug(f"📝 Prompt file unchanged: {name}.txt")
                return False
                
        except Exception as e:
            logging.error(f"💥 Error checking prompt modification: {e}")
            logging.error(f"💥 Error details: {type(e).__name__}: {str(e)}")
            return False

    def select_prompt(self, track_info: Dict) -> tuple[str, str]:
        """Select the appropriate prompt based on track info.

        Args:
            track_info: Dictionary with track information

        Returns:
            Tuple of (selected prompt content, prompt name)
        """
        # This is where we can implement logic to select different prompts based on
        # show name, time of day, genre, etc.

        # Example: Select a show-specific prompt if available
        if track_info.get("program"):
            # Convert program name to a valid filename (lowercase, underscores)
            program_name = track_info["program"].lower().replace(" ", "_")
            show_prompt = self.get_prompt(program_name)
            if show_prompt:
                return show_prompt, program_name

        # Try time-of-day based prompts - check each one before falling back
        current_hour = time.localtime().tm_hour
        
        # Morning (5 AM - 10 AM)
        if 5 <= current_hour < 10:
            prompt_file = "morning"
            logging.debug(f"📝 Checking for time-based prompt: {prompt_file}.txt")
            morning_prompt = self.get_prompt(prompt_file)
            if morning_prompt:
                logging.debug(f"📝 Using time-based prompt: {prompt_file}.txt")
                return morning_prompt, prompt_file
                
        # Daytime (10 AM - 3 PM)
        elif 10 <= current_hour < 15:
            prompt_file = "daytime"
            logging.debug(f"📝 Checking for time-based prompt: {prompt_file}.txt")
            daytime_prompt = self.get_prompt(prompt_file)
            if daytime_prompt:
                logging.debug(f"📝 Using time-based prompt: {prompt_file}.txt")
                return daytime_prompt, prompt_file
                
        # Afternoon (3 PM - 7 PM)
        elif 15 <= current_hour < 19:
            prompt_file = "afternoon"
            logging.debug(f"📝 Checking for time-based prompt: {prompt_file}.txt")
            afternoon_prompt = self.get_prompt(prompt_file)
            if afternoon_prompt:
                logging.debug(f"📝 Using time-based prompt: {prompt_file}.txt")
                return afternoon_prompt, prompt_file
                
        # Evening (7 PM - 11 PM)
        elif 19 <= current_hour < 23:
            prompt_file = "evening"
            logging.debug(f"📝 Checking for time-based prompt: {prompt_file}.txt")
            evening_prompt = self.get_prompt(prompt_file)
            if evening_prompt:
                logging.debug(f"📝 Using time-based prompt: {prompt_file}.txt")
                return evening_prompt, prompt_file
                
        # Late Night (11 PM - 5 AM)
        else:
            prompt_file = "late_night"
            logging.debug(f"📝 Checking for time-based prompt: {prompt_file}.txt")
            late_night_prompt = self.get_prompt(prompt_file)
            if late_night_prompt:
                logging.debug(f"📝 Using time-based prompt: {prompt_file}.txt")
                return late_night_prompt, prompt_file

        # Fall back to default prompt
        default_prompt = self.get_prompt("default")
        if default_prompt:
            return default_prompt, "default"

        # If everything fails, return a minimal prompt
        return ("""Create a short post about this song playing on Now Wave Radio.

Song: "{title}" by {artist}"

Must be under 200 characters.""", "minimal_fallback")

    def format_prompt(self, prompt_template: str, track_info: Dict) -> str:
        """Format a prompt template with track information.

        Args:
            prompt_template: Prompt template string
            track_info: Dictionary with track information

        Returns:
            Formatted prompt
        """
        try:
            # Create a dictionary with default values for all possible fields
            template_values = {
                "title": track_info.get("title", "(Unknown Title)"),
                "artist": track_info.get("artist", "(Unknown Artist)"),
                "album": track_info.get("album", "(Unknown)"),
                "year": track_info.get("year", "(Unknown)"),
                "program": track_info.get("program", "Now Wave Mix"),
                "presenter": track_info.get("presenter", "(Unknown DJ)"),
            }

            # Format the prompt template
            return prompt_template.format(**template_values)
        except Exception as e:
            logging.error(f"💥 Error formatting prompt: {e}")
            # Return a simple fallback prompt
            return f"Create a short post about {track_info.get('title', 'this song')} by {track_info.get('artist', 'this artist')} playing on Now Wave Radio."
