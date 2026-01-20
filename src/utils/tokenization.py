"""
Tokenization Utilities

Shared token counting functions using tiktoken.
Used across multiple pipeline steps (Step 3, Step 5, etc.).
"""

from typing import Optional
import tiktoken

from src.config import TOKEN_ENCODING
from src.utils.logging_config import logger


# Cache tokenizer instance for performance
_tokenizer_cache: Optional[tiktoken.Encoding] = None


def get_tokenizer() -> tiktoken.Encoding:
    """
    Get tiktoken tokenizer for cl100k_base encoding.

    Uses module-level cache to avoid repeated initialization.

    Returns:
        Tiktoken encoding instance
    """
    global _tokenizer_cache

    if _tokenizer_cache is None:
        logger.debug(f"Initializing tiktoken tokenizer: {TOKEN_ENCODING}")
        _tokenizer_cache = tiktoken.get_encoding(TOKEN_ENCODING)

    return _tokenizer_cache


def count_tokens(text: str, tokenizer: Optional[tiktoken.Encoding] = None) -> int:
    """
    Count tokens in text using tiktoken cl100k_base encoding.

    Args:
        text: Text to count tokens in
        tokenizer: Optional pre-initialized tokenizer (for performance)

    Returns:
        Token count

    Example:
        >>> count_tokens("Hello, world!")
        4

        >>> # Reuse tokenizer for batch processing
        >>> tok = get_tokenizer()
        >>> total = sum(count_tokens(text, tok) for text in texts)
    """
    if not text:
        return 0

    if tokenizer is None:
        tokenizer = get_tokenizer()

    return len(tokenizer.encode(text))


def reset_tokenizer_cache():
    """
    Reset the cached tokenizer instance.

    Useful for testing or when changing TOKEN_ENCODING config.
    """
    global _tokenizer_cache
    _tokenizer_cache = None
    logger.debug("Tokenizer cache reset")
