#!/bin/bash
#
# Myrcat shell launcher for systemd

cd "$(dirname "$0")"
source venv/bin/activate
python myrcat.py $*
deactivate
exit 0

