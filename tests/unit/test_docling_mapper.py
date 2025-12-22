"""
Unit Tests for src.utils.docling_mapper

Tests individual mapper functions for extracting data from Docling JSON.
"""

import pytest
from src.utils.docling_mapper import (
    extract_page_number,
    extract_page_range,
    extract_text_content,
    extract_markdown_content,
    extract_block_type,
    extract_docling_level,
    extract_bbox,
    extract_element_id,
)


class TestPageNumberExtraction:
    """Tests for extract_page_number()"""

    def test_extract_page_number_docling_2_0(self):
        """Docling 2.0 format with page_no in provenance"""
        element = {
            'prov': [
                {'page_no': 42, 'bbox': {'l': 100, 't': 100, 'r': 200, 'b': 120}}
            ]
        }
        assert extract_page_number(element) == 42

    def test_extract_page_number_legacy_format(self):
        """Legacy format with 'page' instead of 'page_no'"""
        element = {
            'prov': [
                {'page': 15, 'bbox': {}}
            ]
        }
        assert extract_page_number(element) == 15

    def test_extract_page_number_direct_field(self):
        """Page number in direct field"""
        element = {'page_no': 99}
        assert extract_page_number(element) == 99

    def test_extract_page_number_missing(self):
        """Returns None when page number not found"""
        element = {'text': 'Some content'}
        assert extract_page_number(element) is None

    def test_extract_page_number_empty_prov(self):
        """Returns None with empty provenance"""
        element = {'prov': []}
        assert extract_page_number(element) is None


class TestPageRangeExtraction:
    """Tests for extract_page_range()"""

    def test_extract_page_range_multipage(self):
        """Multi-page element (e.g., table spanning pages 12-14)"""
        element = {
            'prov': [
                {'page_no': 12, 'bbox': {}},
                {'page_no': 13, 'bbox': {}},
                {'page_no': 14, 'bbox': {}}
            ]
        }
        assert extract_page_range(element) == "12-14"

    def test_extract_page_range_single_page(self):
        """Single-page element returns None"""
        element = {
            'prov': [
                {'page_no': 5, 'bbox': {}}
            ]
        }
        assert extract_page_range(element) is None

    def test_extract_page_range_non_sequential(self):
        """Non-sequential pages (should still return min-max)"""
        element = {
            'prov': [
                {'page_no': 10, 'bbox': {}},
                {'page_no': 15, 'bbox': {}},
                {'page_no': 12, 'bbox': {}}
            ]
        }
        assert extract_page_range(element) == "10-15"

    def test_extract_page_range_legacy_format(self):
        """Works with legacy 'page' field"""
        element = {
            'prov': [
                {'page': 20, 'bbox': {}},
                {'page': 21, 'bbox': {}}
            ]
        }
        assert extract_page_range(element) == "20-21"


class TestTextContentExtraction:
    """Tests for extract_text_content()"""

    def test_extract_text_from_text_field(self):
        """Extract from 'text' field"""
        element = {'text': 'This is the content.'}
        assert extract_text_content(element) == 'This is the content.'

    def test_extract_text_from_orig_field(self):
        """Extract from 'orig' field (Docling 2.0)"""
        element = {'orig': 'Original text content'}
        assert extract_text_content(element) == 'Original text content'

    def test_extract_text_from_table_cells(self):
        """Extract text from table cells"""
        element = {
            'label': 'table',
            'data': {
                'table_cells': [
                    {'text': 'Cell 1', 'row_span': 1},
                    {'text': 'Cell 2', 'row_span': 1},
                    {'text': 'Cell 3', 'row_span': 1}
                ]
            }
        }
        result = extract_text_content(element)
        assert 'Cell 1' in result
        assert 'Cell 2' in result
        assert 'Cell 3' in result

    def test_extract_text_preserves_special_chars(self):
        """Medical symbols preserved: °, ±, μ"""
        element = {'text': 'Temperature 38.5°C ± 0.5°C, 100μg dose'}
        result = extract_text_content(element)
        assert '°' in result
        assert '±' in result
        assert 'μ' in result

    def test_extract_text_strips_whitespace(self):
        """Whitespace is stripped"""
        element = {'text': '  Content with spaces  '}
        assert extract_text_content(element) == 'Content with spaces'

    def test_extract_text_empty_returns_none(self):
        """Empty text returns None"""
        element = {'text': '   '}
        assert extract_text_content(element) is None

    def test_extract_text_no_content(self):
        """Element with no content returns None"""
        element = {'label': 'figure'}
        assert extract_text_content(element) is None


class TestBlockTypeExtraction:
    """Tests for extract_block_type()"""

    def test_extract_block_type_from_label(self):
        """Extract block type from 'label' field"""
        test_cases = [
            ({'label': 'section_header'}, 'section_header'),
            ({'label': 'text'}, 'text'),
            ({'label': 'list_item'}, 'list_item'),
            ({'label': 'table'}, 'table'),
            ({'label': 'document_index'}, 'document_index'),
            ({'label': 'page_header'}, 'page_header'),
            ({'label': 'page_footer'}, 'page_footer'),
            ({'label': 'caption'}, 'caption'),
            ({'label': 'picture'}, 'picture'),
        ]

        for element, expected in test_cases:
            assert extract_block_type(element) == expected

    def test_extract_block_type_from_type_field(self):
        """Extract from 'type' field (legacy)"""
        element = {'type': 'paragraph'}
        assert extract_block_type(element) == 'paragraph'

    def test_extract_block_type_defaults_to_unknown(self):
        """Defaults to 'unknown' when not found"""
        element = {'text': 'Some content'}
        assert extract_block_type(element) == 'unknown'


class TestDoclingLevelExtraction:
    """Tests for extract_docling_level()"""

    def test_extract_level_from_section_header(self):
        """Extract level from section_header"""
        element = {
            'label': 'section_header',
            'level': 2,
            'text': '1.1 Introduction'
        }
        assert extract_docling_level(element) == 2

    def test_extract_level_non_header_returns_none(self):
        """Non-header elements return None"""
        element = {
            'label': 'text',
            'text': 'Body content'
        }
        assert extract_docling_level(element) is None

    def test_extract_level_missing_field_returns_none(self):
        """Header without level field returns None"""
        element = {
            'label': 'section_header',
            'text': 'Heading'
        }
        assert extract_docling_level(element) is None


class TestBboxExtraction:
    """Tests for extract_bbox()"""

    def test_extract_bbox_valid(self):
        """Extract valid bounding box"""
        import json
        element = {
            'bbox': {'l': 100, 't': 200, 'r': 400, 'b': 250}
        }
        result = extract_bbox(element)
        assert result is not None

        parsed = json.loads(result)
        assert parsed['l'] == 100
        assert parsed['t'] == 200
        assert parsed['r'] == 400
        assert parsed['b'] == 250

    def test_extract_bbox_missing(self):
        """Returns None when bbox missing"""
        element = {'text': 'Content'}
        assert extract_bbox(element) is None

    def test_extract_bbox_empty(self):
        """Returns None when bbox is empty"""
        element = {'bbox': None}
        assert extract_bbox(element) is None


class TestElementIdExtraction:
    """Tests for extract_element_id()"""

    def test_extract_element_id_from_id_field(self):
        """Extract from 'id' field"""
        element = {'id': 'elem_42'}
        assert extract_element_id(element) == 'elem_42'

    def test_extract_element_id_from_element_id_field(self):
        """Extract from 'element_id' field"""
        element = {'element_id': 'doc_5_para_10'}
        assert extract_element_id(element) == 'doc_5_para_10'

    def test_extract_element_id_prefers_id_over_element_id(self):
        """Prefers 'id' field when both present"""
        element = {'id': 'id_value', 'element_id': 'element_id_value'}
        assert extract_element_id(element) == 'id_value'

    def test_extract_element_id_missing(self):
        """Returns None when not found"""
        element = {'text': 'Content'}
        assert extract_element_id(element) is None


class TestMarkdownContentExtraction:
    """Tests for extract_markdown_content()"""

    def test_extract_markdown_from_markdown_field(self):
        """Extract from 'markdown' field"""
        element = {'markdown': '| Col1 | Col2 |\n|------|------|\n| A | B |'}
        result = extract_markdown_content(element)
        assert result is not None
        assert '| Col1 | Col2 |' in result

    def test_extract_markdown_strips_whitespace(self):
        """Whitespace is stripped"""
        element = {'markdown': '  # Heading  '}
        assert extract_markdown_content(element) == '# Heading'

    def test_extract_markdown_empty_returns_none(self):
        """Empty markdown returns None"""
        element = {'markdown': '   '}
        assert extract_markdown_content(element) is None

    def test_extract_markdown_missing(self):
        """Returns None when markdown field missing"""
        element = {'text': 'Plain text'}
        assert extract_markdown_content(element) is None
