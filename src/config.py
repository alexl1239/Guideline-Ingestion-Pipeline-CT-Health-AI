"""
Configuration Module for UCG-23 RAG ETL Pipeline

Loads configuration from environment variables (.env file) and validates
that all required settings are present. Includes model settings, API keys,
file paths, and batch processing parameters.
"""

import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Note: Logger will be configured by setup_logger() in logging_config
# Import is deferred to avoid circular dependency during config loading


# Load environment variables from .env file
# Look for .env in the project root (parent of src/)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try loading from current directory as fallback
    load_dotenv()


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


def get_env_variable(var_name: str, required: bool = True, default: Optional[str] = None) -> str:
    """
    Get environment variable with validation.

    Args:
        var_name: Name of environment variable
        required: Whether this variable is required
        default: Default value if not required and not found

    Returns:
        Value of environment variable

    Raises:
        ConfigurationError: If required variable is missing
    """
    value = os.getenv(var_name)

    if value is None or value.strip() == "":
        if required:
            raise ConfigurationError(
                f"Required environment variable '{var_name}' is not set. "
                f"Please add it to your .env file."
            )
        return default

    return value.strip()


# ==================================
# API Keys (Required)
# ==================================

try:
    # OpenAI API key (for embeddings)
    OPENAI_API_KEY = get_env_variable("OPENAI_API_KEY", required=True)

    # Claude API key (optional, for LLM-based processing)
    CLAUDE_API_KEY = get_env_variable("CLAUDE_API_KEY", required=False)

except ConfigurationError as e:
    # Note: Using print() here because this runs during module import,
    # before logging is configured. Logging setup depends on config being loaded first.
    print(f"\n❌ Configuration Error: {e}", file=sys.stderr)
    print("\nPlease ensure your .env file contains all required API keys:", file=sys.stderr)
    print("  - OPENAI_API_KEY", file=sys.stderr)
    print("  - CLAUDE_API_KEY (optional)", file=sys.stderr)
    sys.exit(1)


# ==================================
# Model Configuration
# ==================================

# Embedding model settings (OpenAI text-embedding-3-small)
EMBEDDING_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536  # Fixed dimension for text-embedding-3-small

# IMPORTANT: Changing embedding model requires regenerating entire vector table
# per requirements section 3.3


# ==================================
# Token Limits (from requirements)
# ==================================

# Child chunk settings (retrieval units)
CHILD_TOKEN_TARGET = 256  # Target size for child chunks
CHILD_TOKEN_TOLERANCE = 0.10  # ±10% tolerance
CHILD_TOKEN_HARD_MAX = 512  # Hard maximum (never exceed)

# Parent chunk settings (context for LLM)
PARENT_TOKEN_TARGET = 1500  # Target size for parent chunks
PARENT_TOKEN_MIN = 1000  # Minimum preferred size
PARENT_TOKEN_HARD_MAX = 2000  # Hard maximum (never exceed)

# Token encoding (all tokenization uses tiktoken cl100k_base)
TOKEN_ENCODING = "cl100k_base"


# ==================================
# Batch Processing Parameters
# ==================================

# From requirements section 7.1 (Transaction boundaries)

# Step 1 (Parsing): Batch per N blocks
PARSING_BATCH_SIZE = 100

# Step 3-4 (Cleanup/Tables): Batch per N sections
CLEANUP_BATCH_SIZE = 10
TABLE_BATCH_SIZE = 10

# Step 6 (Embeddings): Batch per N chunks
EMBEDDING_BATCH_SIZE = 100

# Retry settings for API calls
MAX_API_RETRIES = 3
API_RETRY_INITIAL_BACKOFF = 2  # seconds


# ==================================
# Table Conversion Thresholds
# ==================================

# From requirements section 5.5
# Large tables (>50 rows or >10 columns) are handled differently
LARGE_TABLE_ROW_THRESHOLD = 50
LARGE_TABLE_COL_THRESHOLD = 10


# ==================================
# File Paths
# ==================================

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Source PDF file (Docling has no page limit, so single file processing)
SOURCE_PDF_PATH = PROJECT_ROOT / "data" / "ucg23_raw" / "Uganda_Clinical_Guidelines_2023.pdf"


# Output database
DATABASE_PATH = PROJECT_ROOT / "data" / "ucg23_rag.db"

# Intermediate processing directories
INTERMEDIATE_DIR = PROJECT_ROOT / "data" / "intermediate"
EXPORTS_DIR = PROJECT_ROOT / "data" / "exports"
QA_REPORTS_DIR = PROJECT_ROOT / "data" / "qa_reports"

# Logging directory
LOGS_DIR = PROJECT_ROOT / "logs"


# ==================================
# Docling Configuration
# ==================================

# Docling version tracking for reproducibility
# Docling is an open-source, offline PDF parser by IBM
# Key features: no page limit, local processing, no API key required
DOCLING_VERSION = "2.0.0"  # Update this when upgrading Docling

# Docling configuration notes:
# - Full document processing in single pass (no page limit)
# - OCR support via Tesseract for scanned pages
# - Automatic multi-page table reconstruction
# - High-quality layout analysis for accurate reading order
# - Native identification of page headers/footers for filtering


# ==================================
# QA Validation Settings
# ==================================

# From requirements section 5.8.2 (Statistical validation requirements)

# Percentage of diseases to sample for full accuracy review
QA_DISEASE_SAMPLE_PERCENTAGE = 0.20  # 20%

# Sections that require 100% validation
QA_EMERGENCY_PROTOCOLS_REQUIRED = True  # 100% validation
QA_VACCINE_SCHEDULES_REQUIRED = True  # 100% validation


# ==================================
# Logging Configuration
# ==================================

# Log level (used by logging_config.py)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Note: Log format, rotation, and retention are configured in src/utils/logging_config.py
# to avoid redundancy and maintain a single source of truth for logging setup.


# ==================================
# Validation on Import
# ==================================

def validate_configuration():
    """
    Validate configuration on module import.

    Checks:
    - API keys are present
    - File paths are valid
    - Numeric values are in valid ranges
    - Required directories exist or can be created

    Raises:
        ConfigurationError: If configuration is invalid
    """
    errors = []

    # Validate API keys (already checked above, but verify not empty)
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is empty")

    # Validate token limits
    if CHILD_TOKEN_TARGET <= 0:
        errors.append(f"CHILD_TOKEN_TARGET must be positive, got {CHILD_TOKEN_TARGET}")
    if CHILD_TOKEN_HARD_MAX <= CHILD_TOKEN_TARGET:
        errors.append(
            f"CHILD_TOKEN_HARD_MAX ({CHILD_TOKEN_HARD_MAX}) must be greater than "
            f"CHILD_TOKEN_TARGET ({CHILD_TOKEN_TARGET})"
        )
    if PARENT_TOKEN_HARD_MAX <= PARENT_TOKEN_TARGET:
        errors.append(
            f"PARENT_TOKEN_HARD_MAX ({PARENT_TOKEN_HARD_MAX}) must be greater than "
            f"PARENT_TOKEN_TARGET ({PARENT_TOKEN_TARGET})"
        )

    # Validate batch sizes
    if PARSING_BATCH_SIZE <= 0:
        errors.append(f"PARSING_BATCH_SIZE must be positive, got {PARSING_BATCH_SIZE}")
    if EMBEDDING_BATCH_SIZE <= 0:
        errors.append(f"EMBEDDING_BATCH_SIZE must be positive, got {EMBEDDING_BATCH_SIZE}")

    # Validate source PDF exists
    if not SOURCE_PDF_PATH.exists():
        errors.append(f"Source PDF not found: {SOURCE_PDF_PATH}")

    # Create required directories if they don't exist
    for directory in [INTERMEDIATE_DIR, EXPORTS_DIR, QA_REPORTS_DIR, LOGS_DIR]:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create directory {directory}: {e}")

    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
        raise ConfigurationError(error_msg)


# Run validation on import
try:
    validate_configuration()
except ConfigurationError as e:
    # Note: Using print() here because this runs during module import,
    # before logging is configured. Logging setup depends on config being loaded first.
    print(f"\n❌ {e}", file=sys.stderr)
    sys.exit(1)


# ==================================
# Helper Functions
# ==================================

def get_child_chunk_range() -> tuple[int, int]:
    """
    Get valid token range for child chunks.

    Returns:
        Tuple of (min_tokens, max_tokens)
    """
    tolerance_tokens = int(CHILD_TOKEN_TARGET * CHILD_TOKEN_TOLERANCE)
    min_tokens = CHILD_TOKEN_TARGET - tolerance_tokens
    max_tokens = min(CHILD_TOKEN_TARGET + tolerance_tokens, CHILD_TOKEN_HARD_MAX)
    return (min_tokens, max_tokens)


def get_parent_chunk_range() -> tuple[int, int]:
    """
    Get valid token range for parent chunks.

    Returns:
        Tuple of (min_tokens, max_tokens)
    """
    return (PARENT_TOKEN_MIN, PARENT_TOKEN_HARD_MAX)


def print_configuration():
    """Print current configuration (for debugging)."""
    print("\n" + "=" * 80)
    print("UCG-23 RAG ETL Pipeline Configuration")
    print("=" * 80)
    print(f"\nAPI Keys:")
    print(f"  OPENAI_API_KEY: {'✓ Set' if OPENAI_API_KEY else '✗ Missing'}")
    print(f"  CLAUDE_API_KEY: {'✓ Set' if CLAUDE_API_KEY else '- Not set (optional)'}")
    print(f"\nParsing Configuration:")
    print(f"  Parser: Docling (offline, open-source)")
    print(f"  Docling Version: {DOCLING_VERSION}")
    print(f"\nModel Configuration:")
    print(f"  Embedding Model: {EMBEDDING_MODEL_NAME}")
    print(f"  Embedding Dimension: {EMBEDDING_DIMENSION}")
    print(f"\nToken Limits:")
    print(f"  Child chunks: target={CHILD_TOKEN_TARGET}, max={CHILD_TOKEN_HARD_MAX}")
    print(f"  Parent chunks: target={PARENT_TOKEN_TARGET}, max={PARENT_TOKEN_HARD_MAX}")
    print(f"\nBatch Sizes:")
    print(f"  Parsing: {PARSING_BATCH_SIZE} blocks")
    print(f"  Cleanup/Tables: {CLEANUP_BATCH_SIZE}/{TABLE_BATCH_SIZE} sections")
    print(f"  Embeddings: {EMBEDDING_BATCH_SIZE} chunks")
    print(f"\nFile Paths:")
    print(f"  Source PDF: {SOURCE_PDF_PATH.name} ({'exists' if SOURCE_PDF_PATH.exists() else 'missing'})")
    print(f"  Database: {DATABASE_PATH}")
    print(f"\nDirectories:")
    print(f"  Intermediate: {INTERMEDIATE_DIR}")
    print(f"  Exports: {EXPORTS_DIR}")
    print(f"  QA Reports: {QA_REPORTS_DIR}")
    print(f"  Logs: {LOGS_DIR}")
    print("=" * 80 + "\n")


# Export all configuration variables
__all__ = [
    # API Keys
    "OPENAI_API_KEY",
    "CLAUDE_API_KEY",
    # Model settings
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIMENSION",
    "TOKEN_ENCODING",
    # Token limits
    "CHILD_TOKEN_TARGET",
    "CHILD_TOKEN_TOLERANCE",
    "CHILD_TOKEN_HARD_MAX",
    "PARENT_TOKEN_TARGET",
    "PARENT_TOKEN_MIN",
    "PARENT_TOKEN_HARD_MAX",
    # Batch settings
    "PARSING_BATCH_SIZE",
    "CLEANUP_BATCH_SIZE",
    "TABLE_BATCH_SIZE",
    "EMBEDDING_BATCH_SIZE",
    "MAX_API_RETRIES",
    "API_RETRY_INITIAL_BACKOFF",
    # Table settings
    "LARGE_TABLE_ROW_THRESHOLD",
    "LARGE_TABLE_COL_THRESHOLD",
    # File paths
    "PROJECT_ROOT",
    "SOURCE_PDF_PATH",
    "DATABASE_PATH",
    "INTERMEDIATE_DIR",
    "EXPORTS_DIR",
    "QA_REPORTS_DIR",
    "LOGS_DIR",
    # Docling config
    "DOCLING_VERSION",
    # QA settings
    "QA_DISEASE_SAMPLE_PERCENTAGE",
    "QA_EMERGENCY_PROTOCOLS_REQUIRED",
    "QA_VACCINE_SCHEDULES_REQUIRED",
    # Logging
    "LOG_LEVEL",
    # Helper functions
    "get_child_chunk_range",
    "get_parent_chunk_range",
    "print_configuration",
]
