# Hierarchy & VLM Tracking Improvements - Summary

## Date: 2026-02-02

## Issues Addressed

### 1. VLM Native Level Bug
**Problem**: When VLM was enabled, Docling set ALL section headers to level=1, causing Step 3 to fail (no level-2 sections).

**Solution**: Changed hierarchy logic to **prioritize numbering patterns** over VLM native level:
- "1.1 CONTEXT" → level 2 (from numbering)
- "Step 1:" → increment from context
- Unnumbered sections → use VLM level as fallback

**Files Modified**:
- `src/utils/segmentation/native_hierarchy.py`

---

### 2. False Level-1 Sections
**Problem**: 85 level-1 sections, including obvious subsections like "Step 1:", "a)", "b)"

**Solution**: Added pattern detection helpers:
- `_is_front_matter()` - ToC, foreword, acknowledgements → force level-1
- `_is_likely_subsection()` - "Step N:", "a)", "b)" → increment from context
- Context-aware fallback logic when VLM says level-1 but we're deep in content

**Result**:
- **Before**: 85 level-1, 25 level-2, 29 level-3
- **After**: 38 level-1, 25 level-2, 34 level-3, 42 level-4

---

### 3. VLM Tracking

**Problem**: No way to tell if a document was parsed with VLM enabled or disabled.

**Solution**: Added pipeline metadata to Docling JSON:
```json
{
  "pipeline_metadata": {
    "vlm_enabled": true,
    "table_mode": "accurate",
    "docling_version": "2.0.0",
    "parsed_at": "2026-02-02T20:48:36.440159"
  }
}
```

**Displayed in**:
- Step 1 logs (parsing)
- Step 2 logs (segmentation)
- Stored in `documents.docling_json`

**Files Modified**:
- `src/parsers/docling_parser.py` (add metadata)
- `src/pipeline/step2_segmentation.py` (display metadata)

---

## Current Status

### Hierarchy Quality: Much Better ✅

**Level-1 Sections (38)**:
- Front matter (6): CONTENTS, ToC, FOREWORD, ACKNOWLEDGEMENTS, Acronyms, Title
- Numbered chapters (12): 1-9 INTRODUCTION through Costing
- End matter (20): Tool Kit, Annexes 1-6 with subsections

**Issues Remaining**:
- ⚠️ "8.2 TERMS OF REFERENCE" incorrectly level-1 (should be level-2)
  - Numbering pattern should match but doesn't
  - Need to debug why "8.2" isn't being detected

### Orphaned Blocks: 65 (4.7%) ⚠️

**Status**: Not yet addressed

**Next Steps**:
1. Investigate why 65 blocks aren't assigned to sections
2. Check if they're:
   - Page headers/footers that should be filtered?
   - Blocks between sections that need better assignment logic?
   - Blocks in front/back matter without clear section boundaries?

**Query to investigate**:
```sql
SELECT block_type, COUNT(*)
FROM raw_blocks
WHERE section_id IS NULL
GROUP BY block_type;
```

---

## Testing Results

### Current Config (src/config.py)
```python
ACTIVE_PDF = "National integrated Community Case Management (iCCM) guidelines.pdf"
USE_DOCLING_VLM = True
DOCLING_TABLE_MODE = "accurate"
```

### Processing Time
- **Step 1 (Parsing)**: ~3 minutes with VLM on iCCM (114 pages)
- **Step 2 (Segmentation)**: <1 second

### Database Stats
- **Total blocks**: 1,393
- **Assigned blocks**: 1,328 (95.3%)
- **Orphaned blocks**: 65 (4.7%)
- **Sections**: 139 (38 L1, 25 L2, 34 L3, 42 L4)

---

## Code Quality Improvements

### Lines of Code Reduced
- **Phase 1 (ToC-based)**: ~1,400 lines
- **Phase 2 (Native hierarchy)**: ~550 lines
- **Phase 3 (Hybrid with VLM fix)**: ~600 lines (added helpers)

### Maintainability
- ✅ No ToC parsing
- ✅ No page offset calculation
- ✅ No fuzzy text matching
- ✅ Document-agnostic patterns
- ✅ Clear fallback chain (numbering → VLM → context)

---

## Next Steps

### High Priority
1. **Fix "8.2 TERMS OF REFERENCE" level detection**
   - Debug numbering regex
   - Check for whitespace or formatting issues

2. **Investigate orphaned blocks**
   - Analyze block types
   - Improve assignment logic if needed
   - Consider filtering page headers/footers

### Medium Priority
3. **Test on full UCG-23 document**
   - 1091 pages vs 114 pages
   - Verify hierarchy logic scales
   - Check VLM processing time (~30-50 min expected)

4. **Enhance numbering inference**
   - Roman numerals (I, II, III)
   - Letter-based (A, B, C or (a), (b))
   - Mixed schemes

### Low Priority
5. **Add VLM metadata to other outputs**
   - Export files (section_tree.md, parent_chunks.md)
   - QA reports
   - Final database metadata table

---

## Files Modified

### Core Changes
1. `src/utils/segmentation/native_hierarchy.py`
   - Added `_is_front_matter()`
   - Added `_is_likely_subsection()`
   - Updated `build_section_tree()` with hybrid logic

2. `src/parsers/docling_parser.py`
   - Added `pipeline_metadata` to Docling JSON

3. `src/pipeline/step2_segmentation.py`
   - Display VLM metadata from Docling JSON

### Documentation
4. `HIERARCHY_EVOLUTION.md` - Full architectural history
5. `IMPROVEMENTS_SUMMARY.md` - This file
6. `CLAUDE.md` - Updated with multi-guideline approach

---

## Conclusion

**Major Win**: Hierarchy extraction is now robust to VLM's incorrect level assignments while still benefiting from VLM's enhanced table extraction and layout analysis.

**Strategy**: Trust explicit document structure (numbering) over AI inference (VLM levels), but use both intelligently with clear fallback chains.

**Result**: Pipeline works correctly with VLM enabled, providing both accuracy and robustness.
