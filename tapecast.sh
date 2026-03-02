#!/bin/bash
# TapeCast launcher script
# This script activates the virtual environment and runs TapeCast

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Activate the virtual environment (Python 3.12)
source "$SCRIPT_DIR/venv312/bin/activate"

# Run TapeCast with all arguments passed to this script
tapecast "$@"