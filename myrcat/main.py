#!/usr/bin/env python3
"""
Myrcat - Myriad Playout Cataloging for Now Wave Radio
Author: Clint Dimick
Description: Socket-based service that receives Myriad OCP JSON payloads
"""

import sys
import asyncio
import argparse
from pathlib import Path

from myrcat import __version__
from myrcat.core import Myrcat
from myrcat.exceptions import MyrcatException, ConfigurationError


def parse_arguments():
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Myrcat - Myriad Cataloger")
    parser.add_argument(
        "-c",
        "--config",
        default="config.ini",
        help="Path to config file (default: ./config.ini)",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"Myrcat {__version__}",
        help="Show version information and exit",
    )

    return parser.parse_args()


def main():
    """Main entry point for the application."""
    args = parse_arguments()

    if not Path(args.config).exists():
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    try:
        app = Myrcat(args.config)
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("🔴 Shutting down!")
    except ConfigurationError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except MyrcatException as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()