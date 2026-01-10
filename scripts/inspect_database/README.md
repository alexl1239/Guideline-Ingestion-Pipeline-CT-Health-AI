# Database Inspection Scripts

Scripts for inspecting and validating the UCG-23 RAG ETL database.

## Scripts

### list_parent_blocks.py

Inspects the `parent_chunks` table to verify Step 5 (Cleanup and Parent Chunk Formation).

All outputs are written to `scripts/inspect_database/output/` (no terminal output except a single confirmation line).

#### Usage

```bash
# Outline mode (default) - generates outline + stats
python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db

# Dump a specific parent chunk by ID
python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --dump 123

# Export all parent chunks to a single markdown file
python scripts/inspect_database/list_parent_blocks.py --db data/ucg23_rag.db --export
```

#### Output Files

All outputs are written to `scripts/inspect_database/output/`:

| File | Description |
|------|-------------|
| `parent_blocks_outline.md` | Outline grouped by level-2 sections with chunk metadata |
| `parent_blocks_stats.json` | Summary statistics (counts, token distribution, violations) |
| `parent_chunk_<id>.md` | Single chunk dump (when using `--dump`) |
| `parent_chunks_all.md` | All chunks exported in order (when using `--export`) |

#### What to Check

1. **Outline** (`parent_blocks_outline.md`):
   - All level-2 sections should have parent chunks
   - No `[OVER LIMIT]` flags (chunks > 2000 tokens)

2. **Stats** (`parent_blocks_stats.json`):
   - `chunks_over_2000_tokens.count` should be 0
   - `empty_content_chunks.count` should be 0
   - `null_token_count_chunks.count` should be 0
   - Token distribution should be in target range (1000-1500)

3. **Export** (`parent_chunks_all.md`):
   - Open in VS Code for manual spot-checking
   - Verify clinical content is preserved and readable
   - Check for gaps or duplications

## Step 5 Verification

This script helps verify:
- Parent chunks cover full clinical content without gaps or duplications
- No parent chunk exceeds 2,000 token hard limit
- Clinical content is preserved and readable
- Token counts are stored correctly
