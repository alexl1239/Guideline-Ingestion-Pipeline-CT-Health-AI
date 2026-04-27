"""
Table Linearization via OpenAI Chat API (Step 3)

Sends each preprocessed table to an LLM with a constrained prompt that
preserves every clinical value verbatim and only changes syntax. Returns
clean markdown prose suitable for storage in raw_blocks.text_content.
"""

import time
from typing import Optional

from openai import OpenAI, APIError, RateLimitError, APITimeoutError

from src.config import (
    OPENAI_API_KEY,
    TABLE_LLM_MODEL,
    MAX_API_RETRIES,
    API_RETRY_INITIAL_BACKOFF,
)
from src.utils.logging_config import logger


_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """Lazy-init shared OpenAI client."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = """You are a Clinical Content Editor for the Uganda Ministry of Health.

Your task: Convert a clinical guideline table into natural-language sentences \
and Markdown bulleted lists, suitable for inclusion in a RAG context window.

CRITICAL CONSTRAINTS:
1. NO FACTUAL CHANGE: Preserve every medical term, dosage, age, frequency, \
duration, route, indication, contraindication, diagnostic criterion, level-of-care \
code, and numeric value EXACTLY as written. Do not paraphrase clinical content.
2. PRESERVE STRUCTURE: When the table groups items by row, render each row as a \
sentence or short bulleted block. When items are lists within a cell, use Markdown \
bullets (-).
3. SYNTACTIC ONLY: Your only freedom is to add connecting prose words \
("for", "when", "in patients with", "the dose is") so sentences read naturally.
4. NO COMMENTARY: Do not add headings, summaries, footnotes, or explanations \
that are not present in the source table.
5. OUTPUT: Clean Markdown only. No code fences, no preamble, no "Here is the \
linearized table" — output the converted text directly."""


def build_user_prompt(table_markdown: str, heading_path: Optional[str]) -> str:
    """
    Build the per-table user message.

    Args:
        table_markdown: Pre-cleaned table markdown (after normalize_table_markdown)
        heading_path: Section path for clinical context (may be None)

    Returns:
        User message string for the chat API
    """
    context = f"Section: {heading_path}\n\n" if heading_path else ""
    return (
        f"{context}"
        f"Convert the following table into natural-language Markdown.\n\n"
        f"```\n{table_markdown}\n```"
    )


def linearize_table(
    table_markdown: str,
    heading_path: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Send a single table to the LLM and return linearized prose.

    Retries on transient API errors with exponential backoff. Raises on
    non-retryable errors so the caller can decide whether to skip and continue
    or abort the batch.

    Args:
        table_markdown: Cleaned table markdown
        heading_path: Section path for clinical context
        model: Override the model (defaults to TABLE_LLM_MODEL from config)

    Returns:
        Linearized prose (markdown)

    Raises:
        APIError: After MAX_API_RETRIES exhausted on a retryable error
        Other openai exceptions: Non-retryable errors propagate immediately
    """
    client = get_client()
    model = model or TABLE_LLM_MODEL
    user_prompt = build_user_prompt(table_markdown, heading_path)

    backoff = API_RETRY_INITIAL_BACKOFF

    for attempt in range(MAX_API_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                # Low temperature: linearization is deterministic; we want
                # consistent, faithful output across re-runs.
                temperature=0.0,
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("LLM returned empty content")
            return content.strip()

        except (RateLimitError, APITimeoutError, APIError) as e:
            if attempt < MAX_API_RETRIES - 1:
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{MAX_API_RETRIES}): "
                    f"{type(e).__name__}: {e}. Retrying in {backoff}s..."
                )
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(
                    f"LLM call exhausted retries after {MAX_API_RETRIES} attempts: {e}"
                )
                raise


__all__ = [
    "linearize_table",
    "build_user_prompt",
    "SYSTEM_PROMPT",
    "get_client",
]
