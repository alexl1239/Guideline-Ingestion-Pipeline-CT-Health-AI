# """
# LLM helper utilities for segmentation and table conversion.

# Provides strict prompt templates per Extraction_Process_v2.1 requirements.
# """

# from typing import List, Dict, Optional
# import json
# import logging


# class LLMHelpers:
#     """Strict LLM prompt templates for structural editing and table conversion."""

#     def __init__(self, llm_client=None):
#         """
#         Initialize LLM helpers.

#         Args:
#             llm_client: Optional LLM client (Claude/GPT) for API calls
#         """
#         self.llm_client = llm_client
#         self.logger = logging.getLogger(__name__)

#     @staticmethod
#     def get_segmentation_prompt(markdown_content: str) -> str:
#         """
#         Generate strict LLM prompt for structural segmentation.

#         Per requirements section 5.3:
#         - Use ONLY for problematic areas (missing subsections, level inconsistencies,
#           ambiguous patterns, sections >10 pages without headings)
#         - Output ONLY JSON
#         - Do NOT modify text, add content, or reorder

#         Args:
#             markdown_content: Markdown content to analyze

#         Returns:
#             Formatted prompt string
#         """
#         return f"""You are a structural editor. Your ONLY task is to identify section headings and their hierarchy levels.

# STRICT CONSTRAINTS:
# 1. Output ONLY JSON with format: [{{"heading": "...", "level": N}}, ...]
# 2. Do NOT modify heading text
# 3. Do NOT add content
# 4. Do NOT reorder sections
# 5. Levels must be 1 (chapter), 2 (disease), or 3+ (subsection)

# Input markdown:
# {markdown_content}

# Output JSON only:"""

#     @staticmethod
#     def get_table_conversion_prompt(table_markdown: str, heading: str) -> str:
#         """
#         Generate strict LLM prompt for table linearization.

#         Per requirements section 5.5:
#         - NO FACTUAL CHANGE
#         - PRESERVE LISTS
#         - SYNTACTIC ONLY
#         - Clean Markdown output

#         Args:
#             table_markdown: Table content in markdown/CSV format
#             heading: Table title/heading for context

#         Returns:
#             Formatted prompt string
#         """
#         return f"""Role: You are a highly specialized Clinical Content Editor for the Uganda Ministry of Health.

# Task: Convert the provided table into natural language sentences and bulleted lists.

# CRITICAL CONSTRAINT - DO NOT BREAK:
# 1. NO FACTUAL CHANGE: Preserve every piece of information exactly. Do not alter any medical term, dosage, age, frequency, criteria, or diagnosis.
# 2. PRESERVE LISTS: If a column contains a list, convert to proper Markdown bullets (-)
# 3. SYNTACTIC ONLY: Changes must be purely syntactic while maintaining exact clinical meaning
# 4. OUTPUT FORMAT: Clean Markdown text only

# Source Table Title: {heading}
# Table Content (CSV/Markdown):
# {table_markdown}

# Based only on content above, generate linearized output. Example structure:
# - The guidelines state that [A VALUE] requires [B VALUE]
# - For [A VALUE 2], the recommended action is [B VALUE 2]

# Begin Output Below:"""

#     def should_trigger_llm_segmentation(self, section_data: Dict) -> bool:
#         """
#         Determine if section requires LLM reconciliation.

#         Explicit heuristics from requirements section 5.3:
#         - Missing expected subsections (e.g., disease without "Management")
#         - Heading level inconsistencies (e.g., jump from level 1 to 3)
#         - Ambiguous heading patterns not matching regex
#         - Sections with > 10 pages without sub-headings

#         Args:
#             section_data: Dictionary with section metadata

#         Returns:
#             True if LLM review is needed
#         """
#         # Expected disease subsections from UCG structure
#         EXPECTED_SUBSECTIONS = {
#             'Definition', 'Causes', 'Risk factors', 'Clinical features',
#             'Complications', 'Differential diagnosis', 'Investigations',
#             'Management', 'Prevention'
#         }

#         # Check for missing subsections (if this is a disease section)
#         if section_data.get('level') == 2:  # Disease level
#             found_subsections = set(section_data.get('subsections', []))
#             if 'Management' not in found_subsections:
#                 self.logger.warning(
#                     f"Disease section missing 'Management': {section_data.get('heading')}"
#                 )
#                 return True

#         # Check for level inconsistencies
#         child_levels = section_data.get('child_levels', [])
#         if child_levels:
#             parent_level = section_data.get('level', 1)
#             for child_level in child_levels:
#                 if child_level > parent_level + 1:
#                     self.logger.warning(
#                         f"Level inconsistency: jump from {parent_level} to {child_level}"
#                     )
#                     return True

#         # Check for long sections without headings
#         page_count = section_data.get('page_count', 0)
#         has_subheadings = len(section_data.get('subsections', [])) > 0
#         if page_count > 10 and not has_subheadings:
#             self.logger.warning(
#                 f"Long section ({page_count} pages) without sub-headings: "
#                 f"{section_data.get('heading')}"
#             )
#             return True

#         # Check for ambiguous heading patterns (implementation would check regex match)
#         if section_data.get('heading_pattern_ambiguous', False):
#             return True

#         return False

#     def parse_segmentation_response(self, llm_response: str) -> Optional[List[Dict]]:
#         """
#         Parse and validate LLM segmentation response.

#         Args:
#             llm_response: JSON response from LLM

#         Returns:
#             List of heading dictionaries or None if invalid
#         """
#         try:
#             headings = json.loads(llm_response)

#             # Validate structure
#             if not isinstance(headings, list):
#                 self.logger.error("LLM response is not a list")
#                 return None

#             for item in headings:
#                 if not isinstance(item, dict):
#                     self.logger.error("Heading item is not a dictionary")
#                     return None
#                 if 'heading' not in item or 'level' not in item:
#                     self.logger.error("Missing required fields in heading item")
#                     return None
#                 if not isinstance(item['level'], int) or item['level'] < 1:
#                     self.logger.error(f"Invalid level: {item['level']}")
#                     return None

#             return headings

#         except json.JSONDecodeError as e:
#             self.logger.error(f"Failed to parse LLM JSON response: {e}")
#             return None

#     def call_llm(self, prompt: str, model: str = "claude-3-sonnet",
#                 max_tokens: int = 4000) -> Optional[str]:
#         """
#         Make LLM API call with error handling.

#         Args:
#             prompt: Formatted prompt string
#             model: Model identifier
#             max_tokens: Maximum response tokens

#         Returns:
#             LLM response text or None on error
#         """
#         if not self.llm_client:
#             self.logger.error("No LLM client configured")
#             return None

#         try:
#             # Placeholder for actual API call
#             # Implementation would use self.llm_client
#             response = None  # self.llm_client.generate(prompt, model, max_tokens)
#             return response
#         except Exception as e:
#             self.logger.error(f"LLM API call failed: {e}")
#             return None
