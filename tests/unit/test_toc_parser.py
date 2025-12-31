"""
Unit Tests for src.utils.toc_parser

Tests Table of Contents extraction and parsing from Docling JSON.
"""

import pytest
from src.utils.segmentation.toc_parser import (
    parse_toc_entry,
    infer_toc_level,
    validate_toc_entries,
    get_toc_summary,
    extract_toc_from_docling,
)


class TestParseTocEntry:
    """Tests for parse_toc_entry()"""

    def test_parse_with_dotted_leaders(self):
        """Parse ToC entry with dotted leaders"""
        entry = parse_toc_entry("1.2.3 Anaphylactic Shock ......... 45")
        assert entry is not None
        assert entry['heading'] == "Anaphylactic Shock"
        assert entry['page'] == 45
        assert entry['level'] == 3
        assert entry['numbering'] == "1.2.3"

    def test_parse_with_spaces(self):
        """Parse ToC entry with multiple spaces"""
        entry = parse_toc_entry("Introduction    12")
        assert entry is not None
        assert entry['heading'] == "Introduction"
        assert entry['page'] == 12
        # Unnumbered entries default to level 2 (not chapters)
        assert entry['level'] == 2

    def test_parse_chapter_with_colon(self):
        """Parse chapter entry with colon"""
        entry = parse_toc_entry("Chapter 2: Infectious Diseases ... 100")
        assert entry is not None
        assert entry['heading'] == "Chapter 2: Infectious Diseases"
        assert entry['page'] == 100

    def test_parse_numbered_without_page(self):
        """Parse numbered entry without page number"""
        entry = parse_toc_entry("1.2 Background")
        assert entry is not None
        assert entry['heading'] == "Background"
        assert entry['page'] is None
        assert entry['level'] == 2
        assert entry['numbering'] == "1.2"

    def test_parse_unnumbered_without_page(self):
        """Unnumbered entry without page returns None"""
        entry = parse_toc_entry("Some Random Text")
        assert entry is None

    def test_parse_empty_string(self):
        """Empty string returns None"""
        entry = parse_toc_entry("")
        assert entry is None

    def test_parse_short_string(self):
        """Very short string returns None"""
        entry = parse_toc_entry("Ab")
        assert entry is None

    def test_parse_complex_numbering(self):
        """Parse entry with complex numbering"""
        entry = parse_toc_entry("2.3.4.1 Sub-subsection ........ 250")
        assert entry is not None
        assert entry['heading'] == "Sub-subsection"
        assert entry['page'] == 250
        assert entry['level'] == 4
        assert entry['numbering'] == "2.3.4.1"


class TestInferTocLevel:
    """Tests for infer_toc_level()"""

    def test_level_1_single_digit(self):
        """Single digit is level 1"""
        assert infer_toc_level("1") == 1
        assert infer_toc_level("5") == 1

    def test_level_2_two_segments(self):
        """Two segments is level 2"""
        assert infer_toc_level("1.1") == 2
        assert infer_toc_level("2.5") == 2

    def test_level_3_three_segments(self):
        """Three segments is level 3"""
        assert infer_toc_level("1.2.3") == 3
        assert infer_toc_level("5.10.2") == 3

    def test_level_4_four_segments(self):
        """Four segments is level 4"""
        assert infer_toc_level("1.2.3.4") == 4

    def test_clamped_at_4(self):
        """Deep nesting clamped to level 4"""
        assert infer_toc_level("1.2.3.4.5") == 4
        assert infer_toc_level("1.2.3.4.5.6.7") == 4

    def test_none_returns_2(self):
        """None returns level 2 (not a chapter)"""
        assert infer_toc_level(None) == 2

    def test_empty_string_returns_2(self):
        """Empty string returns level 2 (not a chapter)"""
        assert infer_toc_level("") == 2


class TestValidateTocEntries:
    """Tests for validate_toc_entries()"""

    def test_valid_toc(self):
        """Valid ToC passes validation"""
        entries = [
            {'heading': 'Chapter 1', 'page': 10, 'level': 1},
            {'heading': '1.1 Section', 'page': 15, 'level': 2},
            {'heading': '1.2 Section', 'page': 20, 'level': 2},
            {'heading': 'Chapter 2', 'page': 30, 'level': 1},
        ]
        assert validate_toc_entries(entries) is True

    def test_too_few_entries(self):
        """Too few entries fails validation"""
        entries = [
            {'heading': 'Chapter 1', 'page': 10, 'level': 1},
        ]
        assert validate_toc_entries(entries) is False

    def test_no_level_1_entries(self):
        """No level 1 entries fails validation"""
        entries = [
            {'heading': '1.1 Section', 'page': 10, 'level': 2},
            {'heading': '1.2 Section', 'page': 15, 'level': 2},
            {'heading': '1.3 Section', 'page': 20, 'level': 2},
        ]
        assert validate_toc_entries(entries) is False

    def test_descending_pages(self):
        """Descending page numbers fails validation"""
        entries = [
            {'heading': 'Chapter 1', 'page': 100, 'level': 1},
            {'heading': 'Section', 'page': 50, 'level': 2},
            {'heading': 'Chapter 2', 'page': 10, 'level': 1},
        ]
        assert validate_toc_entries(entries) is False

    def test_missing_pages_passes(self):
        """Missing page numbers is acceptable"""
        entries = [
            {'heading': 'Chapter 1', 'page': None, 'level': 1},
            {'heading': 'Section', 'page': None, 'level': 2},
            {'heading': 'Chapter 2', 'page': None, 'level': 1},
            {'heading': 'Chapter 3', 'page': None, 'level': 1},
        ]
        assert validate_toc_entries(entries) is True


class TestGetTocSummary:
    """Tests for get_toc_summary()"""

    def test_summary_with_entries(self):
        """Generate summary with entries"""
        entries = [
            {'heading': 'Ch 1', 'level': 1},
            {'heading': '1.1', 'level': 2},
            {'heading': '1.2', 'level': 2},
            {'heading': '1.2.1', 'level': 3},
        ]
        summary = get_toc_summary(entries)
        assert "4 entries" in summary
        assert "Level 1: 1 entries" in summary
        assert "Level 2: 2 entries" in summary
        assert "Level 3: 1 entries" in summary

    def test_summary_empty(self):
        """Generate summary with no entries"""
        summary = get_toc_summary([])
        assert "No entries found" in summary


class TestExtractTocFromDocling:
    """Tests for extract_toc_from_docling()"""

    def test_extract_with_explicit_toc(self):
        """Extract ToC when explicit ToC section exists"""
        docling_json = {
            'texts': [
                {
                    'text': 'Table of Contents',
                    'label': 'section_header',
                    'prov': [{'page_no': 1}]
                },
                {
                    'text': '1 Introduction ......... 10',
                    'label': 'text',
                    'prov': [{'page_no': 1}]
                },
                {
                    'text': '2 Chapter Two ......... 20',
                    'label': 'text',
                    'prov': [{'page_no': 1}]
                },
                {
                    'text': '2.1 Section A ......... 25',
                    'label': 'text',
                    'prov': [{'page_no': 1}]
                },
                {
                    'text': '2.2 Section B ......... 30',
                    'label': 'text',
                    'prov': [{'page_no': 1}]
                },
                {
                    'text': '3 Chapter Three ......... 40',
                    'label': 'text',
                    'prov': [{'page_no': 1}]
                },
                {
                    'text': '4 Chapter Four ......... 50',
                    'label': 'text',
                    'prov': [{'page_no': 2}]
                },
                # End marker
                {
                    'text': 'Introduction',
                    'label': 'section_header',
                    'prov': [{'page_no': 10}]
                },
            ]
        }

        toc = extract_toc_from_docling(docling_json)

        assert len(toc) >= 6  # Should find at least 6 entries
        assert toc[0]['heading'] == 'Introduction'
        assert toc[0]['page'] == 10
        assert toc[1]['heading'] == 'Chapter Two'

    def test_extract_fallback_to_section_headers(self):
        """Fall back to section headers when no explicit ToC"""
        docling_json = {
            'texts': [
                {
                    'text': '1 Introduction',
                    'label': 'section_header',
                    'prov': [{'page_no': 10}]
                },
                {
                    'text': 'Some content',
                    'label': 'text',
                    'prov': [{'page_no': 10}]
                },
                {
                    'text': '2 Chapter Two',
                    'label': 'section_header',
                    'prov': [{'page_no': 20}]
                },
                {
                    'text': '2.1 Section',
                    'label': 'section_header',
                    'prov': [{'page_no': 25}]
                },
            ]
        }

        toc = extract_toc_from_docling(docling_json)

        assert len(toc) == 3
        assert toc[0]['heading'] == 'Introduction'
        assert toc[0]['page'] == 10
        assert toc[0]['level'] == 1
        assert toc[2]['heading'] == 'Section'
        assert toc[2]['level'] == 2

    def test_extract_empty_docling_json(self):
        """Handle empty Docling JSON gracefully"""
        toc = extract_toc_from_docling({})
        assert toc == []

    def test_extract_no_texts(self):
        """Handle Docling JSON without texts"""
        toc = extract_toc_from_docling({'texts': []})
        assert toc == []
