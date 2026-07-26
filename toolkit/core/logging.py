"""
Centralized logging configuration for Spotify-Apple Music Toolkit.
Provides Rich-integrated logging with consistent formatting across all modules.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

_configured = False
_console: Optional[Console] = None


def get_console() -> Console:
    """Return shared Rich console instance."""
    global _console
    if _console is None:
        _console = Console()
    return _console


def setup_logging(level: int = logging.INFO, show_path: bool = False) -> None:
    """
    Configure root logger with Rich handler.
    Call once at application startup.

    Args:
        level: Logging level (default INFO)
        show_path: Show file path in log output (default False)
    """
    global _configured
    if _configured:
        return

    console = get_console()
    handler = RichHandler(
        console=console,
        show_path=show_path,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("spotipy").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given module name.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    if not _configured:
        setup_logging()
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, msg: str, exc: Exception) -> None:
    """
    Log an exception with full traceback at ERROR level.

    Args:
        logger: Logger instance
        msg: Error message
        exc: Exception instance
    """
    logger.error(f"{msg}: {exc}", exc_info=True)


def log_warning(logger: logging.Logger, msg: str, exc: Optional[Exception] = None) -> None:
    """
    Log a warning, optionally with exception info.

    Args:
        logger: Logger instance
        msg: Warning message
        exc: Optional exception instance
    """
    if exc:
        logger.warning(f"{msg}: {exc}")
    else:
        logger.warning(msg)


# Initialize logging on module import
setup_logging()
