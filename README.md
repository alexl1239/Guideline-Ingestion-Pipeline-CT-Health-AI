## Summary of the UCG-23 RAG Pipeline

The pipeline converts **UCG-23** from PDF into a **single SQLite database** that is:

* **Parser-flexible**

  * Primarily uses **Docling**

* **Clinically accurate**

  * Strict constraints on content transformation
  * Extensive multi-stage QA validation

* **Fully self-contained**

  * Produces one `.db` file
  * Includes embedded model metadata for reproducibility

* **Structured hierarchically**

  * Chapters → diseases → subsections → parent chunks → child chunks

* **Enriched**

  * Tables are converted into logical text statements
  * All clinical meaning is preserved exactly

* **Optimized for RAG**

  * Uses `sqlite-vec` embeddings (OpenAI `text-embedding-3-small`)
  * Similarity search runs on **child chunks**
  * Retrieval returns **parent chunks** to the LLM for cleaner context

* **Production-ready**

  * Transaction boundaries for every step
  * Robust error handling and recovery procedures
  * External logging for full traceability

* **Extensible**

  * Supports incremental updates
  * Multi-document ingestion compatible

---

### Final Deliverable

A **single portable SQLite database file** that can be distributed and used fully offline as the **core knowledge base** of a clinical support chatbot built around the *Uganda Clinical Guidelines 2023*.
