"""
Docling Parser Implementation

Uses IBM Docling (open-source, offline PDF parser) to convert PDFs into
structured markdown and JSON representations.

Features:
- Offline processing (no API key required)
- No page limit (processes entire document in single pass)
- Multi-page table reconstruction
- High-quality layout analysis
- Native page header/footer identification
- OCR support via Tesseract

Outputs:
- Clean markdown text
- Structured JSON document representation
- Saved to data/docling_outputs/ for inspection
"""

from __future__ import annotations

import json
from pathlib import Path

from docling.document_converter import DocumentConverter
from loguru import logger

from src.config import DOCLING_VERSION
from .base import BaseParser, ParseResult


class DoclingParser(BaseParser):
    """
    Docling-based PDF parser implementation.

    Wraps IBM Docling's DocumentConverter to provide a clean interface
    for the ETL pipeline. Converts PDFs into markdown and structured JSON.

    Example:
        >>> parser = DoclingParser()
        >>> result = parser.parse(Path("data/document.pdf"))
        >>> print(f"Parsed {result.num_pages} pages")
        >>> print(result.md_text[:100])  # First 100 chars of markdown
    """

    def __init__(self) -> None:
        """
        Initialize Docling parser with default configuration.

        Uses Docling's default settings:
        - OCR enabled via Tesseract for scanned pages
        - Default layout analysis model
        - Automatic multi-page table reconstruction
        """
        super().__init__()
        self.logger.info(f"Initializing Docling parser (version {DOCLING_VERSION})")

        try:
            self._converter = DocumentConverter()
            self.logger.success("Docling DocumentConverter initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Docling: {e}")
            raise RuntimeError(f"Docling initialization failed: {e}") from e

        # Create output directory for saving markdown and JSON
        self._output_dir = Path("data/docling_outputs")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"Output directory: {self._output_dir}")

    def parse(self, pdf_path: Path) -> ParseResult:
        """
        Parse a PDF file using Docling.

        Process:
        1. Validate PDF file exists
        2. Run Docling end-to-end conversion
        3. Extract markdown text
        4. Extract structured JSON
        5. Count pages
        6. Save outputs to data/docling_outputs/
        7. Return ParseResult

        Args:
            pdf_path: Path to the PDF file to parse

        Returns:
            ParseResult containing doc_json, md_text, num_pages, and parser_version

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            RuntimeError: If Docling parsing fails
        """
        # 1. Validate PDF exists
        if not pdf_path.exists():
            self.logger.error(f"PDF not found: {pdf_path}")
            raise FileNotFoundError(f"PDF not found at {pdf_path}")

        self.logger.info(f"Starting Docling parse: {pdf_path.name}")
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        self.logger.info(f"  File size: {file_size_mb:.2f} MB")

        try:
            # 2. Run Docling conversion (PDF → DoclingDocument)
            self.logger.info("Running Docling conversion...")
            result = self._converter.convert(str(pdf_path))
            doc = result.document
            self.logger.success("✓ Docling conversion complete")

            # 3. Export markdown
            self.logger.info("Exporting to markdown...")
            markdown_text = doc.export_to_markdown()
            self.logger.success(f"✓ Markdown exported ({len(markdown_text):,} chars)")

            # 4. Export structured JSON dict
            self.logger.info("Exporting to structured JSON...")
            doc_json = doc.export_to_dict()
            self.logger.success("✓ JSON structure exported")

            # 5. Count pages
            # Docling stores page count in the document metadata
            num_pages = len(doc.pages) if hasattr(doc, 'pages') else doc_json.get('page_count', 0)
            self.logger.info(f"  Total pages: {num_pages}")

            # 6. Save outputs to files for inspection
            self._save_outputs(pdf_path.stem, markdown_text, doc_json)

            # 7. Return ParseResult
            self.logger.success(f"✓ Parse complete: {num_pages} pages, {len(markdown_text):,} chars")

            return ParseResult(
                doc_json=doc_json,
                md_text=markdown_text,
                num_pages=num_pages,
                parser_version=DOCLING_VERSION,
            )

        except Exception as e:
            self.logger.error(f"Docling parsing failed: {e}")
            self.logger.exception("Full traceback:")
            raise RuntimeError(f"Docling parsing failed: {e}") from e

    def _save_outputs(self, base_name: str, markdown: str, doc_json: dict) -> None:
        """
        Save markdown and JSON outputs to data/docling_outputs/.

        Args:
            base_name: Base filename (without extension)
            markdown: Markdown text to save
            doc_json: JSON dict to save
        """
        # Save markdown
        md_path = self._output_dir / f"{base_name}_docling.md"
        try:
            md_path.write_text(markdown, encoding="utf-8")
            self.logger.success(f"✓ Saved markdown: {md_path}")
        except Exception as e:
            self.logger.warning(f"Could not save markdown: {e}")

        # Save JSON
        json_path = self._output_dir / f"{base_name}_docling.json"
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(doc_json, f, indent=2, ensure_ascii=False)
            self.logger.success(f"✓ Saved JSON: {json_path}")
        except Exception as e:
            self.logger.warning(f"Could not save JSON: {e}")
