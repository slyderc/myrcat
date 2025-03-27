#!/bin/bash
# Helper script to run the testprompt utility

source ../venv/bin/activate > /dev/null 2>&1

# No logs directory needed

# Run the utility with the provided arguments
python ./testprompt.py "$@"

# Provide help if no arguments given
if [ $# -eq 0 ]; then
    echo ""
    echo "Usage: ./testprompt.sh -c config_file.ini"
    echo ""
    echo "Example configs available:"
    echo "  ./testprompt.sh -c testprompt.ini.example"
    echo "  ./testprompt.sh -c jazz_test.ini.example"
    echo ""
    echo "To create your own config with API access:"
    echo "  cp utils/testprompt.ini.example myconfig.ini"
    echo "  vim myconfig.ini  # edit to add your API key and customize track info"
    echo "  ./testprompt.sh -c myconfig.ini"
    echo ""
    echo "IMPORTANT: To use AI generation, you must add a valid Anthropic API key"
    echo "           to your config file. Without an API key, the utility will"
    echo "           fall back to using templates instead of AI-generated content."
    echo ""
fi
