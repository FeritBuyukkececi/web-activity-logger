"""Verify project setup is correct."""
import sys


def test_python_version():
    """Verify Python 3.14+ is being used."""
    assert sys.version_info >= (3, 14), f"Expected Python 3.14+, got {sys.version}"


def test_playwright_import():
    """Verify playwright is installed and importable."""
    from playwright.sync_api import sync_playwright
    assert sync_playwright is not None


def test_playwright_async_import():
    """Verify async playwright is importable."""
    from playwright.async_api import async_playwright
    assert async_playwright is not None


def test_folder_structure():
    """Verify required folders exist."""
    from pathlib import Path

    project_root = Path(__file__).parent.parent

    required_dirs = ["src", "extension", "tests", "logs"]
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        assert dir_path.exists(), f"Directory {dir_name}/ does not exist"
        assert dir_path.is_dir(), f"{dir_name} is not a directory"
