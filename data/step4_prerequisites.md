# Step 4 Prerequisites: Decisions and Actions Before Implementation

**Date**: 2026-03-23

---

## Current State of Tables

- **25 tables** extracted across the iCCM document
- 8 small (<3KB), 13 medium (3-10KB), 4 large (>10KB)
- 12 of 38 parent chunks already contain tables wrapped in `[TABLE]...[/TABLE]` tags
- Step 4 is currently a placeholder (no implementation)

### Table Quality Assessment

The table markdown from Docling is **usable but not clean**. Most tables have correct row/column structure. The issues are cosmetic, not structural:

| Issue | Affected Tables | Severity |
|-------|----------------|----------|
| Missing spaces in headers (`DELIVEREDBYICCMVHTS`, `iCCMM&E`) | 6 of 25 | Low — fixable with simple preprocessing |
| HTML entities (`&amp;` instead of `&`) | Same 6 | Low — trivial decode |
| Repeated merged-header rows (e.g. cost table repeats header text across 13 columns) | 1 (table 954) | Low — large table, keep-as-markdown candidate anyway |
| Simple list-as-table (materials, tools) | 4-5 small tables | Low — LLM can handle these easily |

**Bottom line: the table markdown is not too messy to proceed.** The structural data (rows, columns, pipes) is intact. The issues are limited to header text quality in 6 tables, which can be fixed with a preprocessing step before LLM linearization.

---

## Decisions Needed

### 1. Pipeline Ordering: Should Step 4 run before or after Step 3?

Currently Step 3 runs first and wraps tables in `[TABLE]...[/TABLE]` inside parent chunks. Step 4 then needs to either:

**Option A — Step 4 runs BEFORE Step 3 (recommended)**
- Step 4 reads table blocks from `raw_blocks`, linearizes them, and writes the result back to `raw_blocks.text_content` (or a new field)
- Step 3 then picks up the linearized text naturally during chunk construction
- Pro: Step 3 remains the single point of chunk construction. No double-processing.
- Con: Requires re-running Step 3 after Step 4. Adds a linearized content field or repurposes `text_content`.

**Option B — Step 4 runs AFTER Step 3**
- Step 4 finds `[TABLE]...[/TABLE]` blocks in `parent_chunks.content` and replaces them with linearized text
- Pro: No need to re-run Step 3.
- Con: Step 4 now modifies parent chunks directly, breaking the clean ownership model. Token counts become stale. Harder to re-run Step 3 independently.

**Decision needed**: Which option? Option A is cleaner for a multi-document pipeline.

### 2. Test Document: Should you validate against iCCM or UCG-23?

The iCCM tables are operational/administrative:
- Stakeholder matrices
- M&E indicator tables
- Cost scaling tables
- Training materials lists
- Reporting timeframes

The Step 4 spec references clinically critical tables:
- Vaccine schedules
- Emergency dosing protocols
- Level of Care (LOC) code tables

**These only exist in UCG-23.** The automated validation checks (dose patterns, age ranges, numeric integrity) can't be built or tested against iCCM.

**Options**:
- (a) Build the basic linearization framework against iCCM (fast iteration), then validate the clinical-specific logic against UCG-23
- (b) Switch to UCG-23 now and build everything against the real target

Option (a) is pragmatic — the LLM prompt design and small/large table routing work the same regardless of content.

### 3. Linearize vs. Summarize: Where is the threshold?

The CLAUDE.md spec says:
- Small tables (<50 rows, <10 columns): LLM linearization
- Large tables (>50 rows or >10 columns): Keep markdown + add summary

Current table sizes in iCCM:

| Category | Count | Examples |
|----------|-------|---------|
| Clearly small (< 20 rows) | 14 | Materials lists, tool references, small status tables |
| Medium (20-50 rows) | 7 | M&E indicators, performance indicators, cost breakdowns |
| Borderline/large (50+ rows) | 4 | Annex M&E workplan tables (52-66 rows), cost scaling table |

**Decision needed**: Are you comfortable with the 50-row / 10-column thresholds from the spec, or do you want to adjust based on what you see? The 4 large annex tables are unlikely to linearize well regardless.

### 4. What to do with list-as-table blocks?

Several "tables" are really just lists formatted as tables:
- Table 939 (page 23): Training materials a) through h)
- Table 938 (page 18): Single row of tools
- Table 940 (page 26): Single row with "VHT strategy"

These don't need LLM linearization — they're already readable. Options:
- (a) Pass them through the LLM anyway (simpler code, slightly wasteful)
- (b) Detect trivially simple tables (≤2 columns, ≤10 rows, no numeric data) and just clean the markdown directly
- (c) Don't special-case them, treat uniformly

---

## Actions Before Starting Step 4

### Required (blocking)

1. **Decide pipeline ordering** (Decision 1 above)
   - If Option A: add a `linearized_content` column to `raw_blocks`, or decide to write to `text_content`
   - If Option B: plan how Step 4 patches parent chunks and refreshes token counts

2. **Add table markdown preprocessing** to clean Docling output before LLM ingestion:
   - Decode HTML entities (`&amp;` → `&`)
   - Split known concatenated header patterns (detect CamelCase-like runs in ALL-CAPS headers)
   - Strip duplicate merged-header rows
   - This is ~20 lines of code in a `normalize_table_markdown()` utility

### Recommended (not blocking but valuable)

3. **Design the LLM prompt** for table linearization
   - The CLAUDE.md spec already has a prompt template — review and refine it
   - Consider including the section `heading_path` as context so the LLM knows the clinical domain
   - Test it manually against 2-3 iCCM tables before automating

4. **Run Step 1 on UCG-23** to have the clinical tables available for validation
   - This takes 5-10 minutes but gives you the real test data for dose/age/LOC validation
   - Can happen in parallel with building the framework against iCCM

### Not needed yet (do during implementation)

5. Automated validation scripts for dose patterns and numeric integrity (build alongside linearization)
6. Traceability linking (linearized text → original table block ID) — design during implementation
