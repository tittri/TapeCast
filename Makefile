.PHONY: help install install-dev install-all test lint format clean build run check-ffmpeg

# Default target
help:
	@echo "TapeCast Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install        Install base dependencies"
	@echo "  make install-dev    Install development dependencies"
	@echo "  make install-all    Install all dependencies (base + optional + dev)"
	@echo ""
	@echo "Development:"
	@echo "  make test          Run tests"
	@echo "  make lint          Run linting"
	@echo "  make format        Format code"
	@echo "  make clean         Clean build artifacts"
	@echo "  make build         Build package"
	@echo ""
	@echo "Utilities:"
	@echo "  make check-ffmpeg  Check FFmpeg installation"
	@echo "  make run           Run TapeCast CLI"

# Install base dependencies
install:
	pip install -e .

# Install development dependencies
install-dev:
	pip install -e ".[dev]"

# Install all dependencies (including optional)
install-all:
	pip install -e ".[all,dev]"

# Run tests
test:
	pytest tests/ -v --cov=tapecast --cov-report=term-missing

# Run tests with markers
test-fast:
	pytest tests/ -v -m "not slow"

# Run linting
lint:
	ruff check tapecast tests
	mypy tapecast --ignore-missing-imports

# Format code
format:
	ruff format tapecast tests
	black tapecast tests

# Clean build artifacts
clean:
	rm -rf build dist *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*~" -delete
	rm -rf output/

# Build package
build: clean
	python -m build

# Check FFmpeg installation
check-ffmpeg:
	@which ffmpeg > /dev/null 2>&1 && echo "✓ FFmpeg found at: $$(which ffmpeg)" || echo "✗ FFmpeg not found"
	@which ffprobe > /dev/null 2>&1 && echo "✓ FFprobe found at: $$(which ffprobe)" || echo "✗ FFprobe not found"
	@ffmpeg -version 2>/dev/null | head -n1 || true

# Run the CLI
run:
	python -m tapecast

# Development server (for future web interface)
dev-server:
	@echo "Web interface not yet implemented"

# Create output directories
setup-dirs:
	mkdir -p output/downloads output/processed output/metadata output/thumbnails output/transcripts

# Install pre-commit hooks (if using pre-commit)
pre-commit:
	pre-commit install
	pre-commit run --all-files

# Generate requirements.txt from pyproject.toml (for compatibility)
requirements:
	pip-compile pyproject.toml -o requirements.txt --resolver=backtracking
	pip-compile --extra=dev pyproject.toml -o requirements-dev.txt --resolver=backtracking