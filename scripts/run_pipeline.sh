#!/bin/bash
# Run complete ETL pipeline for UCG-23

set -e  # Exit on error

echo "=========================================="
echo "UCG-23 RAG ETL Pipeline"
echo "=========================================="
echo ""

# Check virtual environment
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Run 'python -m venv venv' first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check dependencies
echo "Checking dependencies..."
python -c "import llama_parse; import openai; import sqlite_vec" 2>/dev/null || {
    echo "Error: Missing dependencies. Run 'pip install -r requirements.txt'"
    exit 1
}

# Check API keys
echo "Checking API keys..."
if [ -z "$LLAMAPARSE_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    if [ -f ".env" ]; then
        echo "Loading .env file..."
        set -a
        source .env
        set +a
    else
        echo "Error: API keys not found. Create .env file with LLAMAPARSE_API_KEY and OPENAI_API_KEY"
        exit 1
    fi
fi

echo ""
echo "Starting pipeline..."
echo ""

# Step 0: Document Registration
echo "Step 0: Document Registration"
python src/pipeline/step0_registration.py
if [ $? -ne 0 ]; then
    echo "Error in Step 0"
    exit 1
fi
echo "✓ Step 0 complete"
echo ""

# Step 1: Parsing
echo "Step 1: PDF Parsing (this may take a while...)"
python src/pipeline/step1_parsing.py
if [ $? -ne 0 ]; then
    echo "Error in Step 1"
    exit 1
fi
echo "✓ Step 1 complete"
echo ""

# Step 2: Segmentation
echo "Step 2: Structural Segmentation"
python src/pipeline/step2_segmentation.py
if [ $? -ne 0 ]; then
    echo "Error in Step 2"
    exit 1
fi
echo "✓ Step 2 complete"
echo ""

# Step 3: Cleanup
echo "Step 3: Markdown Cleanup"
python src/pipeline/step3_cleanup.py
if [ $? -ne 0 ]; then
    echo "Error in Step 3"
    exit 1
fi
echo "✓ Step 3 complete"
echo ""

# Step 4: Table Linearization
echo "Step 4: Table Linearization"
python src/pipeline/step4_tables.py
if [ $? -ne 0 ]; then
    echo "Error in Step 4"
    exit 1
fi
echo "✓ Step 4 complete"
echo ""

# Step 5: Chunking
echo "Step 5: Parent-Child Chunking"
python src/pipeline/step5_chunking.py
if [ $? -ne 0 ]; then
    echo "Error in Step 5"
    exit 1
fi
echo "✓ Step 5 complete"
echo ""

# Step 6: Embeddings
echo "Step 6: Embedding Generation (this may take a while...)"
python src/pipeline/step6_embeddings.py
if [ $? -ne 0 ]; then
    echo "Error in Step 6"
    exit 1
fi
echo "✓ Step 6 complete"
echo ""

# Step 7: QA Validation
echo "Step 7: QA Validation"
python src/pipeline/step7_qa.py
if [ $? -ne 0 ]; then
    echo "Error in Step 7"
    exit 1
fi
echo "✓ Step 7 complete"
echo ""

# Step 8: Export
echo "Step 8: Database Finalization"
python src/pipeline/step8_export.py
if [ $? -ne 0 ]; then
    echo "Error in Step 8"
    exit 1
fi
echo "✓ Step 8 complete"
echo ""

echo "=========================================="
echo "Pipeline Complete!"
echo "=========================================="
echo ""
echo "Database created at: data/ucg23_rag.db"
echo ""
echo "Next steps:"
echo "  - Run 'python scripts/inspect_db.py' to inspect the database"
echo "  - Run 'python scripts/query_db.py' to test queries"
echo ""
