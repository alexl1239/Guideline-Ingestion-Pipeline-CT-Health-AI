"""
Parser Base Classes and Data Structures

Defines the abstract parser interface and result dataclass for the ETL pipeline.

All parser implementations (Docling, etc.) must inherit from BaseParser and
return a ParseResult containing:
- doc_json: Full structured JSON representation
- md_text: Clean markdown output
- num_pages: Total page count
- parser_version: Parser version for reproducibility
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

from src.utils.logging_config import logger


@dataclass
class ParseResult:
    """
    Structured result from PDF parsing.

    Contains all outputs needed for the ETL pipeline:
    - doc_json: Full document structure as JSON-serializable dict
    - md_text: Clean markdown representation of document
    - num_pages: Total number of pages in the PDF
    - parser_version: Version string of the parser for reproducibility

    Example:
        >>> result = parser.parse(pdf_path)
        >>> print(f"Parsed {result.num_pages} pages")
        >>> print(f"Markdown length: {len(result.md_text)} chars")
        >>> print(f"Parser version: {result.parser_version}")
    """

    doc_json: Dict[str, Any]
    md_text: str
    num_pages: int
    parser_version: str

    def __post_init__(self):
        """Validate fields after initialization."""
        if not isinstance(self.doc_json, dict):
            raise TypeError("doc_json must be a dictionary")
        if not isinstance(self.md_text, str):
            raise TypeError("md_text must be a string")
        if not isinstance(self.num_pages, int) or self.num_pages < 1:
            raise ValueError("num_pages must be a positive integer")
        if not isinstance(self.parser_version, str) or not self.parser_version.strip():
            raise ValueError("parser_version must be a non-empty string")


class BaseParser(ABC):
    """
    Abstract base class for PDF parsers.

    All parser implementations must inherit from this class and implement
    the parse() method to convert PDF files into structured ParseResult objects.

    The parser is responsible for:
    1. Loading and reading the PDF file
    2. Extracting text, structure, and metadata
    3. Generating clean markdown output
    4. Producing a structured JSON representation
    5. Reporting version information for reproducibility

    Example:
        >>> class MyParser(BaseParser):
        ...     def parse(self, pdf_path: Path) -> ParseResult:
        ...         # Implementation here
        ...         return ParseResult(...)
        >>> parser = MyParser()
        >>> result = parser.parse(Path("document.pdf"))
    """

    def __init__(self):
        """Initialize the parser."""
        self.logger = logger.bind(parser=self.__class__.__name__)
        self.logger.debug(f"Initialized {self.__class__.__name__}")

    @abstractmethod
    def parse(self, pdf_path: Path) -> ParseResult:
        """
        Parse a PDF file and return structured results.

        This method must be implemented by all parser subclasses. It should:
        1. Validate the input PDF file exists
        2. Load and parse the PDF
        3. Extract text and structure
        4. Generate markdown output
        5. Create structured JSON representation
        6. Return ParseResult with all fields populated

        Args:
            pdf_path: Path to the PDF file to parse

        Returns:
            ParseResult containing doc_json, md_text, num_pages, and parser_version

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            ValueError: If PDF is invalid or corrupt
            RuntimeError: If parsing fails for any other reason

        Example:
            >>> parser = DoclingParser()
            >>> result = parser.parse(Path("data/document.pdf"))
            >>> print(f"Successfully parsed {result.num_pages} pages")
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement parse() method"
        )
