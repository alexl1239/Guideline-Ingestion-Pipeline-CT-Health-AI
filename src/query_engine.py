# """
# RAG Query Engine

# Demonstrates the parent-child retrieval pattern from Extraction_Process_v2.1 section 6.

# Key principle: Search on child chunks, return parent chunks to LLM.
# """

# import logging
# import sqlite3
# from typing import List, Dict, Optional, Callable
# import sqlite_vec


# class RAGQueryEngine:
#     """Query engine implementing parent-child retrieval pattern."""

#     def __init__(self, db_path: str, embedding_function: Callable):
#         """
#         Initialize RAG query engine.

#         Args:
#             db_path: Path to SQLite database with sqlite-vec
#             embedding_function: Function that takes text and returns embedding vector
#         """
#         self.db_path = db_path
#         self.embedding_function = embedding_function
#         self.logger = logging.getLogger(__name__)

#     def query(self, user_query: str, top_k: int = 5,
#              document_filter: Optional[str] = None) -> List[Dict]:
#         """
#         Execute RAG query using parent-child retrieval pattern.

#         Per requirements section 6:
#         - Generate query embedding
#         - Search child chunks for similarity
#         - Return parent chunks (deduplicated) with metadata

#         Args:
#             user_query: User's question
#             top_k: Number of parent chunks to return
#             document_filter: Optional document ID to filter by

#         Returns:
#             List of parent chunk dictionaries with metadata
#         """
#         self.logger.info(f"Processing query: {user_query[:100]}...")

#         # Generate query embedding
#         query_embedding = self.embedding_function(user_query)

#         # Connect to database and load sqlite-vec
#         conn = self._get_connection()

#         try:
#             # Execute parent-child retrieval query
#             results = self._execute_retrieval_query(
#                 conn, query_embedding, top_k, document_filter
#             )

#             # Enrich with section metadata
#             enriched_results = self._enrich_with_metadata(conn, results)

#             return enriched_results

#         finally:
#             conn.close()

#     def _get_connection(self) -> sqlite3.Connection:
#         """
#         Get database connection with sqlite-vec loaded.

#         Returns:
#             SQLite connection with vector extension enabled
#         """
#         conn = sqlite3.connect(self.db_path)
#         conn.enable_load_extension(True)
#         sqlite_vec.load(conn)
#         conn.enable_load_extension(False)
#         return conn

#     def _execute_retrieval_query(self, conn: sqlite3.Connection,
#                                 query_embedding: List[float], top_k: int,
#                                 document_filter: Optional[str] = None) -> List[Dict]:
#         """
#         Execute the core parent-child retrieval query.

#         This is the exact pattern from requirements section 6.2:
#         - Search vec_child_chunks for similarity
#         - Join to parent_chunks
#         - Group by parent to deduplicate
#         - Return top_k parents ordered by min distance

#         Args:
#             conn: Database connection
#             query_embedding: Query vector
#             top_k: Number of results
#             document_filter: Optional document ID filter

#         Returns:
#             List of parent chunk dictionaries
#         """
#         # Base query from requirements
#         query = """
#             SELECT DISTINCT
#                 p.id as parent_id,
#                 p.section_id,
#                 p.content,
#                 p.token_count,
#                 p.page_start,
#                 p.page_end,
#                 MIN(distance) as min_distance
#             FROM vec_child_chunks v
#             INNER JOIN child_chunks c ON v.chunk_id = c.id
#             INNER JOIN parent_chunks p ON c.parent_id = p.id
#         """

#         # Add document filter if specified
#         if document_filter:
#             query += """
#             INNER JOIN sections s ON p.section_id = s.id
#             WHERE s.document_id = ?
#             """

#         query += """
#             WHERE v.embedding MATCH ?
#             GROUP BY p.id
#             ORDER BY min_distance
#             LIMIT ?
#         """

#         cursor = conn.cursor()

#         # Serialize embedding for sqlite-vec
#         serialized_embedding = self._serialize_embedding(query_embedding)

#         # Execute query
#         if document_filter:
#             cursor.execute(query, (document_filter, serialized_embedding, top_k))
#         else:
#             cursor.execute(query, (serialized_embedding, top_k))

#         # Parse results
#         results = []
#         for row in cursor.fetchall():
#             results.append({
#                 'parent_id': row[0],
#                 'section_id': row[1],
#                 'content': row[2],
#                 'token_count': row[3],
#                 'page_start': row[4],
#                 'page_end': row[5],
#                 'distance': row[6]
#             })

#         return results

#     def _enrich_with_metadata(self, conn: sqlite3.Connection,
#                              results: List[Dict]) -> List[Dict]:
#         """
#         Enrich parent chunks with section metadata.

#         Adds:
#         - Section heading and heading_path
#         - Document title and version
#         - Hierarchical context

#         Args:
#             conn: Database connection
#             results: List of parent chunk dictionaries

#         Returns:
#             Enriched results with metadata
#         """
#         cursor = conn.cursor()

#         for result in results:
#             # Get section metadata
#             cursor.execute("""
#                 SELECT s.heading, s.heading_path, s.level,
#                        d.title, d.version_label
#                 FROM sections s
#                 INNER JOIN documents d ON s.document_id = d.id
#                 WHERE s.id = ?
#             """, (result['section_id'],))

#             section_data = cursor.fetchone()
#             if section_data:
#                 result['section_heading'] = section_data[0]
#                 result['section_path'] = section_data[1]
#                 result['section_level'] = section_data[2]
#                 result['document_title'] = section_data[3]
#                 result['document_version'] = section_data[4]

#         return results

#     def _serialize_embedding(self, embedding: List[float]) -> bytes:
#         """
#         Serialize embedding for sqlite-vec.

#         Args:
#             embedding: Vector to serialize

#         Returns:
#             Serialized bytes
#         """
#         # Placeholder for proper sqlite-vec serialization
#         # Implementation depends on sqlite_vec API
#         pass

#     def format_context_for_llm(self, results: List[Dict]) -> str:
#         """
#         Format retrieved parent chunks for LLM context.

#         Per requirements section 6.3:
#         - Provide only parent chunks
#         - Include section headings and page ranges
#         - Preserve clinical warnings and contraindications

#         Args:
#             results: Retrieved parent chunks with metadata

#         Returns:
#             Formatted context string
#         """
#         context_parts = []

#         for i, result in enumerate(results, 1):
#             # Format: [Source info] Content
#             source = (
#                 f"[{result['document_title']} {result['document_version']} - "
#                 f"{result['section_path']} (pages {result['page_start']}-{result['page_end']})]"
#             )

#             context_parts.append(f"## Source {i}\n{source}\n\n{result['content']}")

#         return "\n\n---\n\n".join(context_parts)

#     def get_database_stats(self) -> Dict:
#         """
#         Get database statistics for monitoring.

#         Returns:
#             Dictionary with counts and metrics
#         """
#         conn = self._get_connection()
#         cursor = conn.cursor()

#         stats = {}

#         try:
#             cursor.execute("SELECT COUNT(*) FROM documents")
#             stats['document_count'] = cursor.fetchone()[0]

#             cursor.execute("SELECT COUNT(*) FROM sections")
#             stats['section_count'] = cursor.fetchone()[0]

#             cursor.execute("SELECT COUNT(*) FROM parent_chunks")
#             stats['parent_chunk_count'] = cursor.fetchone()[0]

#             cursor.execute("SELECT COUNT(*) FROM child_chunks")
#             stats['child_chunk_count'] = cursor.fetchone()[0]

#             cursor.execute("SELECT COUNT(*) FROM vec_child_chunks")
#             stats['embedded_chunk_count'] = cursor.fetchone()[0]

#         finally:
#             conn.close()

#         return stats


# def demo_query():
#     """
#     Demonstration of RAG query pattern.

#     Shows how to use the query engine with the UCG database.
#     """
#     import sys
#     from pathlib import Path

#     # Setup logging
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#     )

#     # Load configuration
#     sys.path.insert(0, str(Path(__file__).parent))
#     from config import DATABASE_PATH, EMBEDDING_MODEL_NAME

#     # Mock embedding function (replace with real OpenAI call)
#     def mock_embedding_function(text: str) -> List[float]:
#         # Placeholder - would call OpenAI API
#         # from openai import OpenAI
#         # client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
#         # response = client.embeddings.create(model=EMBEDDING_MODEL_NAME, input=text)
#         # return response.data[0].embedding
#         return [0.0] * 1536  # Mock 1536-dim vector

#     # Initialize query engine
#     engine = RAGQueryEngine(DATABASE_PATH, mock_embedding_function)

#     # Get stats
#     stats = engine.get_database_stats()
#     print(f"\nDatabase Statistics:")
#     print(f"  Documents: {stats['document_count']}")
#     print(f"  Sections: {stats['section_count']}")
#     print(f"  Parent chunks: {stats['parent_chunk_count']}")
#     print(f"  Child chunks: {stats['child_chunk_count']}")
#     print(f"  Embedded chunks: {stats['embedded_chunk_count']}")

#     # Example query
#     example_query = "What is the management protocol for anaphylactic shock?"
#     print(f"\nExample Query: {example_query}")

#     results = engine.query(example_query, top_k=3)

#     print(f"\nRetrieved {len(results)} parent chunks:")
#     for i, result in enumerate(results, 1):
#         print(f"\n{i}. {result['section_path']}")
#         print(f"   Pages: {result['page_start']}-{result['page_end']}")
#         print(f"   Tokens: {result['token_count']}")
#         print(f"   Distance: {result['distance']:.4f}")
#         print(f"   Preview: {result['content'][:200]}...")

#     # Format for LLM
#     context = engine.format_context_for_llm(results)
#     print(f"\n{'='*60}")
#     print("Formatted Context for LLM:")
#     print(f"{'='*60}")
#     print(context[:1000] + "..." if len(context) > 1000 else context)


# if __name__ == "__main__":
#     demo_query()
