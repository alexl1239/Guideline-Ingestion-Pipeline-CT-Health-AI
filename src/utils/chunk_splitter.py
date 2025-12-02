# """
# Parent-child chunking utilities.

# Implements the hierarchical chunking strategy:
# - Parent chunks: 1000-1500 tokens (hard max 2000) - complete clinical topics
# - Child chunks: 256 tokens ± 10% (hard max 512) - retrieval units
# """

# from typing import List, Tuple
# import logging


# class ChunkSplitter:
#     """Handles parent-child chunking with token-based splitting."""

#     # Token targets from requirements
#     PARENT_TOKEN_TARGET = 1500
#     PARENT_TOKEN_HARD_MAX = 2000
#     CHILD_TOKEN_TARGET = 256
#     CHILD_TOKEN_TOLERANCE = 0.10  # ±10%
#     CHILD_TOKEN_HARD_MAX = 512

#     def __init__(self, tokenizer):
#         """
#         Initialize chunk splitter.

#         Args:
#             tokenizer: Tokenizer instance (tiktoken cl100k_base)
#         """
#         self.tokenizer = tokenizer
#         self.logger = logging.getLogger(__name__)

#     def create_parent_chunks(self, cleaned_markdown: str, section_id: str,
#                             subsection_boundaries: List[int]) -> List[dict]:
#         """
#         Create parent chunks from cleaned markdown.

#         Per requirements (Step 3):
#         - Target: 1000-1500 tokens (hard max 2000)
#         - One parent per disease/topic (level=2 section) when possible
#         - If >2000 tokens, split ONLY at subsection boundaries, never mid-paragraph

#         Args:
#             cleaned_markdown: Cleaned section markdown
#             section_id: Database section ID
#             subsection_boundaries: Character positions of subsection breaks

#         Returns:
#             List of parent chunk dictionaries with content, token_count, metadata
#         """
#         token_count = self.tokenizer.count_tokens(cleaned_markdown)

#         if token_count <= self.PARENT_TOKEN_HARD_MAX:
#             # Single parent chunk
#             return [{
#                 'section_id': section_id,
#                 'content': cleaned_markdown,
#                 'token_count': token_count,
#                 'chunk_index': 0
#             }]
#         else:
#             # Split at subsection boundaries
#             return self._split_at_boundaries(
#                 cleaned_markdown,
#                 section_id,
#                 subsection_boundaries
#             )

#     def _split_at_boundaries(self, text: str, section_id: str,
#                            boundaries: List[int]) -> List[dict]:
#         """
#         Split text at subsection boundaries, never mid-paragraph.
#         """
#         # Implementation placeholder
#         pass

#     def create_child_chunks(self, parent_content: str, parent_id: str,
#                           heading_path: str) -> List[dict]:
#         """
#         Create child chunks from parent chunk.

#         Per requirements (Step 5):
#         - Target: 256 tokens ± 10% (hard max 512)
#         - Each child includes heading as context
#         - Respect paragraph and bullet boundaries
#         - Preserve clinical context and cross-references

#         Args:
#             parent_content: Parent chunk content
#             parent_id: Parent chunk database ID
#             heading_path: Full heading path for context

#         Returns:
#             List of child chunk dictionaries
#         """
#         child_chunks = []

#         # Split content into semantic units (paragraphs, bullets)
#         units = self._split_into_semantic_units(parent_content)

#         current_chunk = []
#         current_tokens = 0

#         for unit in units:
#             unit_tokens = self.tokenizer.count_tokens(unit)

#             # Check if adding this unit would exceed target
#             if (current_tokens + unit_tokens > self._get_child_max_target() and
#                 current_chunk):
#                 # Save current chunk
#                 child_chunks.append(self._create_child_chunk(
#                     current_chunk, parent_id, heading_path, len(child_chunks)
#                 ))
#                 current_chunk = []
#                 current_tokens = 0

#             current_chunk.append(unit)
#             current_tokens += unit_tokens

#         # Add final chunk
#         if current_chunk:
#             child_chunks.append(self._create_child_chunk(
#                 current_chunk, parent_id, heading_path, len(child_chunks)
#             ))

#         return child_chunks

#     def _split_into_semantic_units(self, text: str) -> List[str]:
#         """
#         Split text into semantic units (paragraphs, bullet points).

#         Respects:
#         - Paragraph breaks (\n\n)
#         - Bullet points (lines starting with -, *, number)
#         - Preserves cross-references
#         """
#         # Implementation placeholder
#         pass

#     def _create_child_chunk(self, units: List[str], parent_id: str,
#                           heading_path: str, index: int) -> dict:
#         """
#         Create a child chunk with heading context prepended.

#         Per requirements: f"Section: {heading_path}\n\n{chunk_content}"
#         """
#         content = '\n\n'.join(units)
#         augmented_content = f"Section: {heading_path}\n\n{content}"

#         return {
#             'parent_id': parent_id,
#             'content': augmented_content,
#             'token_count': self.tokenizer.count_tokens(augmented_content),
#             'order_index': index,
#             'heading_path': heading_path
#         }

#     def _get_child_max_target(self) -> int:
#         """Get maximum target for child chunks (256 + 10%)."""
#         return int(self.CHILD_TOKEN_TARGET * (1 + self.CHILD_TOKEN_TOLERANCE))

#     def validate_chunks(self, chunks: List[dict], chunk_type: str) -> bool:
#         """
#         Validate that chunks meet token requirements.

#         Args:
#             chunks: List of chunk dictionaries
#             chunk_type: 'parent' or 'child'

#         Returns:
#             True if all chunks are valid
#         """
#         if chunk_type == 'parent':
#             max_tokens = self.PARENT_TOKEN_HARD_MAX
#         else:
#             max_tokens = self.CHILD_TOKEN_HARD_MAX

#         for chunk in chunks:
#             if chunk['token_count'] > max_tokens:
#                 self.logger.error(
#                     f"{chunk_type} chunk exceeds max tokens: "
#                     f"{chunk['token_count']} > {max_tokens}"
#                 )
#                 return False

#         return True
