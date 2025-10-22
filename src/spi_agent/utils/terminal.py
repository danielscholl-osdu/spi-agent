"""Terminal manipulation utilities for cross-platform screen clearing.

This module provides utilities for clearing the terminal screen across
different platforms (macOS, Linux, Windows) using multiple fallback strategies.
"""

import os
import sys
from typing import Optional


def supports_ansi_codes() -> bool:
    """Check if the terminal supports ANSI escape sequences.

    Returns:
        True if terminal likely supports ANSI codes, False otherwise
    """
    # Check if stdout is a TTY (not redirected to file/pipe)
    if not sys.stdout.isatty():
        return False

    # Check for TERM environment variable on Unix systems
    term = os.environ.get("TERM", "")
    if term and term != "dumb":
        return True

    # On Windows 10+, ANSI is supported
    if sys.platform == "win32":
        try:
            # Windows 10 version 1511+ supports ANSI
            import platform
            version = platform.version()
            # Check Windows version (10.0.xxxxx format)
            if version.startswith("10.0."):
                build = int(version.split(".")[2])
                return build >= 10586  # Windows 10 version 1511
        except (ValueError, IndexError, ImportError):
            pass

    return False


def get_clear_command() -> Optional[str]:
    """Get the platform-appropriate terminal clear command.

    Returns:
        Command string ("clear" or "cls"), or None if platform unknown
    """
    if sys.platform == "win32":
        return "cls"
    elif sys.platform in ("darwin", "linux", "linux2"):
        return "clear"
    return None


def clear_screen() -> bool:
    """Clear the terminal screen using available methods.

    Tries multiple approaches in order:
    1. ANSI escape codes (universal, works on most terminals)
    2. Platform-specific command (clear/cls via os.system)

    Returns:
        True if clearing succeeded, False otherwise
    """
    # Try ANSI escape codes first
    if supports_ansi_codes():
        try:
            # \033[2J clears the entire screen
            # \033[H moves cursor to home position (top-left)
            print("\033[2J\033[H", end="", flush=True)
            return True
        except Exception:
            # If ANSI fails, continue to next method
            pass

    # Fall back to platform-specific command
    clear_cmd = get_clear_command()
    if clear_cmd:
        try:
            result = os.system(clear_cmd)
            return result == 0
        except Exception:
            # If command fails, return False
            pass

    # All methods failed
    return False
