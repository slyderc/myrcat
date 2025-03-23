#!/usr/bin/env python3
"""
Setup script for Myrcat package.
"""

from setuptools import setup, find_packages
import re

# Extract version from __init__.py
with open("myrcat/__init__.py", "r") as f:
    version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
    version = version_match.group(1) if version_match else '0.0.0'

# Read requirements
with open("requirements.txt", "r") as f:
    requirements = f.read().splitlines()

setup(
    name="myrcat",
    version=version,
    description="Myriad Playout Cataloging for Now Wave Radio",
    author="Clint Dimick",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "myrcat=myrcat.main:main",
        ],
    },
    python_requires=">=3.7",
)