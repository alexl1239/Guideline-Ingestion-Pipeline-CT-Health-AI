"""
STEP 0 — DOCUMENT REGISTRATION

Registers clinical guideline PDFs in the SQLite database with complete provenance:
- SHA-256 checksum for data integrity
- Full PDF bytes stored for self-contained database
- UUID generation for unique document identification
- Transaction boundaries for atomicity
- Embedding metadata registration
- Comprehensive error handling and logging

Document-agnostic: Works with any clinical guideline PDF specified in config.

Input: PDF file specified in config (SOURCE_PDF_PATH)
Output: Document record in SQLite with metadata
"""

import hashlib
import uuid
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional

from src.utils.logging_config import logger
from src.config import (
    DOCLING_VERSION,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_DIMENSION,
    SOURCE_PDF_PATH,
)
from src.database.connections import get_connection

# Source PDF path from config
PDF_PATH = SOURCE_PDF_PATH


class RegistrationError(Exception):
    """Raised when document registration fails."""
    pass


def compute_sha256(file_path: Path) -> str:
    """
    Compute SHA-256 checksum of a file.

    Reads file in 8KB chunks to handle large files efficiently without
    loading entire file into memory.

    Args:
        file_path: Path to the file to hash

    Returns:
        Hexadecimal SHA-256 checksum string

    Raises:
        IOError: If file cannot be read
    """
    logger.info(f"Computing SHA-256 checksum for: {file_path.name}")
    sha256_hash = hashlib.sha256()

    file_size = file_path.stat().st_size
    bytes_processed = 0

    try:
        with open(file_path, "rb") as f:
            # Read in 8KB chunks
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
                bytes_processed += len(chunk)

                # Log progress for large files (every 10MB)
                if bytes_processed % (10 * 1024 * 1024) == 0:
                    progress = (bytes_processed / file_size) * 100
                    logger.debug(f"Hashing progress: {progress:.1f}% ({bytes_processed:,} / {file_size:,} bytes)")

        checksum = sha256_hash.hexdigest()
        logger.success(f"SHA-256 checksum computed: {checksum[:16]}...")
        return checksum

    except IOError as e:
        logger.error(f"Failed to read file for hashing: {e}")
        raise


def check_document_exists(checksum: str) -> Optional[str]:
    """
    Check if a document with the given checksum already exists.

    Args:
        checksum: SHA-256 checksum of the file

    Returns:
        Document ID (UUID string) if exists, None otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id FROM documents WHERE checksum_sha256 = ?",
                (checksum,)
            )
            result = cursor.fetchone()

            if result:
                doc_id = result[0]
                logger.info(f"Document already registered with ID: {doc_id}")
                return doc_id

            return None

    except Exception as e:
        logger.debug(f"Could not check for existing document: {e}")
        return None


def run() -> str:
    """
    Execute Step 0: Document Registration.

    Process:
    1. Validate PDF file exists
    2. Compute SHA-256 checksum
    3. Check for existing registration (idempotency)
    4. Generate UUID for new document
    5. Load PDF bytes
    6. Begin SQL transaction
    7. Insert into documents table
    8. Insert into embedding_metadata table
    9. Commit on success, rollback on error

    Returns:
        UUID string of registered document

    Raises:
        FileNotFoundError: If PDF file is missing
        RegistrationError: If registration fails
    """
    logger.info("=" * 80)
    logger.info("STEP 0: DOCUMENT REGISTRATION")
    logger.info("=" * 80)

    # 1. Validate PDF exists
    if not PDF_PATH.exists():
        logger.error(f"PDF not found at: {PDF_PATH.resolve()}")
        raise FileNotFoundError(
            f"❌ PDF not found at: {PDF_PATH.resolve()}\n"
            f"Fix: Ensure PDF is located at {PDF_PATH}"
        )

    logger.success(f"✓ Found PDF: {PDF_PATH.name}")
    file_size_mb = PDF_PATH.stat().st_size / (1024 * 1024)
    logger.info(f"  File size: {file_size_mb:.2f} MB")

    # 2. Compute SHA-256 checksum
    checksum = compute_sha256(PDF_PATH)
    logger.success(f"✓ SHA-256 checksum: {checksum}")

    # 3. Check if already registered (idempotency)
    existing_id = check_document_exists(checksum)
    if existing_id:
        logger.warning(f"⚠ Document already registered with ID: {existing_id}")
        logger.info("Skipping re-registration (idempotent)")
        logger.info("=" * 80)
        return existing_id

    # 4. Generate UUID
    document_id = str(uuid.uuid4())
    logger.success(f"✓ Generated document ID: {document_id}")

    # 5. Load PDF bytes
    logger.info(f"Loading PDF bytes ({file_size_mb:.2f} MB)...")
    try:
        pdf_bytes = PDF_PATH.read_bytes()
        logger.success(f"✓ Loaded {len(pdf_bytes):,} PDF bytes")
    except Exception as e:
        logger.error(f"Failed to read PDF bytes: {e}")
        raise RegistrationError(f"Could not read PDF file: {e}") from e

    # 6-9. Database transaction
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            logger.info("Beginning SQL transaction...")
            cursor.execute("BEGIN")

            # Insert into documents table
            logger.info("Inserting document record...")

            # Extract document title from filename (remove .pdf extension)
            doc_title = PDF_PATH.stem

            cursor.execute(
                """
                INSERT INTO documents (
                    id, title, version_label, source_url,
                    checksum_sha256, pdf_bytes, docling_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    doc_title,
                    None,  # Version label can be set manually if needed
                    None,  # Source URL can be set manually if needed
                    checksum,
                    pdf_bytes,
                    None,  # Will be populated in Step 1 (Parsing)
                    datetime.now(UTC).isoformat(),
                ),
            )
            logger.success("✓ Document record inserted")

            # Insert embedding metadata (only if not exists)
            cursor.execute("SELECT id FROM embedding_metadata WHERE model_name = ?", (EMBEDDING_MODEL_NAME,))
            if not cursor.fetchone():
                logger.info("Inserting embedding metadata...")
                cursor.execute(
                    """
                    INSERT INTO embedding_metadata (
                        model_name, dimension, docling_version, created_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        EMBEDDING_MODEL_NAME,
                        EMBEDDING_DIMENSION,
                        DOCLING_VERSION,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                logger.success("✓ Embedding metadata inserted")
            else:
                logger.debug("Embedding metadata already exists (skipping)")

            # Commit is handled automatically by context manager
            logger.success("✓ Transaction committed successfully")

        # Summary (after successful commit)
        logger.info("")
        logger.info("=" * 80)
        logger.info("REGISTRATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Document ID:        {document_id}")
        logger.info(f"Title:              {PDF_PATH.stem}")
        logger.info(f"Checksum (SHA-256): {checksum}")
        logger.info(f"PDF Size:           {file_size_mb:.2f} MB")
        logger.info(f"Embedding Model:    {EMBEDDING_MODEL_NAME}")
        logger.info(f"Embedding Dim:      {EMBEDDING_DIMENSION}")
        logger.info(f"Docling Version:    {DOCLING_VERSION}")
        logger.info("=" * 80)
        logger.info("")

        return document_id

    except Exception as e:
        logger.error(f"❌ Transaction failed: {e}")
        raise RegistrationError(f"Database insertion failed: {e}") from e


if __name__ == "__main__":
    # Initialize logging when run directly
    from src.utils.logging_config import setup_logger
    setup_logger()

    try:
        doc_id = run()
        logger.info(f"✓ Step 0 completed successfully. Document ID: {doc_id}")
    except Exception as e:
        logger.error(f"❌ Step 0 failed: {e}")
        exit(1)
