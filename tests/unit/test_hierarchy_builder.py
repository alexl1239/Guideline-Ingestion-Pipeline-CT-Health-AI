"""
Unit Tests for src.utils.segmentation.hierarchy_builder

Tests hierarchy construction and section identification logic.
"""

import pytest
from src.utils.segmentation.hierarchy_builder import (
    identify_chapters,
    identify_diseases,
    identify_subsections,
    build_heading_path,
    assign_blocks_to_sections,
    build_complete_hierarchy,
)


class TestIdentifyChapters:
    """Tests for identify_chapters()"""

    def test_identify_with_toc_match(self):
        """Identify chapters using ToC matches"""
        headers = [
            {'id': 1, 'text_content': 'CHAPTER 1: EMERGENCIES', 'page_number': 10},
            {'id': 2, 'text_content': 'CHAPTER 2: INFECTIOUS DISEASES', 'page_number': 50},
        ]
        toc = [
            {'heading': 'Emergencies', 'page': 10, 'level': 1},
            {'heading': 'Infectious Diseases', 'page': 50, 'level': 1},
        ]

        chapters = identify_chapters(headers, toc)

        assert len(chapters) == 2
        assert chapters[0]['level'] == 1
        assert chapters[0]['heading'] == 'CHAPTER 1: EMERGENCIES'
        assert chapters[0]['page_start'] == 10
        assert chapters[1]['page_start'] == 50

    def test_identify_without_toc(self):
        """Fallback to pattern-based detection without ToC"""
        headers = [
            {'id': 1, 'text_content': 'Chapter 1: Introduction', 'page_number': 1},
            {'id': 2, 'text_content': '1.1.1 Some Disease', 'page_number': 5},
        ]
        toc = []

        chapters = identify_chapters(headers, toc)

        assert len(chapters) == 1
        assert chapters[0]['heading'] == 'Chapter 1: Introduction'

    def test_identify_empty_input(self):
        """Handle empty inputs gracefully"""
        chapters = identify_chapters([], [])
        assert chapters == []


class TestIdentifyDiseases:
    """Tests for identify_diseases()"""

    def test_identify_numbered_diseases(self):
        """Identify disease sections with numbering"""
        headers = [
            {'id': 1, 'text_content': '1.1 Disease A', 'page_number': 15},
            {'id': 2, 'text_content': '1.2 Disease B', 'page_number': 20},
            {'id': 3, 'text_content': 'Definition', 'page_number': 21},  # Subsection, not disease
        ]
        chapter = {
            'level': 1,
            'heading': 'Chapter 1',
            'page_start': 10,
            'page_end': 30,
            'header_block_id': 999,
        }

        diseases = identify_diseases(headers, chapter, [])

        assert len(diseases) == 2
        assert diseases[0]['heading'] == '1.1 Disease A'
        assert diseases[0]['level'] == 2
        assert diseases[0]['numbering'] == '1.1'
        assert diseases[1]['heading'] == '1.2 Disease B'

    def test_adjust_page_ranges(self):
        """Disease page_end adjusted to next disease start"""
        headers = [
            {'id': 1, 'text_content': '1.1 Disease A', 'page_number': 15},
            {'id': 2, 'text_content': '1.2 Disease B', 'page_number': 25},
        ]
        chapter = {
            'level': 1,
            'heading': 'Chapter 1',
            'page_start': 10,
            'page_end': 40,
            'header_block_id': 999,
        }

        diseases = identify_diseases(headers, chapter, [])

        assert diseases[0]['page_end'] == 24  # One before next disease
        assert diseases[1]['page_end'] == 40  # End of chapter


class TestIdentifySubsections:
    """Tests for identify_subsections()"""

    def test_identify_standard_subsections(self):
        """Identify standard clinical subsections"""
        headers = [
            {'id': 1, 'text_content': 'Definition', 'page_number': 16},
            {'id': 2, 'text_content': 'Clinical features', 'page_number': 17},
            {'id': 3, 'text_content': 'Management', 'page_number': 18},
        ]
        disease = {
            'level': 2,
            'heading': '1.1.1 Anaphylactic Shock',
            'page_start': 15,
            'page_end': 20,
            'header_block_id': 999,
        }

        subsections = identify_subsections(headers, disease)

        assert len(subsections) == 3
        assert subsections[0]['heading'] == 'Definition'
        assert subsections[0]['level'] == 3
        assert subsections[0]['subsection_type'] == 'definition'
        assert subsections[1]['subsection_type'] == 'clinical features'
        assert subsections[2]['subsection_type'] == 'management'

    def test_identify_numbered_subsections(self):
        """Identify numbered subsections"""
        headers = [
            {'id': 1, 'text_content': '1.1.1 Subsection A', 'page_number': 16},
            {'id': 2, 'text_content': '1.1.2 Subsection B', 'page_number': 17},
        ]
        disease = {
            'level': 2,
            'heading': '1.1 Disease',
            'page_start': 15,
            'page_end': 20,
            'header_block_id': 999,
        }

        subsections = identify_subsections(headers, disease)

        assert len(subsections) == 2
        assert subsections[0]['level'] == 3
        assert subsections[0]['numbering'] == '1.1.1'


class TestBuildHeadingPath:
    """Tests for build_heading_path()"""

    def test_chapter_path(self):
        """Chapter has simple path"""
        chapter = {
            'level': 1,
            'heading': 'Chapter 1: Emergencies',
        }

        path = build_heading_path(chapter)

        assert path == 'Chapter 1: Emergencies'

    def test_disease_path(self):
        """Disease path includes chapter"""
        chapter = {'heading': 'Emergencies'}
        disease = {
            'level': 2,
            'heading': '1.1.1 Anaphylactic Shock',
            'parent_chapter': chapter,
        }

        path = build_heading_path(disease)

        assert path == 'Emergencies > 1.1.1 Anaphylactic Shock'

    def test_subsection_path(self):
        """Subsection path includes chapter and disease"""
        chapter = {'heading': 'Emergencies'}
        disease = {
            'heading': '1.1.1 Anaphylactic Shock',
            'parent_chapter': chapter,
        }
        subsection = {
            'level': 3,
            'heading': 'Management',
            'parent_disease': disease,
        }

        path = build_heading_path(subsection)

        assert path == 'Emergencies > 1.1.1 Anaphylactic Shock > Management'

    def test_orphan_subsection(self):
        """Subsection without parents falls back gracefully"""
        subsection = {
            'level': 3,
            'heading': 'Management',
        }

        path = build_heading_path(subsection)

        assert path == 'Management'


class TestAssignBlocksToSections:
    """Tests for assign_blocks_to_sections()"""

    def test_assign_blocks_to_sections(self):
        """Assign blocks based on page number"""
        blocks = [
            {'id': 1, 'page_number': 15, 'block_type': 'text'},
            {'id': 2, 'page_number': 16, 'block_type': 'text'},
            {'id': 3, 'page_number': 20, 'block_type': 'text'},
            {'id': 4, 'page_number': 21, 'block_type': 'page_header'},  # Should skip
        ]
        sections = [
            {'level': 2, 'page_start': 15, 'page_end': 19, 'header_block_id': 999},
            {'level': 2, 'page_start': 20, 'page_end': 25, 'header_block_id': 998},
        ]

        mapping = assign_blocks_to_sections(blocks, sections)

        # Should have 2 sections with blocks assigned
        assert len(mapping) == 2

        # Check that page_header was excluded
        total_assigned = sum(len(ids) for ids in mapping.values())
        assert total_assigned == 3  # 3 text blocks, not 4

    def test_assign_prefers_most_specific_section(self):
        """Prefer subsection over disease over chapter"""
        blocks = [
            {'id': 1, 'page_number': 16, 'block_type': 'text'},
        ]
        sections = [
            {'level': 1, 'page_start': 10, 'page_end': 30},  # Chapter
            {'level': 2, 'page_start': 15, 'page_end': 20},  # Disease
            {'level': 3, 'page_start': 16, 'page_end': 17},  # Subsection (most specific)
        ]

        mapping = assign_blocks_to_sections(blocks, sections)

        # Should assign to level 3 (subsection)
        # Find which section got the block
        assigned_sections = [s for s in sections if id(s) in mapping]
        assert len(assigned_sections) == 1
        assert assigned_sections[0]['level'] == 3


class TestBuildCompleteHierarchy:
    """Tests for build_complete_hierarchy()"""

    def test_build_complete_hierarchy(self):
        """Build full hierarchy from headers and ToC"""
        headers = [
            {'id': 1, 'text_content': 'Chapter 1: Emergencies', 'page_number': 10},
            {'id': 2, 'text_content': '1.1 Anaphylaxis', 'page_number': 15},
            {'id': 3, 'text_content': 'Definition', 'page_number': 16},
            {'id': 4, 'text_content': 'Management', 'page_number': 17},
        ]
        toc = [
            {'heading': 'Emergencies', 'page': 10, 'level': 1},
        ]

        hierarchy = build_complete_hierarchy(headers, toc)

        # Should have: 1 chapter, 1 disease, 2 subsections = 4 total
        assert len(hierarchy) >= 3

        # Check hierarchy levels
        levels = [s['level'] for s in hierarchy]
        assert 1 in levels  # Has chapter
        assert 2 in levels  # Has disease
        assert 3 in levels  # Has subsections

        # Check heading paths are built
        for section in hierarchy:
            assert 'heading_path' in section
            assert len(section['heading_path']) > 0

        # Check order is sequential
        orders = [s['order_index'] for s in hierarchy]
        assert orders == list(range(1, len(hierarchy) + 1))

    def test_empty_inputs(self):
        """Handle empty inputs gracefully"""
        hierarchy = build_complete_hierarchy([], [])
        assert hierarchy == []
