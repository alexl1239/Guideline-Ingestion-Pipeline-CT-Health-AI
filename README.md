# Clinical Guidelines RAG ETL Pipeline

A document-agnostic production ETL pipeline that converts clinical guideline PDFs into portable SQLite databases with vector search capabilities for offline RAG applications.

## Overview

This pipeline transforms clinical guideline PDFs (such as the Uganda Clinical Guidelines 2023) into structured, searchable SQLite databases optimized for Retrieval-Augmented Generation (RAG) systems. The output is a single, portable `.db` file that can be used fully offline for clinical decision support.

### Key Features

- **Document-agnostic**: Works with any clinical guideline PDF
- **Fully offline**: No API keys required for parsing (uses Docling)
- **Single database output**: Complete knowledge base in one portable file
- **Vector search**: Built-in semantic search using `sqlite-vec`
- **Hierarchical structure**: Preserves document organization (chapters → sections → subsections)
- **Production-ready**: Transactional pipeline with error handling and resumability
- **Clinically accurate**: Strict constraints to prevent factual changes during processing

## Quick Start

### Prerequisites

```bash
# Python 3.11+
python --version

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup

Create a `.env` file in the project root:

```bash
# Required for embeddings (Step 6)
OPENAI_API_KEY=your_openai_api_key_here

# Optional: for Claude-based table conversion (Step 4)
CLAUDE_API_KEY=your_claude_api_key_here
```

### Configuration

Edit `src/config.py` to select your document:

```python
# Set the active document to process
ACTIVE_PDF = "Your_Clinical_Guideline.pdf"

# Configure VLM (Vision Language Model) for enhanced accuracy
USE_DOCLING_VLM = True                      # Enable for complex layouts (3-5x slower)
DOCLING_VLM_MODEL = "GRANITEDOCLING_TRANSFORMERS"  # Model selection (see VLM Configuration section)
DOCLING_TABLE_MODE = "accurate"             # "fast" or "accurate"
```

### Running the Pipeline

Place your PDF in `data/source_pdfs/`, then:

```bash
# Run full pipeline
python -m src.main --all

# Or run individual steps (0-8)
python -m src.main --step 0  # Document registration
python -m src.main --step 1  # Parsing with Docling
python -m src.main --step 2  # Structural segmentation
python -m src.main --step 3  # Cleanup and parent chunks
python -m src.main --step 4  # Table linearization
python -m src.main --step 5  # Child chunking
python -m src.main --step 6  # Embeddings
python -m src.main --step 7  # QA validation
python -m src.main --step 8  # Database export
```

The output database will be created as `data/Your_Clinical_Guideline_rag.db`

## Pipeline Architecture

### 8-Step ETL Process

1. **Document Registration** - Compute checksums and register source PDF
2. **Parsing** - Extract content using Docling (offline PDF parser)
3. **Structural Segmentation** - Build hierarchical section structure
4. **Cleanup & Parent Chunks** - Normalize content and create topic-level chunks
5. **Table Linearization** - Convert tables to natural language
6. **Child Chunking** - Split into retrieval-optimized chunks (256 tokens)
7. **Embeddings** - Generate vectors using OpenAI `text-embedding-3-small`
8. **Export & Validation** - Optimize database and run QA checks

### Database Schema

```
documents                    # Source metadata and checksums
├── sections                 # Hierarchical structure
│   └── raw_blocks          # Parsed content with native labels
└── parent_chunks           # Complete clinical topics (1000-1500 tokens)
    └── child_chunks        # Retrieval units (256 tokens)
        └── vec_child_chunks # Vector embeddings (sqlite-vec)
```

### RAG Query Pattern

The pipeline implements a parent-child retrieval pattern:
- **Search** on child chunks (256 tokens) for precise matching
- **Return** parent chunks (1000-1500 tokens) to LLM for complete context
- This prevents duplication and ensures coherent clinical information

## Working with Multiple Documents

The pipeline supports processing multiple clinical guidelines, with each generating its own database.

### File Structure

```
data/
  source_pdfs/                    # All source PDFs
    Guideline_A.pdf
    Guideline_B.pdf

  Guideline_A_rag.db              # Generated databases
  Guideline_B_rag.db
```

### Switching Documents

1. Edit `src/config.py`:
   ```python
   ACTIVE_PDF = "Your_Guideline.pdf"
   ```

2. Run the pipeline:
   ```bash
   python -m src.main --all
   ```

Each document gets its own database file (auto-named from PDF filename).

## VLM Configuration

Docling supports optional Vision Language Model (VLM) processing for enhanced document understanding:

```python
# In src/config.py
USE_DOCLING_VLM = True                           # Enable/disable VLM
DOCLING_VLM_MODEL = "GRANITEDOCLING_TRANSFORMERS"  # Model selection
DOCLING_TABLE_MODE = "accurate"                  # "fast" or "accurate"
```

### Available VLM Models

| Model | Size | Hardware | Speed | Accuracy | Status |
|-------|------|----------|-------|----------|--------|
| **GRANITEDOCLING_TRANSFORMERS** | 258M | CPU/CUDA | Moderate | Excellent | ✅ **Recommended** |
| GRANITEDOCLING_MLX | 258M | Apple Silicon | Fast | Excellent | ⚠️ Requires dependency updates |
| SMOLDOCLING_TRANSFORMERS | 256M | CPU/CUDA | Fast | Very Good | Experimental |
| SMOLDOCLING_MLX | 256M | Apple Silicon | Very Fast | Very Good | ⚠️ Requires dependency updates |
| DEFAULT | - | Any | Slow | Good | Legacy mode |

**Current Recommendation**: Use `GRANITEDOCLING_TRANSFORMERS` - production-ready with current dependencies.

### VLM Trade-offs

| Feature | VLM Enabled | VLM Disabled |
|---------|-------------|--------------|
| **Processing Speed** | 3-5x slower | Baseline |
| **Table Accuracy** | Excellent | Good |
| **Complex Layouts** | Excellent | Good |
| **Picture Descriptions** | Yes | No |
| **Use Case** | Production runs | Testing/iteration |

### MLX Support (Apple Silicon)

MLX models provide GPU acceleration on Apple Silicon Macs (M1/M2/M3), but require newer package versions that are currently incompatible with Docling 2.64.0:

```
⚠️ Dependency Conflict:
- MLX requires: transformers >= 5.0
- Docling 2.64.0 requires: transformers < 5.0
```

**Resolution Options**:
1. **Wait for Docling update**: Future Docling versions will support transformers 5.x
2. **Use TRANSFORMERS model**: Works now with excellent accuracy (CPU-based)
3. **Manual workaround**: Advanced users can resolve dependencies manually (not recommended)

**Recommendation**: Use `GRANITEDOCLING_TRANSFORMERS` for production. MLX support will be available when Docling is updated.

## Testing and Development

For fast iteration during development, use a smaller test document:

```python
# In src/config.py
ACTIVE_PDF = "Small_Test_Guideline.pdf"  # e.g., 100-200 pages
USE_DOCLING_VLM = False                   # Faster testing
```

**Processing Time Examples**:
- Small document (100 pages) with VLM disabled: ~30 seconds
- Large document (1000 pages) with VLM enabled: ~30-50 minutes

## Database Inspection

```bash
# Find your database
ls -lh data/*_rag.db

# Check structure
sqlite3 "data/Your_Guideline_rag.db" ".tables"
sqlite3 "data/Your_Guideline_rag.db" ".schema"

# Verify content
sqlite3 "data/Your_Guideline_rag.db" "SELECT * FROM documents;"
sqlite3 "data/Your_Guideline_rag.db" "SELECT level, heading FROM sections LIMIT 10;"
sqlite3 "data/Your_Guideline_rag.db" "SELECT COUNT(*) FROM parent_chunks;"
sqlite3 "data/Your_Guideline_rag.db" "SELECT COUNT(*) FROM child_chunks;"
```

## Project Structure

```
├── data/
│   ├── source_pdfs/          # Input PDFs
│   ├── *_rag.db             # Output databases
│   └── intermediate/         # Processing artifacts
├── docs/                     # Documentation
│   ├── CLAUDE.md            # Instructions for Claude Code
│   ├── architecture.md       # System architecture
│   ├── Extraction_Process_v3.md  # Detailed ETL design
│   ├── HIERARCHY_EVOLUTION.md    # Hierarchy extraction evolution
│   └── IMPROVEMENTS_SUMMARY.md   # Recent improvements
├── src/
│   ├── config.py            # Configuration
│   ├── main.py              # Pipeline orchestrator
│   ├── database/            # Schema and connections
│   ├── parsers/             # Docling parser
│   ├── pipeline/            # Steps 0-8
│   └── utils/               # Utilities
├── tests/                    # Test suite
├── .env                     # API keys (not committed)
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Key Technologies

- **Docling**: Offline PDF parser (no API key required)
- **SQLite + sqlite-vec**: Database with vector search
- **OpenAI Embeddings**: `text-embedding-3-small` (1536 dimensions)
- **tiktoken**: Token counting (cl100k_base encoding)
- **loguru**: Structured logging

## Troubleshooting

### VLM Import Errors

**Problem**: `ImportError: cannot import name 'AutoModelForVision2Seq'` or `mlx-vlm is not installed`

**Cause**: Dependency version conflicts between VLM models and Docling

**Solution**:
1. Change model in `src/config.py`:
   ```python
   DOCLING_VLM_MODEL = "GRANITEDOCLING_TRANSFORMERS"
   ```

2. Reinstall correct dependencies:
   ```bash
   pip install --force-reinstall "transformers>=4.42.0,<5.0.0" "huggingface-hub>=0.23,<1.0"
   ```

### Slow Processing

**Problem**: VLM processing is very slow

**Solutions**:
- **For testing**: Disable VLM (`USE_DOCLING_VLM = False`)
- **For production**: Keep VLM enabled but be patient (3-5x slower is normal)
- **Future**: MLX support will provide Apple Silicon acceleration

### Memory Issues

**Problem**: Process killed or out of memory

**Solutions**:
- Process smaller documents first
- Reduce batch sizes in `src/config.py`
- Close other applications
- MLX models (when available) will use less memory
