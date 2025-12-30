"""
Heading Pattern Detection Utilities

Provides regex-based pattern matching and level inference for section headings.
Used in Step 2 (Structural Segmentation) to identify and classify headings
from the Uganda Clinical Guidelines.

Key Functions:
- extract_numbered_heading: Extract numbered patterns like "1.2.3"
- infer_level_from_numbering: Determine hierarchy level from numbering
- is_chapter_heading: Detect chapter-level headings
- is_standard_subsection: Match against standard clinical subsections
- score_heading_candidate: Assign confidence score to heading candidates
"""

import re
from typing import Optional, Tuple
from src.utils.logging_config import logger


# Standard clinical subsections commonly found in UCG-23
STANDARD_SUBSECTIONS = {
    'definition': 3,
    'causes': 3,
    'risk factors': 3,
    'clinical features': 3,
    'complications': 3,
    'differential diagnosis': 3,
    'investigations': 3,
    'management': 3,
    'prevention': 3,
    'treatment': 3,
    'diagnosis': 3,
    'symptoms': 3,
    'prognosis': 3,
    'follow-up': 3,
}

# Regex patterns for heading detection
NUMBERED_HEADING_PATTERN = re.compile(r'^\s*(\d+(?:\.\d+)*)\s+(.+)$')
CHAPTER_PATTERN = re.compile(r'^(?:chapter|section|part)\s+\d+', re.IGNORECASE)
ROMAN_NUMERAL_PATTERN = re.compile(r'^[IVXLCDM]+\.?\s+', re.IGNORECASE)


def extract_numbered_heading(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract numbered heading pattern from text.

    Looks for patterns like:
    - "1 Introduction"
    - "1.1 Background"
    - "1.1.1 Anaphylactic Shock"

    Args:
        text: Heading text to parse

    Returns:
        Tuple of (numbering, heading_text) if pattern found, None otherwise

    Example:
        >>> extract_numbered_heading("1.2.3 Anaphylactic Shock")
        ('1.2.3', 'Anaphylactic Shock')
        >>> extract_numbered_heading("Introduction")
        None
    """
    if not text:
        return None

    text = text.strip()
    match = NUMBERED_HEADING_PATTERN.match(text)

    if match:
        numbering = match.group(1)
        heading_text = match.group(2).strip()
        return (numbering, heading_text)

    return None


def infer_level_from_numbering(numbering: str) -> int:
    """
    Infer hierarchy level from numbering pattern.

    Rules:
    - "1" or "2" → Level 1 (Chapter)
    - "1.1" or "2.3" → Level 2 (Disease/Topic)
    - "1.1.1" or "2.3.4" → Level 3 (Subsection)
    - "1.1.1.1" → Level 4 (Sub-subsection)

    Args:
        numbering: Numeric pattern (e.g., "1.2.3")

    Returns:
        Inferred hierarchy level (1-4)

    Example:
        >>> infer_level_from_numbering("1")
        1
        >>> infer_level_from_numbering("1.2.3")
        3
    """
    if not numbering:
        return 1

    # Count dots to determine depth
    depth = numbering.count('.') + 1

    # Clamp to reasonable range (1-4)
    return min(depth, 4)


def is_chapter_heading(text: str) -> bool:
    """
    Detect if text is a chapter-level heading.

    Looks for patterns:
    - "Chapter 1", "Chapter 2"
    - "EMERGENCIES AND TRAUMA" (all caps, >15 chars)
    - Roman numerals: "I. Introduction", "II. Background"

    Args:
        text: Heading text to check

    Returns:
        True if likely a chapter heading

    Example:
        >>> is_chapter_heading("Chapter 1: Introduction")
        True
        >>> is_chapter_heading("EMERGENCIES AND TRAUMA")
        True
        >>> is_chapter_heading("1.1.1 Anaphylactic Shock")
        False
    """
    if not text:
        return False

    text = text.strip()

    # Pattern 1: Explicit "Chapter" keyword
    if CHAPTER_PATTERN.match(text):
        return True

    # Pattern 2: All caps (typically chapter titles)
    # Must be long enough to avoid false positives on acronyms
    if text.isupper() and len(text) > 15:
        return True

    # Pattern 3: Roman numerals
    if ROMAN_NUMERAL_PATTERN.match(text):
        return True

    return False


def is_standard_subsection(text: str) -> Tuple[bool, Optional[str]]:
    """
    Check if text matches a standard clinical subsection.

    Standard subsections:
    - Definition, Causes, Risk factors
    - Clinical features, Complications, Differential diagnosis
    - Investigations, Management, Prevention

    Args:
        text: Heading text to check

    Returns:
        Tuple of (is_match, subsection_type)
        - is_match: True if matches standard subsection
        - subsection_type: Matched subsection name (lowercase) or None

    Example:
        >>> is_standard_subsection("Management")
        (True, 'management')
        >>> is_standard_subsection("Clinical Features")
        (True, 'clinical features')
        >>> is_standard_subsection("Random Heading")
        (False, None)
    """
    if not text:
        return (False, None)

    text_lower = text.strip().lower()

    # Remove common prefixes/suffixes
    text_lower = re.sub(r'^\d+(\.\d+)*\.?\s*', '', text_lower)  # Remove numbering (handles 1, 1.2, 1.2.3, etc.)
    text_lower = text_lower.strip().rstrip(':.')  # Remove trailing punctuation and extra whitespace

    for subsection_name in STANDARD_SUBSECTIONS.keys():
        if text_lower == subsection_name:
            return (True, subsection_name)

    return (False, None)


def score_heading_candidate(
    text: str,
    docling_level: Optional[int] = None,
    in_toc: bool = False
) -> int:
    """
    Assign confidence score to a heading candidate.

    Scoring:
    - +40 points: Has numbered pattern (1.2.3)
    - +30 points: Has docling_level assigned
    - +20 points: Matches standard subsection
    - +20 points: Is chapter heading
    - +10 points: Appears in Table of Contents

    Args:
        text: Heading text
        docling_level: Optional level from Docling parser
        in_toc: Whether heading appears in ToC

    Returns:
        Confidence score (0-100)

    Example:
        >>> score_heading_candidate("1.2.3 Management", docling_level=3)
        90  # +40 numbered, +30 docling, +20 standard subsection
    """
    score = 0

    if not text:
        return score

    # Check for numbered heading pattern
    if extract_numbered_heading(text):
        score += 40

    # Docling assigned a level
    if docling_level is not None:
        score += 30

    # Matches standard subsection
    is_standard, _ = is_standard_subsection(text)
    if is_standard:
        score += 20

    # Is chapter heading
    if is_chapter_heading(text):
        score += 20

    # In Table of Contents
    if in_toc:
        score += 10

    return min(score, 100)  # Cap at 100


def normalize_heading_text(text: str) -> str:
    """
    Normalize heading text for consistent comparison.

    Normalizations:
    - Strip leading/trailing whitespace
    - Remove excessive spaces
    - Standardize quotation marks
    - Preserve numbering and capitalization

    Args:
        text: Raw heading text

    Returns:
        Normalized heading text

    Example:
        >>> normalize_heading_text("  1.2.3   Anaphylactic  Shock  ")
        "1.2.3 Anaphylactic Shock"
    """
    if not text:
        return ""

    # Strip and normalize spaces
    text = ' '.join(text.split())

    # Standardize quotation marks
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")

    return text.strip()


def get_heading_confidence_category(score: int) -> str:
    """
    Categorize confidence score into human-readable category.

    Categories:
    - High (70-100): Very likely a heading
    - Medium (40-69): Probably a heading
    - Low (1-39): Possibly a heading
    - None (0): Not a heading

    Args:
        score: Confidence score from score_heading_candidate

    Returns:
        Category string

    Example:
        >>> get_heading_confidence_category(85)
        'High'
        >>> get_heading_confidence_category(35)
        'Low'
    """
    if score >= 70:
        return 'High'
    elif score >= 40:
        return 'Medium'
    elif score > 0:
        return 'Low'
    else:
        return 'None'


__all__ = [
    'extract_numbered_heading',
    'infer_level_from_numbering',
    'is_chapter_heading',
    'is_standard_subsection',
    'score_heading_candidate',
    'normalize_heading_text',
    'get_heading_confidence_category',
    'STANDARD_SUBSECTIONS',
]
