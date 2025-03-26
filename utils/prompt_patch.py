"""
Patched prompt manager for the test prompt utility.
This adds support for simulating different times of day.
"""

import time
from typing import Dict, Tuple
from pathlib import Path

from myrcat.managers.prompt import PromptManager


class PatchedPromptManager(PromptManager):
    """Patched prompt manager with time simulation support."""
    
    def __init__(self, prompts_dir: Path, simulated_hour: int = None):
        """Initialize the prompt manager with optional time simulation.
        
        Args:
            prompts_dir: Directory containing prompt templates
            simulated_hour: Optional hour (0-23) to simulate for time-based prompts
        """
        super().__init__(prompts_dir)
        self.simulated_hour = simulated_hour
        if simulated_hour is not None:
            # Ensure hour is in valid range
            self.simulated_hour = max(0, min(23, simulated_hour))
    
    def select_prompt(self, track_info: Dict) -> Tuple[str, str]:
        """Select the appropriate prompt based on track info and simulated time.
        
        This overrides the parent class method to use simulated time if provided.
        
        Args:
            track_info: Dictionary with track information
            
        Returns:
            Tuple of (selected prompt content, prompt name)
        """
        # Track which prompt was selected (for testing and logging)
        self.selected_prompt_name = "unknown"
        
        # Selection reason tracking for better debugging
        self.selection_reason = "unknown"
        
        # First priority: Select a show-specific prompt if available
        if track_info.get("program"):
            # Convert program name to a valid filename (lowercase, underscores)
            program_name = track_info["program"].lower().replace(" ", "_")
            show_prompt = self.get_prompt(program_name)
            if show_prompt:
                self.selected_prompt_name = program_name
                self.selection_reason = "program_specific"
                return show_prompt, program_name

        # Try time-of-day based prompts - check each one before falling back
        # Use simulated hour if set, otherwise use current time
        if self.simulated_hour is not None:
            current_hour = self.simulated_hour
        else:
            current_hour = time.localtime().tm_hour
        
        # Store time segment for debugging
        if 5 <= current_hour < 10:
            self.time_segment = "morning"
        elif 10 <= current_hour < 15:
            self.time_segment = "daytime"
        elif 15 <= current_hour < 19:
            self.time_segment = "afternoon"
        elif 19 <= current_hour < 23:
            self.time_segment = "evening"
        else:
            self.time_segment = "late_night"
            
        # Morning (5 AM - 10 AM)
        if 5 <= current_hour < 10:
            prompt_file = "morning"
            morning_prompt = self.get_prompt(prompt_file)
            if morning_prompt:
                self.selected_prompt_name = prompt_file
                self.selection_reason = "time_based"
                return morning_prompt, prompt_file
                
        # Daytime (10 AM - 3 PM)
        elif 10 <= current_hour < 15:
            prompt_file = "daytime"
            daytime_prompt = self.get_prompt(prompt_file)
            if daytime_prompt:
                self.selected_prompt_name = prompt_file
                self.selection_reason = "time_based"
                return daytime_prompt, prompt_file
                
        # Afternoon (3 PM - 7 PM)
        elif 15 <= current_hour < 19:
            prompt_file = "afternoon"
            afternoon_prompt = self.get_prompt(prompt_file)
            if afternoon_prompt:
                self.selected_prompt_name = prompt_file
                self.selection_reason = "time_based"
                return afternoon_prompt, prompt_file
                
        # Evening (7 PM - 11 PM)
        elif 19 <= current_hour < 23:
            prompt_file = "evening"
            evening_prompt = self.get_prompt(prompt_file)
            if evening_prompt:
                self.selected_prompt_name = prompt_file
                self.selection_reason = "time_based"
                return evening_prompt, prompt_file
                
        # Late Night (11 PM - 5 AM)
        else:
            prompt_file = "late_night"
            late_night_prompt = self.get_prompt(prompt_file)
            if late_night_prompt:
                self.selected_prompt_name = prompt_file
                self.selection_reason = "time_based"
                return late_night_prompt, prompt_file

        # Fall back to default prompt
        default_prompt = self.get_prompt("default")
        if default_prompt:
            self.selected_prompt_name = "default"
            self.selection_reason = "default_fallback"
            return default_prompt, "default"

        # If everything fails, return a minimal prompt
        self.selected_prompt_name = "minimal_fallback"
        self.selection_reason = "minimal_fallback"
        return ("""Create a short post about this song playing on Now Wave Radio.

Song: "{title}" by {artist}"

Must be under 200 characters.""", "minimal_fallback")