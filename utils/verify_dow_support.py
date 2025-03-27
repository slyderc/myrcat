#!/usr/bin/env python3

"""
Verify Day of Week support in prompts.

This script confirms that the {dow} placeholder in prompt templates
is correctly replaced with the current day of the week.
"""

import os
import sys
import time
from pathlib import Path

# Simple standalone implementation to test the {dow} replacement
class SimplePromptTester:
    """Simple tester for prompt format replacement."""
    
    def __init__(self, prompts_dir):
        """Initialize with prompts directory."""
        self.prompts_dir = Path(prompts_dir)
        
    def get_prompt_files(self):
        """Get all prompt template files."""
        return list(self.prompts_dir.glob("*.txt"))
    
    def read_prompt(self, template_name):
        """Read a prompt template file."""
        file_path = self.prompts_dir / f"{template_name}.txt"
        if not file_path.exists():
            return None
        
        with open(file_path, "r") as f:
            return f.read()
            
    def format_prompt(self, prompt_template, track_info):
        """Format a prompt template with track information."""
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
            "dow": current_dow,  # Day of week support
        }

        # Format the prompt template
        return prompt_template.format(**template_values)

def main():
    """Test the day of week placeholder functionality."""
    print("=" * 60)
    print("DAY OF WEEK PLACEHOLDER VERIFICATION")
    print("=" * 60)
    
    # Get current day of week
    current_dow = time.strftime("%A")
    print(f"Current day of week: {current_dow}")
    
    # Initialize tester
    prompts_dir = "templates/prompts"
    tester = SimplePromptTester(prompts_dir)
    
    # Sample track info
    track_info = {
        "title": "Sample Track",
        "artist": "Test Artist",
        "album": "Test Album",
        "year": "2025",
        "program": "Test Program",
        "presenter": "Test DJ",
    }
    
    # Test each prompt file in the directory
    prompt_files = tester.get_prompt_files()
    
    if not prompt_files:
        print("\nNo prompt templates found!")
        return
    
    print(f"\nFound {len(prompt_files)} prompt templates to test")
    
    success_count = 0
    for i, template_path in enumerate(prompt_files, 1):
        template_name = template_path.stem
        print(f"\n{i}. Testing {template_name}.txt")
        
        # Load the prompt content directly
        try:
            prompt_content = tester.read_prompt(template_name)
            if not prompt_content:
                print(f"  ❌ Failed to load prompt: {template_name}")
                continue
                
            # Format the prompt with track info
            formatted_prompt = tester.format_prompt(prompt_content, track_info)
            
            # Check if the day of week was replaced
            if "{dow}" in formatted_prompt:
                print(f"  ❌ ERROR: {{dow}} placeholder was not replaced")
            elif current_dow in formatted_prompt:
                print(f"  ✅ SUCCESS: Found '{current_dow}' in formatted prompt")
                preview = formatted_prompt.split("\n")[0]
                print(f"  Preview: \"{preview}\"")
                success_count += 1
            else:
                print(f"  ⚠️ WARNING: Prompt doesn't contain {{dow}} placeholder or current day")
                preview = formatted_prompt.split("\n")[0]
                print(f"  Preview: \"{preview}\"")
        except Exception as e:
            print(f"  ❌ ERROR testing {template_name}: {str(e)}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"SUMMARY: Successfully verified {success_count}/{len(prompt_files)} prompt templates")
    if success_count == len(prompt_files):
        print("✅ All prompt templates are working correctly with {dow} placeholder!")
    else:
        print("⚠️ Some prompt templates may not be using the {dow} placeholder correctly.")
    print("=" * 60)

if __name__ == "__main__":
    main()