"""
Logging Configuration Module for UCG-23 RAG ETL Pipeline

Configures loguru for structured external logging to the logs/ directory
with rotation, retention, and consistent formatting across all pipeline steps.

Provides separate log files for all messages and error-only messages with
different rotation and retention policies.
"""

import sys
from datetime import datetime
from typing import Any
from loguru import logger as _logger

from src.config import (
    LOG_LEVEL,
    LOGS_DIR,
)


# File format: Full timestamp with source location
FILE_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"

# Console format: Short timestamp without source location
CONSOLE_LOG_FORMAT = "{time:HH:mm:ss} | {level: <8} | {message}"


def setup_logger() -> Any:
    """
    Configure loguru logger with console and dual file outputs.

    Creates two log files:
    1. pipeline_{timestamp}.log - All log messages (10MB rotation, keep 10 files)
    2. errors_{timestamp}.log - Error/Critical only (5MB rotation, keep 20 files)

    Also configures colored console output for real-time monitoring.

    Returns:
        Configured loguru logger instance

    Example:
        >>> from src.utils.logging_config import setup_logger
        >>> logger = setup_logger()
        >>> logger.info("Starting ETL pipeline")
        >>> logger.error("Failed to parse document")
    """
    # Remove default handler to avoid duplicate logs
    _logger.remove()

    # Create logs directory if it doesn't exist
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate timestamp for log filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Add console handler with colored output
    _logger.add(
        sys.stderr,
        format=CONSOLE_LOG_FORMAT,
        level=LOG_LEVEL,
        colorize=True,
    )

    # Add main log file handler (all messages)
    pipeline_log = LOGS_DIR / f"pipeline_{timestamp}.log"
    _logger.add(
        pipeline_log,
        format=FILE_LOG_FORMAT,
        level=LOG_LEVEL,
        rotation="10 MB",  # Rotate when file reaches 10MB
        retention=10,  # Keep 10 log files
        compression="zip",  # Compress old log files
        enqueue=True,  # Thread-safe logging
    )

    # Add error log file handler (errors and critical only)
    error_log = LOGS_DIR / f"errors_{timestamp}.log"
    _logger.add(
        error_log,
        format=FILE_LOG_FORMAT,
        level="ERROR",  # Only ERROR and CRITICAL messages
        rotation="5 MB",  # Rotate when file reaches 5MB
        retention=20,  # Keep 20 error log files
        compression="zip",
        enqueue=True,
    )

    _logger.info(f"Logging configured: {pipeline_log}")
    _logger.info(f"Error logging configured: {error_log}")

    return _logger


def get_logger(name: str) -> Any:
    """
    Get a logger instance with context binding for a specific module.

    This function returns the global logger with the given name bound
    to it, allowing you to identify which module generated each log message.

    Args:
        name: Name identifier for the logger context (typically module name)

    Returns:
        Logger instance bound to the given name

    Example:
        >>> from src.utils.logging_config import get_logger
        >>> logger = get_logger("step0_registration")
        >>> logger.info("Document registered successfully")
    """
    return _logger.bind(name=name)


def log_step_start(step_name: str) -> None:
    """
    Log the start of a pipeline step with consistent formatting.

    Args:
        step_name: Name of the pipeline step (e.g., "Step 0: Document Registration")

    Example:
        >>> from src.utils.logging_config import log_step_start
        >>> log_step_start("Step 0: Document Registration")
    """
    _logger.info("=" * 80)
    _logger.info(f"STARTING: {step_name}")
    _logger.info("=" * 80)


def log_step_complete(step_name: str, duration: float) -> None:
    """
    Log the completion of a pipeline step with duration.

    Args:
        step_name: Name of the pipeline step
        duration: Duration in seconds (use time.time() difference)

    Example:
        >>> import time
        >>> from src.utils.logging_config import log_step_complete
        >>> start_time = time.time()
        >>> # ... do work ...
        >>> duration = time.time() - start_time
        >>> log_step_complete("Step 0: Document Registration", duration)
    """
    _logger.success(f"COMPLETED: {step_name}")
    _logger.info(f"Duration: {duration:.2f} seconds ({duration / 60:.2f} minutes)")
    _logger.info("=" * 80)


# Export the logger instance for direct use
logger = _logger


__all__ = [
    "setup_logger",
    "get_logger",
    "log_step_start",
    "log_step_complete",
    "logger",
]
