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

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat

VLM_AVAILABLE = True  # VLM is available in Docling 2.0+

from src.utils.logging_config import logger
from src.config import DOCLING_VERSION, USE_DOCLING_VLM, DOCLING_VLM_MODEL, DOCLING_TABLE_MODE
from src.parsers.base import BaseParser, ParseResult


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
        Initialize Docling parser with configuration.

        Configuration options:
        - VLM (Vision Language Model): Enhanced image understanding with picture descriptions
        - Table mode: "fast" or "accurate" for table extraction
        - OCR enabled via Tesseract for scanned pages
        - Automatic multi-page table reconstruction
        """
        super().__init__()
        self.logger.info(f"Initializing Docling parser (version {DOCLING_VERSION})")

        # Track whether VLM was actually enabled and which model
        self._vlm_enabled = False
        self._vlm_model = "None"

        try:
            if USE_DOCLING_VLM and DOCLING_VLM_MODEL != "DEFAULT":
                self.logger.info(f"VLM requested: {DOCLING_VLM_MODEL}")
                self.logger.warning("VLM mode will significantly increase processing time (3-5x slower)")

                # Import VLM pipeline components
                from docling.pipeline.vlm_pipeline import VlmPipeline
                from docling.datamodel.pipeline_options import VlmPipelineOptions
                from docling.datamodel import vlm_model_specs

                # Map model name to vlm_model_specs
                model_map = {
                    "GRANITEDOCLING_TRANSFORMERS": vlm_model_specs.GRANITEDOCLING_TRANSFORMERS,
                    "GRANITEDOCLING_MLX": vlm_model_specs.GRANITEDOCLING_MLX,
                    "SMOLDOCLING_TRANSFORMERS": vlm_model_specs.SMOLDOCLING_TRANSFORMERS,
                    "SMOLDOCLING_MLX": vlm_model_specs.SMOLDOCLING_MLX,
                }

                if DOCLING_VLM_MODEL not in model_map:
                    self.logger.warning(f"Unknown VLM model '{DOCLING_VLM_MODEL}', using GRANITEDOCLING_MLX")
                    vlm_options = vlm_model_specs.GRANITEDOCLING_MLX
                else:
                    vlm_options = model_map[DOCLING_VLM_MODEL]

                self.logger.info(f"✓ VLM model selected: {DOCLING_VLM_MODEL}")

                # Create VLM pipeline options
                pipeline_options = VlmPipelineOptions(vlm_options=vlm_options)

                # Create PDF format options with VLM pipeline
                pdf_options = PdfFormatOption(
                    pipeline_cls=VlmPipeline,
                    pipeline_options=pipeline_options,
                )

                # Create converter with VLM pipeline
                self._converter = DocumentConverter(
                    format_options={InputFormat.PDF: pdf_options}
                )

                self._vlm_enabled = True
                self._vlm_model = DOCLING_VLM_MODEL
                self.logger.success(f"✓ Docling DocumentConverter initialized with {DOCLING_VLM_MODEL}")

            elif USE_DOCLING_VLM and DOCLING_VLM_MODEL == "DEFAULT":
                # Legacy VLM configuration (old behavior)
                self.logger.info(f"VLM requested with DEFAULT (legacy) configuration")
                self.logger.warning("VLM mode will significantly increase processing time (3-5x slower)")

                # Create PdfFormatOption with legacy VLM settings
                pdf_options = PdfFormatOption()

                # Get existing pipeline options and modify them
                pipeline_opts = pdf_options.pipeline_options

                # Enable VLM picture description
                pipeline_opts.do_picture_description = True
                pipeline_opts.do_picture_classification = True
                self.logger.info("✓ VLM picture description enabled")

                # Configure table structure mode
                from docling.datamodel.pipeline_options import TableFormerMode
                if DOCLING_TABLE_MODE == "accurate":
                    pipeline_opts.table_structure_options.mode = TableFormerMode.ACCURATE
                    self.logger.info("✓ Table extraction: accurate mode")
                else:
                    pipeline_opts.table_structure_options.mode = TableFormerMode.FAST
                    self.logger.info("✓ Table extraction: fast mode")

                # Ensure table structure and OCR are enabled
                pipeline_opts.do_table_structure = True
                pipeline_opts.do_ocr = True

                # Create converter with custom options
                self._converter = DocumentConverter(
                    format_options={InputFormat.PDF: pdf_options}
                )

                self._vlm_enabled = True
                self._vlm_model = "DEFAULT (legacy)"
                self.logger.success("✓ Docling DocumentConverter initialized with VLM (legacy mode)")

            else:
                # Use default configuration (no VLM)
                self.logger.info("Using default parsing mode (VLM disabled)")
                self._converter = DocumentConverter()
                self._vlm_enabled = False
                self._vlm_model = "None"
                self.logger.success("✓ Docling DocumentConverter initialized (default mode)")

        except Exception as e:
            self.logger.error(f"Failed to initialize Docling: {e}")
            self.logger.exception("Full traceback:")
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

            # 4. Export structured JSON dict with table markdown
            self.logger.info("Exporting to structured JSON...")
            doc_json = doc.export_to_dict()

            # Add pipeline metadata (VLM settings, version, etc.)
            import datetime
            if 'pipeline_metadata' not in doc_json:
                doc_json['pipeline_metadata'] = {}

            doc_json['pipeline_metadata'].update({
                'vlm_enabled': self._vlm_enabled,
                'vlm_model': self._vlm_model,
                'table_mode': DOCLING_TABLE_MODE if self._vlm_enabled else 'default',
                'docling_version': DOCLING_VERSION,
                'parsed_at': datetime.datetime.now().isoformat(),
            })
            self.logger.info(f"✓ Pipeline metadata added (VLM: {self._vlm_model})")

            # Add formatted markdown for tables
            if 'tables' in doc_json:
                self.logger.info(f"Adding markdown export for {len(doc_json['tables'])} tables...")
                for i, table_item in enumerate(doc.tables):
                    try:
                        # Export table to markdown using Docling's built-in method (pass doc to avoid deprecation warning)
                        table_markdown = table_item.export_to_markdown(doc=doc)
                        # Add to the corresponding table in JSON
                        if i < len(doc_json['tables']):
                            doc_json['tables'][i]['markdown'] = table_markdown
                    except Exception as e:
                        self.logger.warning(f"Could not export table {i} to markdown: {e}")

                self.logger.success("✓ Table markdown added")

            self.logger.success("✓ JSON structure exported")

            # 5. Count pages
            # Docling stores page count in the document metadata
            num_pages = len(doc.pages) if hasattr(doc, 'pages') else doc_json.get('page_count', 0)
            self.logger.info(f"  Total pages: {num_pages}")

            # 6. Save outputs to files for inspection
            self._save_outputs(pdf_path.stem, markdown_text, doc_json)

            # 7. Log VLM status
            if self._vlm_enabled:
                self.logger.success(f"✓ VLM was ENABLED for this parse (model: {self._vlm_model})")
            else:
                self.logger.info("ℹ VLM was DISABLED for this parse (default mode)")

            # 8. Return ParseResult
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
