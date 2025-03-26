# Myrcat Utilities

This directory contains helper utilities for the Myrcat system.

## testprompt.py

A utility to test AI prompts for social media posts without posting to social platforms.

### Purpose

This utility allows you to test how different track metadata and prompts generate social media posts, helping to refine prompt templates for better results. It uses the same code as the main application for prompt selection, AI calls, and content generation, ensuring that what you see in the test will match what will be posted in production.

### Features

- Uses the same prompt selection logic as the main application
- Makes real API calls to Claude for authentic results
- Displays formatted sample posts with hashtags
- Shows statistics about the generated post
- Pulls track information from a configuration file
- Doesn't post to any social media platforms

### Usage

1. Copy the sample configuration file:

```bash
cp utils/testprompt.ini.example utils/myconfig.ini
```

2. Edit the configuration file to add your API key and customize track information:

```bash
nano utils/myconfig.ini
```

3. Run the utility:

```bash
./utils/testprompt.py -c utils/myconfig.ini
```

### Configuration

The configuration file includes:

- `[track]` section: Track metadata (artist, title, album, etc.)
- `[ai_content]` section: AI service settings (API key, model, etc.)
- `[bluesky]` section: Formatting settings (used for hashtag generation)
- `[publish_exceptions]` section: Ensures no actual posts are made

### Example Output

```
========================================================================
Test Prompt Utility - Sample Post Generator
========================================================================

📋 Track Information:
   Artist:    Bonobo
   Title:     Ketto
   Album:     Days to Come
   Year:      2006
   Program:   Morning Chill
   Presenter: DJ Ambient

🤖 AI Generation Information:
   Source:  ai
   Prompt:  morning_chill

📝 Generated Post:
------------------------------------------------------------------------
☕ Ease into your day with Bonobo's atmospheric "Ketto" on Now Wave Radio. DJ Ambient bringing those perfect morning downtempo vibes from 2006's "Days to Come" album. Pure chill perfection!

#NowWaveRadio #MorningChill #Bonobo
------------------------------------------------------------------------

📊 Post Statistics:
   Character count: 212/300 (✅ OK)
   Word count:      35
   Hashtags:        3

🔖 Extracted Hashtags:
   #NowWaveRadio
   #MorningChill
   #Bonobo
```

### Troubleshooting

If you encounter errors:

1. Check your API key is correctly set in the configuration file
2. Ensure the paths to prompt files are correct
3. Check for any missing required fields in the configuration file
4. Run with verbose logging to see what's happening

For more detailed error information, you can modify the logging level in the script to DEBUG.