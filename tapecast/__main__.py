"""
TapeCast CLI entry point

This allows the package to be run with: python -m tapecast
"""

from .cli import app


if __name__ == "__main__":
    app()