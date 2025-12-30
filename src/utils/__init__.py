"""
Utilities Module for UCG-23 RAG ETL Pipeline

Organized by pipeline step for clarity and maintainability.

Structure:
- logging_config.py: Shared logging utilities
- parsing/: Step 1 utilities (Docling mapping)
- segmentation/: Step 2 utilities (heading patterns, ToC parsing, hierarchy building)
"""

# Re-export logging utilities at top level for backward compatibility
from src.utils.logging_config import setup_logger, get_logger, logger

__all__ = [
    "setup_logger",
    "get_logger",
    "logger",
]
