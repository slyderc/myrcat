#!/usr/bin/env python3

"""
Test script to verify day-of-week formatting in prompt templates.
This minimal script avoids importing unnecessary modules.
"""

import sys
import os
import time
from pathlib import Path

# Setup test directories
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates/prompts")

# Create a simple mock prompt manager that just does the formatting
class SimplePromptManager:
    def format_prompt(self, prompt_template, track_info):
        # Get current day of the week
        current_dow = time.strftime("%A")  # Full day name (e.g., "Monday")
        
        # Create a dictionary with default values for all possible fields
        template_values = {
            "title": track_info.get("title", "(Unknown Title)"),
            "artist": track_info.get("artist", "(Unknown Artist)"),
            "album": track_info.get("album", "(Unknown)"),
            "year": track_info.get("year", "(Unknown)"),
            "program": track_info.get("program", "Now Wave Mix"),
            "presenter": track_info.get("presenter", "(Unknown DJ)"),
            "dow": current_dow,  # Add day of week support
        }

        # Format the prompt template
        return prompt_template.format(**template_values)

def main():
    # Get today's day of the week
    current_dow = time.strftime("%A")
    print(f"Current day of the week: {current_dow}")
    
    # Create simple prompt manager
    prompt_manager = SimplePromptManager()
    
    # Test track info
    track_info = {
        "title": "Test Title",
        "artist": "Test Artist",
        "album": "Test Album",
        "year": "2023",
        "program": "Test Program",
        "presenter": "Test Presenter",
    }
    
    # Test with a sample template string that includes {dow}
    test_prompt = "Today is {dow}. Now playing on Now Wave Radio: {title} by {artist} from {album} ({year})"
    
    print("\nTemplate prompt:")
    print(test_prompt)
    
    print("\nFormatted prompt:")
    formatted_prompt = prompt_manager.format_prompt(test_prompt, track_info)
    print(formatted_prompt)
    
    # Check if the day of week was properly replaced
    if current_dow in formatted_prompt:
        print(f"\n✅ SUCCESS: Found '{current_dow}' in the formatted prompt")
    else:
        print(f"\n❌ ERROR: Did not find '{current_dow}' in the formatted prompt")

    # Try with a real template file if it exists
    flashback_path = os.path.join(TEMPLATE_DIR, "flashback.txt")
    if os.path.exists(flashback_path):
        print("\n\nTesting with actual flashback.txt template:")
        with open(flashback_path, 'r') as f:
            flashback_template = f.read()
            
        formatted_flashback = prompt_manager.format_prompt(flashback_template, track_info)
        print("\nFormatted flashback template (first 300 characters):")
        print(formatted_flashback[:300])
        
        if current_dow in formatted_flashback:
            print(f"\n✅ SUCCESS: Found '{current_dow}' in the formatted flashback template")
        else:
            print(f"\n❌ ERROR: Did not find '{current_dow}' in the formatted flashback template")

if __name__ == "__main__":
    main()