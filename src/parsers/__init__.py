"""
Parser Module for UCG-23 RAG ETL Pipeline

Provides parser implementations for converting PDFs into structured formats.
Currently includes Docling (offline, open-source parser by IBM).
"""

from src.parsers.base import BaseParser, ParseResult
from src.parsers.docling_parser import DoclingParser

__all__ = [
    "BaseParser",
    "ParseResult",
    "DoclingParser",
]
