"""
Unit Tests for src.utils.heading_patterns

Tests pattern matching, level inference, and heading classification logic
for structural segmentation.
"""

import pytest
from src.utils.segmentation.heading_patterns import (
    extract_numbered_heading,
    infer_level_from_numbering,
    is_chapter_heading,
    is_standard_subsection,
    score_heading_candidate,
    normalize_heading_text,
    get_heading_confidence_category,
)


class TestExtractNumberedHeading:
    """Tests for extract_numbered_heading()"""

    def test_single_level_numbering(self):
        """Extract single-level numbering"""
        result = extract_numbered_heading("1 Introduction")
        assert result == ("1", "Introduction")

    def test_two_level_numbering(self):
        """Extract two-level numbering"""
        result = extract_numbered_heading("1.2 Background")
        assert result == ("1.2", "Background")

    def test_three_level_numbering(self):
        """Extract three-level numbering (disease level)"""
        result = extract_numbered_heading("1.1.1 Anaphylactic Shock")
        assert result == ("1.1.1", "Anaphylactic Shock")

    def test_four_level_numbering(self):
        """Extract four-level numbering"""
        result = extract_numbered_heading("1.2.3.4 Subsection")
        assert result == ("1.2.3.4", "Subsection")

    def test_with_extra_whitespace(self):
        """Handle extra whitespace"""
        result = extract_numbered_heading("  1.2.3   Anaphylactic Shock  ")
        assert result == ("1.2.3", "Anaphylactic Shock")

    def test_no_numbering(self):
        """Return None for non-numbered text"""
        result = extract_numbered_heading("Introduction")
        assert result is None

    def test_empty_string(self):
        """Return None for empty string"""
        result = extract_numbered_heading("")
        assert result is None

    def test_none_input(self):
        """Return None for None input"""
        result = extract_numbered_heading(None)
        assert result is None


class TestInferLevelFromNumbering:
    """Tests for infer_level_from_numbering()"""

    def test_level_1_chapter(self):
        """Single digit is level 1 (chapter)"""
        assert infer_level_from_numbering("1") == 1
        assert infer_level_from_numbering("2") == 1

    def test_level_2_disease(self):
        """Two levels is level 2 (disease/topic)"""
        assert infer_level_from_numbering("1.1") == 2
        assert infer_level_from_numbering("2.3") == 2

    def test_level_3_subsection(self):
        """Three levels is level 3 (subsection)"""
        assert infer_level_from_numbering("1.1.1") == 3
        assert infer_level_from_numbering("2.3.4") == 3

    def test_level_4_sub_subsection(self):
        """Four levels is level 4"""
        assert infer_level_from_numbering("1.2.3.4") == 4

    def test_clamped_at_4(self):
        """Deep nesting clamped to level 4"""
        assert infer_level_from_numbering("1.2.3.4.5") == 4
        assert infer_level_from_numbering("1.2.3.4.5.6") == 4

    def test_empty_string(self):
        """Empty string defaults to level 1"""
        assert infer_level_from_numbering("") == 1


class TestIsChapterHeading:
    """Tests for is_chapter_heading()"""

    def test_explicit_chapter_keyword(self):
        """Detect 'Chapter' keyword"""
        assert is_chapter_heading("Chapter 1: Introduction") is True
        assert is_chapter_heading("Chapter 2") is True
        assert is_chapter_heading("CHAPTER 3: EMERGENCIES") is True

    def test_all_caps_long_text(self):
        """Detect all caps chapter titles"""
        assert is_chapter_heading("EMERGENCIES AND TRAUMA") is True
        assert is_chapter_heading("INFECTIOUS DISEASES") is True

    def test_all_caps_short_text(self):
        """Reject short all caps (likely acronyms)"""
        assert is_chapter_heading("ICU") is False
        assert is_chapter_heading("HIV") is False

    def test_roman_numerals(self):
        """Detect Roman numeral chapters"""
        assert is_chapter_heading("I. Introduction") is True
        assert is_chapter_heading("II Background") is True
        assert is_chapter_heading("XII. Advanced Topics") is True

    def test_normal_headings(self):
        """Normal headings are not chapters"""
        assert is_chapter_heading("1.1.1 Anaphylactic Shock") is False
        assert is_chapter_heading("Management") is False
        assert is_chapter_heading("Clinical Features") is False

    def test_empty_string(self):
        """Empty string is not a chapter"""
        assert is_chapter_heading("") is False


class TestIsStandardSubsection:
    """Tests for is_standard_subsection()"""

    def test_definition(self):
        """Detect 'Definition'"""
        is_match, name = is_standard_subsection("Definition")
        assert is_match is True
        assert name == "definition"

    def test_management(self):
        """Detect 'Management'"""
        is_match, name = is_standard_subsection("Management")
        assert is_match is True
        assert name == "management"

    def test_clinical_features(self):
        """Detect multi-word subsections"""
        is_match, name = is_standard_subsection("Clinical Features")
        assert is_match is True
        assert name == "clinical features"

    def test_differential_diagnosis(self):
        """Detect 'Differential Diagnosis'"""
        is_match, name = is_standard_subsection("Differential Diagnosis")
        assert is_match is True
        assert name == "differential diagnosis"

    def test_case_insensitive(self):
        """Case insensitive matching"""
        is_match, name = is_standard_subsection("MANAGEMENT")
        assert is_match is True
        assert name == "management"

        is_match, name = is_standard_subsection("clinical features")
        assert is_match is True

    def test_with_numbering(self):
        """Strip numbering prefix"""
        is_match, name = is_standard_subsection("1.2 Management")
        assert is_match is True
        assert name == "management"

    def test_with_trailing_punctuation(self):
        """Strip trailing punctuation"""
        is_match, name = is_standard_subsection("Management:")
        assert is_match is True

        is_match, name = is_standard_subsection("Definition.")
        assert is_match is True

    def test_non_standard_heading(self):
        """Non-standard headings return False"""
        is_match, name = is_standard_subsection("Random Heading")
        assert is_match is False
        assert name is None

    def test_empty_string(self):
        """Empty string returns False"""
        is_match, name = is_standard_subsection("")
        assert is_match is False
        assert name is None


class TestScoreHeadingCandidate:
    """Tests for score_heading_candidate()"""

    def test_numbered_heading_only(self):
        """Numbered heading gets 40 points"""
        score = score_heading_candidate("1.2.3 Some Heading")
        assert score == 40

    def test_numbered_with_docling_level(self):
        """Numbered + docling_level gets 70 points"""
        score = score_heading_candidate("1.2.3 Some Heading", docling_level=3)
        assert score == 70

    def test_numbered_with_standard_subsection(self):
        """Numbered + standard subsection gets 60 points"""
        score = score_heading_candidate("1.2.3 Management")
        assert score == 60  # +40 numbered, +20 standard

    def test_full_score_combination(self):
        """Numbered + docling + standard gets 90 points"""
        score = score_heading_candidate("1.2.3 Management", docling_level=3)
        assert score == 90  # +40 numbered, +30 docling, +20 standard

    def test_chapter_heading(self):
        """Chapter heading gets points"""
        score = score_heading_candidate("Chapter 1: Introduction")
        assert score == 20  # +20 chapter (doesn't match numbered pattern)

    def test_in_toc_bonus(self):
        """In ToC adds 10 points"""
        score = score_heading_candidate("1.2.3 Management", in_toc=True)
        assert score == 70  # +40 numbered, +20 standard subsection, +10 toc

    def test_capped_at_100(self):
        """Score capped at 100"""
        score = score_heading_candidate(
            "1.2.3 Management",
            docling_level=3,
            in_toc=True
        )
        assert score == 100  # +40 numbered, +30 docling, +20 standard, +10 toc

    def test_empty_string(self):
        """Empty string gets 0"""
        score = score_heading_candidate("")
        assert score == 0


class TestNormalizeHeadingText:
    """Tests for normalize_heading_text()"""

    def test_strip_whitespace(self):
        """Strip leading/trailing whitespace"""
        assert normalize_heading_text("  Hello  ") == "Hello"

    def test_normalize_spaces(self):
        """Normalize multiple spaces"""
        assert normalize_heading_text("1.2.3   Anaphylactic  Shock") == "1.2.3 Anaphylactic Shock"

    def test_standardize_quotes(self):
        """Standardize quotation marks"""
        assert normalize_heading_text('"Hello"') == '"Hello"'
        assert normalize_heading_text("'Hello'") == "'Hello'"

    def test_preserve_numbering(self):
        """Preserve numbering patterns"""
        assert normalize_heading_text("1.2.3 Management") == "1.2.3 Management"

    def test_preserve_capitalization(self):
        """Preserve capitalization"""
        assert normalize_heading_text("EMERGENCY CARE") == "EMERGENCY CARE"

    def test_empty_string(self):
        """Empty string returns empty"""
        assert normalize_heading_text("") == ""

    def test_none_input(self):
        """None input returns empty"""
        assert normalize_heading_text(None) == ""


class TestGetHeadingConfidenceCategory:
    """Tests for get_heading_confidence_category()"""

    def test_high_confidence(self):
        """70-100 is High"""
        assert get_heading_confidence_category(100) == 'High'
        assert get_heading_confidence_category(85) == 'High'
        assert get_heading_confidence_category(70) == 'High'

    def test_medium_confidence(self):
        """40-69 is Medium"""
        assert get_heading_confidence_category(69) == 'Medium'
        assert get_heading_confidence_category(50) == 'Medium'
        assert get_heading_confidence_category(40) == 'Medium'

    def test_low_confidence(self):
        """1-39 is Low"""
        assert get_heading_confidence_category(39) == 'Low'
        assert get_heading_confidence_category(20) == 'Low'
        assert get_heading_confidence_category(1) == 'Low'

    def test_no_confidence(self):
        """0 is None"""
        assert get_heading_confidence_category(0) == 'None'
