"""
Test script to dump the Claude API response structure for debugging.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp
from anthropic import Anthropic

# Add parent directory to path to import myrcat
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def test_claude_api():
    """Call the Anthropic Claude API and dump the response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    
    if not api_key:
        print("Error: No ANTHROPIC_API_KEY found in environment variables")
        return
    
    # Using the newer Anthropic SDK
    client = Anthropic(api_key=api_key)
    
    prompt = """Write a short social media post about a song.
    
    Song: "Bohemian Rhapsody" by Queen
    Album: A Night at the Opera
    Year: 1975
    
    Keep it under 200 characters."""
    
    print("Calling Claude API...")
    
    try:
        # Make the API call using the SDK
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=100,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )
        
        # Pretty print the entire response
        print("\nFull response structure:")
        print(json.dumps(message.model_dump(), indent=2))
        
        # Extract relevant fields
        print("\nExtracted Fields:")
        print(f"Model: {message.model}")
        print(f"Input Tokens: {message.usage.input_tokens}")
        print(f"Output Tokens: {message.usage.output_tokens}")
        print(f"Total Tokens: {message.usage.input_tokens + message.usage.output_tokens}")
        
        # Calculate costs
        input_rate = 0.000003  # $3 per million input tokens
        output_rate = 0.000015  # $15 per million output tokens
        input_cost = message.usage.input_tokens * input_rate
        output_cost = message.usage.output_tokens * output_rate
        total_cost = input_cost + output_cost
        
        print(f"\nCost Calculation:")
        print(f"Input Cost: ${input_cost:.6f}")
        print(f"Output Cost: ${output_cost:.6f}")
        print(f"Total Cost: ${total_cost:.6f}")
        
    except Exception as e:
        print(f"Error calling Claude API: {e}")

if __name__ == "__main__":
    asyncio.run(test_claude_api())