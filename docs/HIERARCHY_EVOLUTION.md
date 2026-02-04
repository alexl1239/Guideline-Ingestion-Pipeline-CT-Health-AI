# Hierarchy Extraction: Evolution from ToC Parsing to Native Docling

## Overview

This document explains the architectural evolution of section hierarchy extraction in the UCG-23 ETL pipeline, from fragile ToC-based parsing to robust native Docling hierarchy extraction.

---

## Phase 1: ToC-Based Approach (Before c877960)

### Architecture

**Files Involved:**
- `src/utils/segmentation/toc_parser.py` (~600 lines)
- `src/utils/segmentation/hierarchy_builder.py` (~800 lines)
- `src/utils/segmentation/heading_patterns.py` (pattern matching)

**Process:**
1. **Extract ToC from Docling JSON**
   - Search for explicit Table of Contents section
   - Parse ToC entries with regex patterns for page numbers
   - Fall back to section header extraction if no ToC found

2. **Apply Page Offset Correction**
   - Detect offset between printed page numbers (in ToC) and PDF page numbers
   - Search document for chapter headers to calculate offset
   - Apply correction to all ToC page numbers

3. **Build Hierarchy from ToC**
   - Match ToC entries to header blocks by page number and fuzzy text matching
   - Infer missing chapters from "orphan" level-2 entries
   - Manually construct parent-child relationships

4. **Handle Edge Cases**
   - Missing chapters (e.g., level-2 entries without parent chapter)
   - OCR errors in ToC text
   - Misaligned page numbers
   - ToC entries that don't match actual document structure

### Problems

#### 1. **Fragile Page Offset Logic**
```python
# Old approach: Complex page offset detection
def _apply_page_offset(toc_entries, docling_json):
    # Find first chapter in ToC
    # Search for same chapter in document
    # Calculate offset: actual_page - toc_page
    # Apply to all entries
```
- Broke when chapter headers weren't found
- Failed on documents with non-standard numbering
- Required fuzzy text matching (error-prone)

#### 2. **ToC-Dependent**
- Required explicit Table of Contents section
- Failed on documents without ToC or with non-standard ToC format
- ToC text often had OCR errors (e.g., "23.2.4" → "23.24" or "232.4")

#### 3. **Complex Fuzzy Matching**
```python
# Old approach: Match ToC to headers by text similarity
if text_words == heading_words or \
   (len(text_words) >= 2 and text_words[:2] == heading_words[:2]):
    # This is probably a match...
```
- False positives from similar headings
- Missed matches due to OCR errors or formatting differences
- Section 23.2.4 bug: matched wrong section due to fuzzy logic

#### 4. **Lots of Code**
- ~1400 lines of complex logic
- Difficult to debug and maintain
- Many document-specific patterns and heuristics

---

## Phase 2: Native Hierarchy Approach (Commit c877960)

### Architecture Shift

**NEW File:**
- `src/utils/segmentation/native_hierarchy.py` (~550 lines)

**REMOVED Files:**
- `src/utils/segmentation/toc_parser.py` ❌
- Most of `src/utils/segmentation/hierarchy_builder.py` ❌

**Net Result:** ~100 fewer lines of code, much simpler logic

### New Process

1. **Extract Section Headers from Docling JSON**
   ```python
   # Get all section_header elements directly
   headers = doc_json.get('texts', [])
   section_headers = [e for e in headers if e.get('type') == 'section_header']
   ```

2. **Trust Docling's Native Level Field**
   ```python
   # Original Phase 2 approach (before today's fix)
   native_level = element.get('level')
   if native_level is not None and native_level > 0:
       level = native_level  # Trust Docling
   else:
       level = _infer_level_from_numbering(heading_text)  # Fallback
   ```

3. **Build Hierarchy from Native Levels**
   - No ToC parsing needed
   - No page offset calculation needed
   - No fuzzy text matching needed
   - Direct hierarchy construction

### Benefits

✅ **No ToC Dependency**
- Works on any document, with or without ToC
- No OCR errors from ToC parsing

✅ **No Page Offset Issues**
- Docling provides actual PDF page numbers directly
- No offset detection or correction needed

✅ **Document-Agnostic**
- Works across different guideline formats
- No document-specific patterns required

✅ **Simpler Codebase**
- ~100 fewer lines of code
- Easier to understand and maintain
- Fewer edge cases to handle

### Remaining Issue

⚠️ **VLM Native Level Bug**
When VLM is enabled, Docling sometimes assigns ALL section headers to `level=1`, even for obvious sub-sections like "1.1 CONTEXT" or "2.3.4 Disease Name".

---

## Phase 3: Hybrid Approach (Today's Fix - Commit 1444839)

### The Problem

With VLM enabled in commit c877960:
```sql
-- All 139 sections assigned level 1 ❌
SELECT docling_level, COUNT(*) FROM raw_blocks
WHERE block_type = 'section_header'
GROUP BY docling_level;

-- Result: 139 | 1
```

This broke Step 3, which requires level-2 sections to create parent chunks.

### The Solution

**Modified:** `src/utils/segmentation/native_hierarchy.py:281-294`

Changed from "trust native level first" to "trust numbering first":

```python
# NEW APPROACH (Hybrid Strategy)
# Prioritize numbering inference over native level

inferred_level = _infer_level_from_numbering(heading_text)

if inferred_level:
    # Use numbering-based level (most reliable)
    # "1.1 CONTEXT" → level 2
    # "23.2.4 Disease" → level 3
    level = inferred_level
elif native_level is not None and native_level > 0:
    # Fallback to Docling's native level
    level = native_level
else:
    # No numbering and no native level: infer from context
    level = min(last_seen_level + 1, 5)
```

### Why This Works

1. **Numbering is Ground Truth**
   - Document authors explicitly encode hierarchy in numbering
   - "1.1" unambiguously means level 2 (chapter 1, section 1)
   - "23.2.4" unambiguously means level 3 (chapter 23, disease 2, subsection 4)

2. **Native Level as Fallback**
   - Use Docling's level for unnumbered sections (like "Introduction", "Tool Kit")
   - Best of both worlds: trust explicit numbering, fall back to layout analysis

3. **Robust to VLM Issues**
   - VLM incorrectly sets all levels to 1? No problem, use numbering
   - VLM disabled? Numbering still works
   - Non-standard documents? Numbering handles most cases

### Results

After today's fix:
```sql
-- Proper hierarchy! ✅
SELECT level, COUNT(*) FROM sections GROUP BY level;

-- Results:
-- 85 | 1  (chapters)
-- 25 | 2  (topics/diseases)  ← This is what Step 3 needs!
-- 29 | 3  (subsections)
```

---

## Comparison Summary

| Aspect | Phase 1: ToC-Based | Phase 2: Native Only | Phase 3: Hybrid (Current) |
|--------|-------------------|----------------------|---------------------------|
| **Lines of Code** | ~1400 | ~550 | ~550 |
| **ToC Dependency** | ❌ Required | ✅ Not needed | ✅ Not needed |
| **Page Offset Logic** | ❌ Complex | ✅ Not needed | ✅ Not needed |
| **Fuzzy Matching** | ❌ Error-prone | ✅ Not needed | ✅ Not needed |
| **Works with VLM** | N/A | ❌ Broken | ✅ Fixed |
| **Document-Agnostic** | ⚠️ Partial | ✅ Yes | ✅ Yes |
| **Maintainability** | ❌ Complex | ✅ Simple | ✅ Simple |
| **Robustness** | ⚠️ Fragile | ⚠️ VLM-dependent | ✅ Robust |

---

## Key Insights

### What We Learned

1. **Trust Explicit Signals First**
   - Numbering patterns ("1.1", "2.3.4") are explicit hierarchy markers
   - These should override AI-inferred levels

2. **AI/ML as Fallback, Not Primary**
   - VLM is great for complex layout understanding
   - But for numbered documents, numbering is more reliable

3. **Simplicity Wins**
   - Removed ~850 lines of complex ToC parsing logic
   - Result is more robust AND simpler

4. **Progressive Enhancement**
   - Phase 1 → Phase 2: Removed ToC dependency
   - Phase 2 → Phase 3: Fixed VLM issue while maintaining simplicity

### Best Practices Applied

✅ **Prefer Structured Data Over Parsing**
- Use Docling's structured JSON instead of parsing text

✅ **Explicit Over Implicit**
- Trust explicit numbering over inferred levels

✅ **Fallback Chains**
- Try most reliable method first, fall back to others

✅ **Document-Agnostic Design**
- No hardcoded patterns for specific documents

---

## Code Comparison

### Old Approach (Phase 1)
```python
# 1. Extract ToC from document
toc_entries = extract_toc_from_docling(docling_json)

# 2. Apply page offset correction
toc_entries = _apply_page_offset(toc_entries, docling_json)

# 3. Match ToC to headers by fuzzy text matching
chapters = identify_chapters(header_blocks, toc_entries)
diseases = identify_diseases_from_toc(header_blocks, toc_entries)

# 4. Infer missing chapters from orphan entries
chapters = _infer_missing_chapters(chapters, toc_entries, header_blocks)

# 5. Build hierarchy manually
hierarchy = build_complete_hierarchy(chapters, diseases, subsections)
```

### New Approach (Phase 3)
```python
# 1. Extract section headers from Docling JSON
header_elements = _get_section_headers_from_json(doc_json)

# 2. Build hierarchy using numbering + native level fallback
sections = build_section_tree(header_elements)

# 3. Assign page ranges automatically
sections = assign_page_ranges(sections, doc_page_count)

# 4. Build heading paths
sections = build_heading_paths(sections)

# Done! Much simpler.
```

---

## Future Improvements

### Potential Enhancements

1. **Feedback to Docling Team**
   - Report VLM native level bug
   - Suggest hybrid numbering+layout approach

2. **Smarter Numbering Inference**
   - Handle Roman numerals (I, II, III)
   - Handle letter-based numbering (A, B, C)
   - Handle mixed schemes (1.A.i)

3. **Layout-Based Fallback**
   - Use font size/weight when numbering unavailable
   - Indentation-based level inference

4. **Cross-Document Learning**
   - Detect numbering scheme automatically
   - Adapt to document-specific patterns

---

## Conclusion

The evolution from ToC-based to native hierarchy extraction demonstrates the value of:

1. **Trusting structured output** from specialized tools (Docling)
2. **Preferring explicit signals** (numbering) over inferred ones (AI levels)
3. **Simplifying architecture** by eliminating fragile heuristics
4. **Building robust fallback chains** for maximum flexibility

The hybrid approach combines the best of:
- ✅ Document structure (numbering patterns)
- ✅ Layout analysis (Docling's VLM)
- ✅ Heuristic fallbacks (for edge cases)

**Result:** A robust, document-agnostic system that works reliably across different clinical guidelines with minimal code complexity.
