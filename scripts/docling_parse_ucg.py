#!/usr/bin/env python3
"""
Docling PDF parsing utility script.

Quick script to parse UCG-23 PDF using Docling and save outputs.
"""

from pathlib import Path
import json
import sys

from docling.document_converter import DocumentConverter

# Add project root to path for proper module resolution
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logging_config import setup_logger, logger

PDF_PATH = Path("data/Uganda_Clinical_Guidelines_2023.pdf")
OUT_DIR = Path("data/docling_outputs")
MARKDOWN_PATH = OUT_DIR / "ucg23_docling.md"
JSON_PATH = OUT_DIR / "ucg23_docling.json"


def main():
    """Parse PDF with Docling and save outputs."""
    # Initialize logging
    setup_logger()

    if not PDF_PATH.exists():
        logger.error(f"PDF not found: {PDF_PATH.resolve()}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Parsing PDF with Docling...")
    converter = DocumentConverter()
    result = converter.convert(str(PDF_PATH))
    doc = result.document

    # save markdown
    markdown = doc.export_to_markdown()
    MARKDOWN_PATH.write_text(markdown, encoding="utf-8")
    logger.success(f"Wrote markdown → {MARKDOWN_PATH}")

    # save structured JSON
    doc_dict = doc.export_to_dict()
    JSON_PATH.write_text(json.dumps(doc_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.success(f"Wrote docling JSON → {JSON_PATH}")

    logger.success("Done parsing UCG-23!")


if __name__ == "__main__":
    main()
