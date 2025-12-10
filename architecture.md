# UCG-23 RAG ETL Pipeline - Architecture Documentation

**Version:** 1.0
**Last Updated:** 2025-12-09

---

## Overview

### High-Level Goal

Convert the Uganda Clinical Guidelines 2023 PDF (~1100 pages) into a single, portable SQLite RAG database (`ucg23_rag.db`) with vector search capabilities for offline clinical decision support.

### Key Characteristics

- **Single Database File**: All content stored in `ucg23_rag.db` with sqlite-vec extension
- **Hierarchical Structure**: Documents → Sections → Parent Chunks → Child Chunks
- **Offline Processing**: Docling parser requires no API calls
- **Transactional Pipeline**: Each step has defined transaction boundaries for resumability
- **Auditability**: Raw parsed data preserved for traceability

### Technology Stack

- **Parser**: Docling (offline, open-source PDF parser by IBM)
- **Database**: SQLite 3 with sqlite-vec extension
- **Embeddings**: OpenAI text-embedding-3-small (1536 dimensions)
- **Tokenization**: tiktoken (cl100k_base encoding)
- **Logging**: loguru (external file logging)
- **LLM**: Claude API (optional, for reconciliation and table conversion)

---

## Project Structure

```
ugc23-rag-etl-pipeline/
├── data/
│   ├── ugc23_raw/                    # Source PDFs
│   ├── intermediate/                 # Processing artifacts
│   ├── exports/                      # Exported data
│   ├── qa_reports/                   # Quality assurance reports
│   └── ucg23_rag.db                  # Output database
│
├── logs/                             # External logging
│   ├── pipeline_*.log                # All messages
│   └── errors_*.log                  # Error-only logs
│
├── scripts/                          # Utility scripts
│   ├── inspect_db.py                 # Database inspection tool
│   ├── query_db.py                   # Query interface
│   └── run_pipeline.sh               # Pipeline execution wrapper
│
├── src/
│   ├── config.py                     # Configuration module
│   ├── main.py                       # Pipeline orchestrator
│   ├── query_engine.py               # RAG query engine
│   │
│   ├── database/                     # Database layer
│   │   ├── schema.py                 # Schema definitions
│   │   └── connections.py            # Connection management
│   │
│   ├── parsers/                      # PDF parsing layer
│   │   ├── base.py                   # Abstract parser interface
│   │   └── docling_parser.py        # Docling implementation
│   │
│   ├── pipeline/                     # ETL pipeline steps (0-8)
│   │   ├── step0_registration.py
│   │   ├── step1_parsing.py
│   │   ├── step2_segmentation.py
│   │   ├── step3_cleanup.py
│   │   ├── step4_tables.py
│   │   ├── step5_chunking.py
│   │   ├── step6_embeddings.py
│   │   ├── step7_qa.py
│   │   └── step8_export.py
│   │
│   └── utils/                        # Utility modules
│       ├── logging_config.py
│       ├── tokenizer.py
│       ├── chunk_splitter.py
│       ├── embedding_generator.py
│       ├── llm_helpers.py
│       ├── table_converter.py
│       └── validation.py
│
├── tests/                            # Test suite
│   ├── unit/
│   ├── integration/
│   └── qa_validation/
│
├── .env                              # Environment variables
├── requirements.txt                  # Python dependencies
├── README.md
├── CLAUDE.md
└── ARCHITECTURE.md
```

---

## Core Modules

### `src/config.py`

**Purpose**: Centralized configuration management. Loads environment variables from `.env` and defines all constants used throughout the pipeline including API keys, model settings, token limits, batch sizes, and file paths.

**Role in System**: Foundation module imported by nearly every other module. Validates configuration on import and exits if required settings are missing.

**Dependencies**: dotenv, pathlib

**Imported By**: All modules

---

### `src/utils/logging_config.py`

**Purpose**: Centralized logging configuration using loguru. Sets up dual file handlers (all messages and errors-only) with automatic rotation, plus colored console output.

**Role in System**: Provides the global logger instance used throughout the application. Must be imported after config to avoid circular dependencies.

**Dependencies**: loguru, src.config

**Imported By**: All modules

---

### `src/database/schema.py`

**Purpose**: Defines and creates the complete SQLite database schema including 7 tables (documents, sections, raw_blocks, parent_chunks, child_chunks, embedding_metadata, vec_child_chunks).

**Role in System**: Creates the database structure before pipeline execution. Loads sqlite-vec extension and validates schema completeness.

**Dependencies**: sqlite3, sqlite_vec, src.config, src.utils.logging_config

**Imported By**: src.database.connections, pipeline steps

---

### `src/database/connections.py`

**Purpose**: Provides thread-safe SQLite connection management with automatic sqlite-vec loading, performance optimizations (WAL mode, caching), and context manager interface.

**Role in System**: Every database operation uses this module's connection context manager. Handles automatic commit/rollback and ensures proper cleanup.

**Dependencies**: sqlite3, sqlite_vec, src.config, src.utils.logging_config, src.database.schema

**Imported By**: All pipeline steps, query_engine

---

### `src/main.py`

**Purpose**: Pipeline orchestrator and main entry point. Initializes logging, validates configuration, creates database schema, and executes pipeline steps in sequence (0-8).

**Role in System**: Coordinates the entire ETL process from start to finish with error handling and progress logging.

**Dependencies**: src.config, src.utils.logging_config, src.database.connections, all pipeline step modules

**Imported By**: None (entry point)

---

### `src/query_engine.py`

**Purpose**: RAG query engine for searching and retrieving clinical information. Generates embeddings for queries, performs vector similarity search on child chunks, and returns parent chunks for LLM context.

**Role in System**: Production interface for querying the completed database. Implements the parent-child retrieval pattern.

**Dependencies**: src.config, src.database.connections, src.utils.embedding_generator, src.utils.logging_config

**Imported By**: External applications

---

## Pipeline Steps

### Step 0: Document Registration
**File**: `src/pipeline/step0_registration.py`

**Purpose**: Registers source PDF in database with SHA-256 checksum and metadata.

**Role**: First step of pipeline. Populates documents and embedding_metadata tables.

**Dependencies**: src.config, src.database.connections, hashlib

---

### Step 1: Parsing
**File**: `src/pipeline/step1_parsing.py`

**Purpose**: Parses PDF using Docling and inserts raw blocks into database.

**Role**: Extracts all content from PDF with native Docling labels. Stores full JSON output for auditability.

**Dependencies**: src.config, src.database.connections, src.parsers.docling_parser

---

### Step 2: Structural Segmentation
**File**: `src/pipeline/step2_segmentation.py`

**Purpose**: Reconstructs logical hierarchy (chapters → diseases → subsections) from raw blocks.

**Role**: Applies regex patterns for numbered headings and identifies standard disease subsections. Uses LLM for problematic areas if needed.

**Dependencies**: src.config, src.database.connections, src.utils.llm_helpers, src.utils.validation

---

### Step 3: Cleanup & Parent Chunks
**File**: `src/pipeline/step3_cleanup.py`

**Purpose**: Cleans raw content and constructs parent chunks (1000-1500 tokens).

**Role**: Removes noise, normalizes text, and concatenates cleaned markdown per section. Splits only at subsection boundaries if needed.

**Dependencies**: src.config, src.database.connections, src.utils.tokenizer, src.utils.chunk_splitter

---

### Step 4: Table Linearization
**File**: `src/pipeline/step4_tables.py`

**Purpose**: Converts tables to natural language prose using LLM.

**Role**: Identifies tables from raw_blocks and converts small tables to readable prose. Large tables stored as markdown with summary.

**Dependencies**: src.config, src.database.connections, src.utils.llm_helpers, src.utils.table_converter, src.utils.validation

---

### Step 5: Child Chunking
**File**: `src/pipeline/step5_chunking.py`

**Purpose**: Splits parent chunks into child chunks (256 tokens) for retrieval.

**Role**: Creates retrieval units with heading context. Respects paragraph boundaries.

**Dependencies**: src.config, src.database.connections, src.utils.tokenizer, src.utils.chunk_splitter

---

### Step 6: Embedding Generation
**File**: `src/pipeline/step6_embeddings.py`

**Purpose**: Generates embeddings for all child chunks using OpenAI API.

**Role**: Populates vec_child_chunks table with vector embeddings. Implements batching and retry logic.

**Dependencies**: src.config, src.database.connections, src.utils.embedding_generator, openai

---

### Step 7: QA & Validation
**File**: `src/pipeline/step7_qa.py`

**Purpose**: Validates pipeline output quality with structural checks and statistical sampling.

**Role**: Performs 100% structural QA, 20% disease sampling, and 100% validation of critical content (emergency protocols, vaccine schedules).

**Dependencies**: src.config, src.database.connections, src.utils.validation

---

### Step 8: Database Export
**File**: `src/pipeline/step8_export.py`

**Purpose**: Finalizes and optimizes database with VACUUM and ANALYZE.

**Role**: Final step. Runs validation queries, optimizes database, generates checksum, and exports summary report.

**Dependencies**: src.config, src.database.connections, src.database.schema

---

## Utilities

### `src/utils/tokenizer.py`

**Purpose**: Token counting using tiktoken with cl100k_base encoding.

**Role**: Used by chunking steps to validate token counts. Critical for chunk size validation.

**Dependencies**: tiktoken, src.config

**Imported By**: step3_cleanup, step5_chunking, chunk_splitter

---

### `src/utils/chunk_splitter.py`

**Purpose**: Splits content into chunks while respecting boundaries (paragraphs, subsections).

**Role**: Ensures chunks never split mid-paragraph or mid-clinical-logic. Used for both parent and child chunking.

**Dependencies**: src.utils.tokenizer, src.config

**Imported By**: step3_cleanup, step5_chunking

---

### `src/utils/embedding_generator.py`

**Purpose**: Generates embeddings using OpenAI API with batching and retry logic.

**Role**: Wraps OpenAI embedding API calls with exponential backoff and error handling. Used by step6 and query engine.

**Dependencies**: openai, src.config, src.utils.logging_config

**Imported By**: step6_embeddings, query_engine

---

### `src/utils/llm_helpers.py`

**Purpose**: Claude API interaction helpers for table conversion and segmentation reconciliation.

**Role**: Provides wrapper functions for calling Claude API with validation of JSON responses. Minimizes LLM usage.

**Dependencies**: anthropic, src.config, src.utils.logging_config

**Imported By**: step2_segmentation, step4_tables, table_converter

---

### `src/utils/table_converter.py`

**Purpose**: Converts tables to natural language prose using LLM helpers.

**Role**: Handles table-to-prose conversion with special attention to Level of Care codes and vaccine schedules.

**Dependencies**: src.utils.llm_helpers, src.config, src.utils.logging_config

**Imported By**: step4_tables

---

### `src/utils/validation.py`

**Purpose**: Validation utilities for section hierarchy, table conversions, and QA checks.

**Role**: Provides validation functions used throughout pipeline for data quality assurance.

**Dependencies**: src.database.connections, src.utils.logging_config

**Imported By**: step2_segmentation, step4_tables, step7_qa

---

### `src/parsers/base.py`

**Purpose**: Abstract base class defining parser interface.

**Role**: Provides interface that all PDF parsers must implement. Simple contract for parse() and get_blocks() methods.

**Dependencies**: abc, pathlib

**Imported By**: docling_parser

---

### `src/parsers/docling_parser.py`

**Purpose**: Implements Docling PDF parser wrapper.

**Role**: Provides Docling-specific implementation of parser interface. Handles full document parsing with no page limit.

**Dependencies**: docling, src.parsers.base, src.config, src.utils.logging_config

**Imported By**: step1_parsing

---

## Dependencies Overview

### Module Dependency Flow

```
config
  └─> logging_config
       └─> schema
            └─> connections
                 └─> All pipeline steps

Utility Dependencies:
- tokenizer (needed by: step3, step5, chunk_splitter)
- chunk_splitter (needed by: step3, step5)
- embedding_generator (needed by: step6, query_engine)
- llm_helpers (needed by: step2, step4, table_converter)
- validation (needed by: step2, step4, step7)
- docling_parser (needed by: step1)
```

### Key Relationships

**Core Foundation** (must be implemented first):
- config → All modules
- logging_config → All modules
- schema → connections → All pipeline steps

**Pipeline Dependencies**:
- Step 0: config, connections (no blockers)
- Step 1: config, connections, docling_parser
- Step 2: config, connections, llm_helpers, validation
- Step 3: config, connections, tokenizer, chunk_splitter
- Step 4: config, connections, llm_helpers, table_converter, validation
- Step 5: config, connections, tokenizer, chunk_splitter
- Step 6: config, connections, embedding_generator
- Step 7: config, connections, validation
- Step 8: config, connections, schema (no blockers)

---

## Execution Flow

### Normal Pipeline Execution

```
1. Initialize Logging
2. Validate Configuration
3. Initialize Database Schema
4. Step 0: Register Document
5. Step 1: Parse PDF with Docling
6. Step 2: Reconstruct Hierarchy
7. Step 3: Clean and Create Parent Chunks
8. Step 4: Linearize Tables
9. Step 5: Create Child Chunks
10. Step 6: Generate Embeddings
11. Step 7: Run QA Validation
12. Step 8: Optimize and Export
```

### RAG Query Flow

```
1. User submits natural language query
2. Generate query embedding via embedding_generator
3. Perform vector similarity search on vec_child_chunks
4. Find top 50 most similar child chunks
5. Join to parent_chunks table to get complete content
6. Group by parent_id to get distinct parent chunks
7. Join to sections table for metadata (heading_path, pages)
8. Return parent chunks with context for LLM
```

---

## Transaction Boundaries

Each pipeline step has specific transaction batching for resumability:

- **Step 0**: Single transaction per document
- **Step 1**: Batch per 100 blocks
- **Step 2**: Single transaction per chapter
- **Step 3**: Batch per 10 sections
- **Step 4**: Batch per 10 sections
- **Step 5**: Batch per disease/topic
- **Step 6**: Batch per 100 chunks
- **Step 7**: Read-only (no transactions)
- **Step 8**: Final operations (VACUUM, ANALYZE)

On failure: rollback current transaction, log error, resume from last successful batch.

---

## Current Implementation Status

**Implemented (4 modules)**:
- src/config.py
- src/utils/logging_config.py
- src/database/schema.py
- src/database/connections.py

**Not Yet Implemented (23 modules)**:
- All pipeline steps (step0-step8)
- All utilities (except logging_config)
- Parser implementations
- Main orchestrator
- Query engine

---

## Recommended Implementation Order

**Phase 1: Core Utilities**
1. tokenizer.py
2. chunk_splitter.py

**Phase 2: Parser**
3. base.py
4. docling_parser.py

**Phase 3: LLM & Validation**
5. llm_helpers.py
6. validation.py
7. table_converter.py

**Phase 4: Embeddings**
8. embedding_generator.py

**Phase 5: Pipeline Steps**
9. step0_registration.py
10. step1_parsing.py
11. step2_segmentation.py
12. step3_cleanup.py
13. step4_tables.py
14. step5_chunking.py
15. step6_embeddings.py
16. step7_qa.py
17. step8_export.py

**Phase 6: Orchestration**
18. main.py
19. query_engine.py

---

**Last Reviewed**: 2025-12-09
