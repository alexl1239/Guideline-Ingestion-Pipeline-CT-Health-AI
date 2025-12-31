"""
Unit Tests for src.utils.segmentation.hierarchy_builder

Tests hierarchy construction and section identification logic.
"""

import pytest
from src.utils.segmentation.hierarchy_builder import (
    identify_chapters,
    identify_diseases_from_toc,
    identify_numbered_subsections_from_toc,
    identify_standard_subsections_from_headers,
    build_heading_path,
    assign_blocks_to_sections,
    build_complete_hierarchy,
)


class TestIdentifyChapters:
    """Tests for identify_chapters()"""

    def test_identify_with_toc(self):
        """Identify chapters from ToC entries"""
        headers = []
        toc = [
            {'heading': 'Emergencies', 'page': 10, 'level': 1, 'numbering': '1'},
            {'heading': 'Infectious Diseases', 'page': 50, 'level': 1, 'numbering': '2'},
        ]

        chapters = identify_chapters(headers, toc)

        assert len(chapters) == 2
        assert chapters[0]['level'] == 1
        assert chapters[0]['heading'] == '1 Emergencies'
        assert chapters[0]['page_start'] == 10
        assert chapters[0]['numbering'] == '1'
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

    def test_infer_missing_chapter(self):
        """Infer missing chapter from orphan level 2 entries"""
        headers = [
            {'id': 1, 'text_content': '9 Mental Disorders', 'page_number': 100},
        ]
        toc = [
            {'heading': 'Emergencies', 'page': 10, 'level': 1, 'numbering': '1'},
            # No chapter 9 explicitly, but there's a 9.1 entry
            {'heading': 'Neurological Disorders', 'page': 100, 'level': 2, 'numbering': '9.1'},
        ]

        chapters = identify_chapters(headers, toc)

        # Should infer chapter 9
        chapter_nums = [c.get('numbering') for c in chapters]
        assert '9' in chapter_nums


class TestIdentifyDiseasesFromToc:
    """Tests for identify_diseases_from_toc()"""

    def test_identify_from_toc(self):
        """Identify diseases from Level 2 ToC entries"""
        chapters = [
            {
                'level': 1,
                'heading': '1 Emergencies',
                'page_start': 10,
                'page_end': 100,
                'numbering': '1',
            },
        ]
        toc = [
            {'heading': 'Emergencies', 'page': 10, 'level': 1, 'numbering': '1'},
            {'heading': 'Common Emergencies', 'page': 15, 'level': 2, 'numbering': '1.1'},
            {'heading': 'Trauma', 'page': 50, 'level': 2, 'numbering': '1.2'},
        ]

        diseases = identify_diseases_from_toc(toc, chapters)

        assert len(diseases) == 2
        assert diseases[0]['heading'] == '1.1 Common Emergencies'
        assert diseases[0]['level'] == 2
        assert diseases[0]['numbering'] == '1.1'
        assert diseases[0]['page_start'] == 15
        assert diseases[1]['heading'] == '1.2 Trauma'

    def test_page_end_from_next_disease(self):
        """Disease page_end comes from next disease's page"""
        chapters = [
            {
                'level': 1,
                'heading': '1 Emergencies',
                'page_start': 10,
                'page_end': 100,
                'numbering': '1',
            },
        ]
        toc = [
            {'heading': 'Disease A', 'page': 15, 'level': 2, 'numbering': '1.1'},
            {'heading': 'Disease B', 'page': 25, 'level': 2, 'numbering': '1.2'},
        ]

        diseases = identify_diseases_from_toc(toc, chapters)

        assert diseases[0]['page_end'] == 24  # One before next disease
        assert diseases[1]['page_end'] == 100  # End of chapter

    def test_infer_missing_disease(self):
        """Infer missing Level 2 from orphan Level 3 entries"""
        chapters = [
            {
                'level': 1,
                'heading': '4 Cardiovascular',
                'page_start': 100,
                'page_end': 200,
                'numbering': '4',
            },
        ]
        toc = [
            # No 4.1 entry, jumps to 4.1.1
            {'heading': 'DVT', 'page': 110, 'level': 3, 'numbering': '4.1.1'},
            {'heading': 'Heart Failure', 'page': 120, 'level': 3, 'numbering': '4.1.2'},
        ]

        diseases = identify_diseases_from_toc(toc, chapters)

        # Should infer 4.1
        assert len(diseases) == 1
        assert diseases[0]['numbering'] == '4.1'
        assert '(Inferred' in diseases[0]['heading']

    def test_deduplicate_diseases(self):
        """Remove duplicate diseases by numbering"""
        chapters = [
            {
                'level': 1,
                'heading': '1 Emergencies',
                'page_start': 10,
                'page_end': 100,
                'numbering': '1',
            },
        ]
        toc = [
            {'heading': 'Disease A', 'page': 15, 'level': 2, 'numbering': '1.1'},
            {'heading': 'Disease A Duplicate', 'page': 16, 'level': 2, 'numbering': '1.1'},
        ]

        diseases = identify_diseases_from_toc(toc, chapters)

        # Should keep only first occurrence
        assert len(diseases) == 1
        assert diseases[0]['heading'] == '1.1 Disease A'


class TestIdentifyNumberedSubsectionsFromToc:
    """Tests for identify_numbered_subsections_from_toc()"""

    def test_identify_level_3_subsections(self):
        """Identify Level 3 subsections from ToC"""
        parent_chapter = {
            'level': 1,
            'heading': '1 Emergencies',
            'page_start': 10,
            'page_end': 100,
            'numbering': '1',
        }
        diseases = [
            {
                'level': 2,
                'heading': '1.1 Common Emergencies',
                'page_start': 15,
                'page_end': 50,
                'numbering': '1.1',
                'parent_chapter': parent_chapter,
            },
        ]
        toc = [
            {'heading': 'Anaphylaxis', 'page': 20, 'level': 3, 'numbering': '1.1.1'},
            {'heading': 'Shock', 'page': 30, 'level': 3, 'numbering': '1.1.2'},
        ]

        subsections = identify_numbered_subsections_from_toc(toc, diseases)

        assert len(subsections) == 2
        assert subsections[0]['heading'] == '1.1.1 Anaphylaxis'
        assert subsections[0]['level'] == 3
        assert subsections[0]['numbering'] == '1.1.1'

    def test_identify_level_4_subsections(self):
        """Identify Level 4 subsections from ToC"""
        parent_chapter = {
            'level': 1,
            'heading': '1 Emergencies',
            'page_start': 10,
            'page_end': 100,
            'numbering': '1',
        }
        diseases = [
            {
                'level': 2,
                'heading': '1.1 Common Emergencies',
                'page_start': 15,
                'page_end': 50,
                'numbering': '1.1',
                'parent_chapter': parent_chapter,
            },
        ]
        toc = [
            {'heading': 'Dehydration in Children', 'page': 25, 'level': 4, 'numbering': '1.1.3.1'},
        ]

        subsections = identify_numbered_subsections_from_toc(toc, diseases)

        assert len(subsections) == 1
        assert subsections[0]['level'] == 4


class TestIdentifyStandardSubsectionsFromHeaders:
    """Tests for identify_standard_subsections_from_headers()"""

    def test_identify_standard_subsections(self):
        """Identify standard clinical subsections from headers"""
        headers = [
            {'id': 1, 'text_content': 'Causes', 'page_number': 16},
            {'id': 2, 'text_content': 'Clinical features', 'page_number': 17},
            {'id': 3, 'text_content': 'Management', 'page_number': 18},
        ]
        diseases = [
            {
                'level': 2,
                'heading': '1.1 Disease',
                'page_start': 15,
                'page_end': 25,
            },
        ]
        numbered_subsections = []

        subsections = identify_standard_subsections_from_headers(
            headers, diseases, numbered_subsections
        )

        assert len(subsections) == 3
        assert subsections[0]['heading'] == 'Causes'
        assert subsections[0]['level'] == 3  # Parent is level 2, so this is level 3
        assert subsections[0]['subsection_type'] == 'causes'

    def test_subsection_level_under_numbered_section(self):
        """Standard subsections under numbered sections get correct level"""
        headers = [
            {'id': 1, 'text_content': 'Management', 'page_number': 26},
        ]
        parent_disease = {
            'level': 2,
            'heading': '1.1 Disease',
            'page_start': 15,
            'page_end': 35,
        }
        diseases = [parent_disease]
        numbered_subsections = [
            {
                'level': 3,
                'heading': '1.1.1 Subsection',
                'page_start': 25,
                'page_end': 30,
                'parent_disease': parent_disease,
            },
        ]

        subsections = identify_standard_subsections_from_headers(
            headers, diseases, numbered_subsections
        )

        assert len(subsections) == 1
        # Should be level 4 (under level 3 numbered subsection)
        assert subsections[0]['level'] == 4


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
            'heading': '1.1 Common Emergencies',
            'parent_chapter': chapter,
        }

        path = build_heading_path(disease)

        assert path == 'Emergencies > 1.1 Common Emergencies'

    def test_subsection_path(self):
        """Subsection path includes chapter and disease"""
        chapter = {'heading': 'Emergencies'}
        disease = {
            'heading': '1.1 Common Emergencies',
            'parent_chapter': chapter,
        }
        subsection = {
            'level': 3,
            'heading': 'Management',
            'parent_disease': disease,
        }

        path = build_heading_path(subsection)

        assert path == 'Emergencies > 1.1 Common Emergencies > Management'

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
            {'id': 2, 'text_content': 'Definition', 'page_number': 16},
            {'id': 3, 'text_content': 'Management', 'page_number': 17},
        ]
        toc = [
            {'heading': 'Emergencies', 'page': 10, 'level': 1, 'numbering': '1'},
            {'heading': 'Common Emergencies', 'page': 15, 'level': 2, 'numbering': '1.1'},
        ]

        hierarchy = build_complete_hierarchy(headers, toc)

        # Should have: 1 chapter, 1 disease, 2 standard subsections = 4 total
        assert len(hierarchy) >= 3

        # Check hierarchy levels
        levels = [s['level'] for s in hierarchy]
        assert 1 in levels  # Has chapter
        assert 2 in levels  # Has disease

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
