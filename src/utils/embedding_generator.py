# """
# Embedding generation with retry logic and batch processing.

# Implements the transaction-boundary pattern from requirements with
# exponential backoff for API failures.
# """

# import time
# import logging
# from typing import List, Dict, Callable, Optional
# import sqlite3


# class EmbeddingGenerator:
#     """Generates embeddings with transaction boundaries and retry logic."""

#     # Batch configuration from requirements
#     DEFAULT_BATCH_SIZE = 100
#     DEFAULT_MAX_RETRIES = 3
#     INITIAL_BACKOFF = 2  # seconds

#     def __init__(self, embedding_function: Callable, batch_size: int = DEFAULT_BATCH_SIZE,
#                  max_retries: int = DEFAULT_MAX_RETRIES):
#         """
#         Initialize embedding generator.

#         Args:
#             embedding_function: Function that takes text and returns embedding vector
#             batch_size: Number of chunks to process per transaction (default 100)
#             max_retries: Maximum retry attempts for failed API calls (default 3)
#         """
#         self.embedding_function = embedding_function
#         self.batch_size = batch_size
#         self.max_retries = max_retries
#         self.logger = logging.getLogger(__name__)

#     def generate_embeddings_with_retry(self, conn: sqlite3.Connection,
#                                       chunks: List[Dict]) -> int:
#         """
#         Generate embeddings with transaction boundaries and retry logic.

#         This is the exact pattern from Extraction_Process_v2.1 section 5.7.

#         Args:
#             conn: SQLite database connection
#             chunks: List of chunk dictionaries with 'id' and 'content' fields

#         Returns:
#             Number of chunks successfully embedded

#         Raises:
#             Exception: If batch fails after all retries
#         """
#         success_count = 0

#         for i in range(0, len(chunks), self.batch_size):
#             batch = chunks[i:i + self.batch_size]
#             batch_num = i // self.batch_size

#             try:
#                 conn.execute("BEGIN TRANSACTION")

#                 for chunk in batch:
#                     embedding = self._generate_with_retry(chunk['content'])

#                     # Insert into vec_child_chunks virtual table
#                     conn.execute(
#                         "INSERT INTO vec_child_chunks (chunk_id, embedding) VALUES (?, ?)",
#                         (chunk['id'], self._serialize_embedding(embedding))
#                     )
#                     success_count += 1

#                 conn.execute("COMMIT")
#                 self.logger.info(f"Successfully processed batch {batch_num} "
#                                f"({len(batch)} chunks)")

#             except Exception as e:
#                 conn.execute("ROLLBACK")
#                 self.logger.error(f"Failed to process batch {batch_num}: {e}")
#                 raise

#         return success_count

#     def _generate_with_retry(self, text: str) -> List[float]:
#         """
#         Generate embedding with exponential backoff retry.

#         Args:
#             text: Text to embed

#         Returns:
#             Embedding vector

#         Raises:
#             Exception: If all retry attempts fail
#         """
#         for attempt in range(self.max_retries):
#             try:
#                 embedding = self.embedding_function(text)
#                 return embedding
#             except Exception as e:
#                 if attempt == self.max_retries - 1:
#                     self.logger.error(
#                         f"Failed to generate embedding after {self.max_retries} attempts: {e}"
#                     )
#                     raise

#                 # Exponential backoff: 2^attempt seconds
#                 backoff_time = self.INITIAL_BACKOFF ** attempt
#                 self.logger.warning(
#                     f"Embedding generation failed (attempt {attempt + 1}/{self.max_retries}), "
#                     f"retrying in {backoff_time}s: {e}"
#                 )
#                 time.sleep(backoff_time)

#     def _serialize_embedding(self, embedding: List[float]) -> bytes:
#         """
#         Serialize embedding vector for sqlite-vec storage.

#         Args:
#             embedding: List of float values

#         Returns:
#             Serialized bytes for BLOB storage
#         """
#         # sqlite-vec expects specific format - implementation depends on sqlite_vec API
#         # Placeholder for proper serialization
#         pass

#     def validate_embedding_dimension(self, embedding: List[float],
#                                     expected_dim: int) -> bool:
#         """
#         Validate that embedding has expected dimensionality.

#         Critical check since dimension is schema-fixed per requirements.

#         Args:
#             embedding: Embedding vector
#             expected_dim: Expected dimension (1536 for text-embedding-3-small)

#         Returns:
#             True if dimension matches
#         """
#         if len(embedding) != expected_dim:
#             self.logger.error(
#                 f"Embedding dimension mismatch: {len(embedding)} != {expected_dim}"
#             )
#             return False
#         return True

#     def estimate_batch_time(self, num_chunks: int, avg_tokens_per_chunk: int) -> float:
#         """
#         Estimate total processing time.

#         Args:
#             num_chunks: Total number of chunks
#             avg_tokens_per_chunk: Average tokens per chunk

#         Returns:
#             Estimated time in seconds
#         """
#         # Rough estimation: OpenAI embedding API ~1000 tokens/second
#         # Plus overhead for batching and retries
#         tokens_total = num_chunks * avg_tokens_per_chunk
#         base_time = tokens_total / 1000  # seconds
#         overhead = (num_chunks / self.batch_size) * 2  # 2 seconds per batch overhead
#         return base_time + overhead
