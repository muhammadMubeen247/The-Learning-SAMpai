"""
Core utility functions for the RAG engine.
Ported from LightRAG/lightrag/utils.py with FYP-specific additions.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import time
import weakref
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from hashlib import md5
from typing import Any, Callable, List, Optional, Protocol, Sequence

import numpy as np

from app.rag.constants import (
    GRAPH_FIELD_SEP,
    DEFAULT_MAX_TOTAL_TOKENS,
    DEFAULT_SOURCE_IDS_LIMIT_METHOD,
    VALID_SOURCE_IDS_LIMIT_METHODS,
    SOURCE_IDS_LIMIT_METHOD_FIFO,
)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("fyp_rag")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s [RAG] %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# Precompile regex for JSON sanitization
_SURROGATE_PATTERN = re.compile(r"[\uD800-\uDFFF\uFFFE\uFFFF]")
_CONTROL_CHAR_PATTERN_ALL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


# ---------------------------------------------------------------------------
# Tokenizer protocol
# ---------------------------------------------------------------------------

class Tokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...
    def decode(self, tokens: list[int]) -> str: ...


class TiktokenTokenizer:
    """Tiktoken-based tokenizer for token counting and chunking."""

    def __init__(self, model: str = "gpt-4o-mini"):
        import tiktoken
        self._enc = tiktoken.encoding_for_model(model)

    def encode(self, text: str) -> list[int]:
        return self._enc.encode(text)

    def decode(self, tokens: list[int]) -> str:
        return self._enc.decode(tokens)

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))


# ---------------------------------------------------------------------------
# EmbeddingFunc
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingFunc:
    """
    Wrapper for async embedding functions with dimension validation.
    Prevents double-wrapping and validates output dimensions.
    """
    embedding_dim: int
    func: callable
    max_token_size: int | None = None
    send_dimensions: bool = False
    model_name: str | None = None

    def __post_init__(self):
        # Unwrap nested EmbeddingFunc instances
        max_unwrap = 3
        count = 0
        while isinstance(self.func, EmbeddingFunc):
            count += 1
            if count > max_unwrap:
                raise ValueError("EmbeddingFunc unwrap depth exceeded — circular reference?")
            self.func = self.func.func
        if count > 0:
            logger.warning(f"Auto-unwrapped nested EmbeddingFunc (depth={count})")

    async def __call__(self, *args, **kwargs) -> np.ndarray:
        if self.send_dimensions:
            kwargs["embedding_dim"] = self.embedding_dim
        if self.max_token_size is not None and "max_token_size" not in kwargs:
            sig = inspect.signature(self.func)
            if "max_token_size" in sig.parameters:
                kwargs["max_token_size"] = self.max_token_size

        result = await self.func(*args, **kwargs)

        total_elements = result.size
        if total_elements % self.embedding_dim != 0:
            raise ValueError(
                f"Embedding dimension mismatch: {total_elements} elements not divisible by {self.embedding_dim}"
            )
        return result


def wrap_embedding_func_with_attrs(
    embedding_dim: int,
    max_token_size: int | None = None,
    model_name: str | None = None,
):
    """Decorator that wraps an async embedding function into an EmbeddingFunc instance."""
    def decorator(func):
        return EmbeddingFunc(
            embedding_dim=embedding_dim,
            func=func,
            max_token_size=max_token_size,
            model_name=model_name,
        )
    return decorator


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def compute_args_hash(*args: Any) -> str:
    args_str = "".join([str(arg) for arg in args])
    try:
        return md5(args_str.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        return md5(args_str.encode("utf-8", errors="replace")).hexdigest()


def compute_mdhash_id(content: str, prefix: str = "") -> str:
    """Compute a deterministic ID for content (used for chunks, docs, entities)."""
    return prefix + compute_args_hash(content)


# ---------------------------------------------------------------------------
# String utilities
# ---------------------------------------------------------------------------

def split_string_by_multi_markers(content: str, markers: list[str]) -> list[str]:
    """Split a string by multiple possible delimiters."""
    if not markers:
        return [content]
    results = [content]
    for marker in markers:
        new_results = []
        for part in results:
            new_results.extend(part.split(marker))
        results = new_results
    return [r.strip() for r in results if r.strip()]


def sanitize_and_normalize_extracted_text(text: str, remove_inner_quotes: bool = False) -> str:
    """Remove surrogate characters and control chars from LLM output."""
    if not text:
        return text
    text = _SURROGATE_PATTERN.sub("", text)
    text = _CONTROL_CHAR_PATTERN_ALL.sub("", text)
    if remove_inner_quotes:
        text = text.strip('"').strip("'")
    return text.strip()


def fix_tuple_delimiter_corruption(
    record: str, delimiter_core: str, tuple_delimiter: str
) -> str:
    """Fix common LLM output corruption where delimiters get malformed.

    Handles patterns like '<#>' -> '<|#|>' and '< #>' -> '<|#|>'.
    """
    # Fix patterns like <#> -> <|#|>
    record = re.sub(
        r"<\s*" + re.escape(delimiter_core) + r"\s*>",
        tuple_delimiter,
        record,
    )
    return record


def is_float_regex(value: str) -> bool:
    """Check if a string represents a float number."""
    return bool(re.match(r"^[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?$", value.strip()))


def pack_user_ass_to_openai_messages(*args: str) -> list[dict[str, str]]:
    """Interleave user/assistant messages for OpenAI chat format."""
    roles = ["user", "assistant"]
    return [{"role": roles[i % 2], "content": c} for i, c in enumerate(args)]


def remove_think_tags(text: str) -> str:
    """Strip <think>...</think> blocks from model output (for reasoning models)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ---------------------------------------------------------------------------
# Token-aware truncation
# ---------------------------------------------------------------------------

def truncate_list_by_token_size(
    list_data: list[Any],
    key: Callable[[Any], str],
    max_token_size: int,
    tokenizer: Tokenizer | None = None,
) -> list[Any]:
    """Return a prefix of list_data whose total token count stays under max_token_size."""
    if max_token_size <= 0:
        return []

    if tokenizer is None:
        # Rough estimate: 4 chars ≈ 1 token
        total = 0
        result = []
        for item in list_data:
            tokens = len(key(item)) // 4
            if total + tokens > max_token_size:
                break
            total += tokens
            result.append(item)
        return result

    total = 0
    result = []
    for item in list_data:
        tokens = len(tokenizer.encode(key(item)))
        if total + tokens > max_token_size:
            break
        total += tokens
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# LLM response cache
# ---------------------------------------------------------------------------

@dataclass
class CacheData:
    args_hash: str
    content: str
    prompt: str = ""
    quantized: bool = False
    min_val: float | None = None
    max_val: float | None = None


async def handle_cache(
    hashing_kv: Any | None,
    args_hash: str,
    prompt: str,
    mode: str = "",
    cache_type: str = "default",
) -> tuple[str, int] | None:
    """Check if a cached response exists and return (content, timestamp) or None."""
    if hashing_kv is None:
        return None
    try:
        cache_key = f"{cache_type}:{args_hash}"
        cached = await hashing_kv.get_by_id(cache_key)
        if cached is not None:
            content = cached.get("return", "")
            timestamp = cached.get("create_time", 0)
            return content, timestamp
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None


async def save_to_cache(
    hashing_kv: Any | None,
    cache_data: CacheData,
    cache_type: str = "default",
) -> None:
    """Save an LLM response to cache."""
    if hashing_kv is None:
        return
    try:
        cache_key = f"{cache_type}:{cache_data.args_hash}"
        await hashing_kv.upsert(
            {
                cache_key: {
                    "return": cache_data.content,
                    "prompt": cache_data.prompt,
                    "cache_type": cache_type,
                    "create_time": int(time.time()),
                    "cached_at": datetime.utcnow().isoformat(),
                }
            }
        )
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


async def use_llm_func_with_cache(
    prompt: str,
    llm_func: Callable,
    llm_response_cache: Any | None = None,
    cache_type: str = "default",
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    chunk_id: str | None = None,
    cache_keys_collector: list | None = None,
    **kwargs,
) -> tuple[str, int]:
    """Call LLM with optional caching. Returns (response_str, timestamp) tuple."""
    args_hash = compute_args_hash(prompt, system_prompt or "", cache_type, chunk_id or "")

    if llm_response_cache is not None:
        cached = await handle_cache(llm_response_cache, args_hash, prompt, cache_type=cache_type)
        if cached is not None:
            content, timestamp = cached
            if cache_keys_collector is not None:
                cache_key = f"{cache_type}:{args_hash}"
                if cache_key not in cache_keys_collector:
                    cache_keys_collector.append(cache_key)
            return content, timestamp

    response = await llm_func(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages or [],
        **kwargs,
    )
    result = response if isinstance(response, str) else str(response)
    result = remove_think_tags(result)
    timestamp = int(time.time())

    if llm_response_cache is not None:
        cache_key = f"{cache_type}:{args_hash}"
        cache_entry: dict[str, Any] = {
            "return": result,
            "prompt": prompt,
            "cache_type": cache_type,
            "create_time": timestamp,
            "cached_at": datetime.utcnow().isoformat(),
        }
        if chunk_id is not None:
            cache_entry["chunk_id"] = chunk_id
        try:
            await llm_response_cache.upsert({cache_key: cache_entry})
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

        if cache_keys_collector is not None and cache_key not in cache_keys_collector:
            cache_keys_collector.append(cache_key)

    return result, timestamp


# ---------------------------------------------------------------------------
# Async concurrency helpers
# ---------------------------------------------------------------------------

async def _cooperative_yield(index: int, every: int = 32) -> None:
    """Yield control to the event loop every N iterations to avoid blocking."""
    if index % every == 0:
        await asyncio.sleep(0)


def priority_limit_async_func_call(max_size: int, llm_timeout: float = 180.0, queue_name: str = "rag"):
    """
    Decorator that limits concurrent async calls via a semaphore.
    Simplified version of LightRAG's priority queue for single-process FYP use.
    """
    semaphore = asyncio.Semaphore(max_size)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with semaphore:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=llm_timeout)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Source ID utilities
# ---------------------------------------------------------------------------

def apply_source_ids_limit(
    source_ids: list[str],
    max_ids: int,
    method: str = SOURCE_IDS_LIMIT_METHOD_FIFO,
    identifier: str = "",
) -> list[str]:
    """Trim a list of chunk IDs to max_ids, respecting the limit method.

    Args:
        source_ids: Current list of chunk IDs (already merged).
        max_ids: Maximum number of IDs to keep.
        method: 'fifo' keeps newest (tail), 'keep' keeps oldest (head).
        identifier: Log-friendly label for truncation warnings.

    Returns:
        Trimmed list of chunk IDs (no GRAPH_FIELD_SEP joining).
    """
    if method not in VALID_SOURCE_IDS_LIMIT_METHODS:
        method = SOURCE_IDS_LIMIT_METHOD_FIFO

    if max_ids is None or len(source_ids) <= max_ids:
        return list(source_ids)

    if method == SOURCE_IDS_LIMIT_METHOD_FIFO:
        result = source_ids[-max_ids:]
    else:  # KEEP — keep oldest
        result = source_ids[:max_ids]

    if identifier:
        logger.debug(
            f"apply_source_ids_limit: trimmed {len(source_ids)} → {max_ids} for {identifier} ({method})"
        )
    return result


def merge_source_ids(existing: list[str], new_ids: list[str]) -> list[str]:
    """Merge two lists of chunk IDs, deduplicating while preserving order.

    Appends new_ids not already in existing.
    """
    seen = set(existing)
    merged = list(existing)
    for id_ in new_ids:
        if id_ and id_ not in seen:
            merged.append(id_)
            seen.add(id_)
    return merged


def source_ids_to_str(source_ids: list[str]) -> str:
    """Join a list of chunk IDs into a GRAPH_FIELD_SEP-delimited string for storage."""
    return GRAPH_FIELD_SEP.join(s for s in source_ids if s)


def make_relation_chunk_key(src: str, tgt: str) -> str:
    """Canonical (sorted) key for an undirected edge."""
    return GRAPH_FIELD_SEP.join(sorted([src, tgt]))


try:
    import json_repair as _json_repair_mod
    _HAS_JSON_REPAIR = True
except ImportError:
    _json_repair_mod = None  # type: ignore[assignment]
    _HAS_JSON_REPAIR = False


def parse_json_robust(text: str) -> dict | None:
    """Parse JSON from LLM output, using json_repair as fallback."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if _HAS_JSON_REPAIR:
        try:
            result = _json_repair_mod.loads(text)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# File path helpers for entity metadata
# ---------------------------------------------------------------------------

def merge_file_paths(existing: str | None, new_paths: list[str], max_paths: int = 100) -> str:
    """Merge new file paths into existing pipe-delimited file_path string."""
    existing_list = [p for p in (existing or "").split("<SEP>") if p.strip()]
    for p in new_paths:
        if p and p not in existing_list:
            existing_list.append(p)
    if len(existing_list) > max_paths:
        existing_list = existing_list[:max_paths]
    return GRAPH_FIELD_SEP.join(existing_list)


# ---------------------------------------------------------------------------
# OpenAI-specific wrappers (FYP implementations)
# ---------------------------------------------------------------------------

@wrap_embedding_func_with_attrs(
    embedding_dim=1536,
    max_token_size=8191,
    model_name="text-embedding-3-small",
)
async def openai_embedding_func(texts: list[str]) -> np.ndarray:
    """
    Async embedding function using OpenAI text-embedding-3-small.
    Returns a (N, 1536) numpy array.
    """
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Batch calls: OpenAI allows up to 2048 inputs per call
    batch_size = 256
    all_embeddings = []
    t0 = time.monotonic()

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await client.embeddings.create(
            input=batch,
            model="text-embedding-3-small",
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    elapsed = time.monotonic() - t0
    logger.debug(
        f"Embedding: {len(texts)} texts → {len(all_embeddings)} vectors "
        f"({elapsed:.2f}s, model=text-embedding-3-small)"
    )
    return np.array(all_embeddings, dtype=np.float32)


async def openai_llm_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    model: str | None = None,
    **kwargs,
) -> str:
    """
    Async LLM function using OpenAI GPT-4o-mini.
    Matches LightRAG's expected llm_model_func signature.
    """
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    llm_model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    t0 = time.monotonic()
    response = await client.chat.completions.create(
        model=llm_model,
        messages=messages,
        temperature=kwargs.get("temperature", 0.2),
        max_tokens=kwargs.get("max_tokens", 2048),
    )
    elapsed = time.monotonic() - t0
    content = response.choices[0].message.content or ""
    usage = response.usage
    logger.debug(
        f"LLM call: model={llm_model} prompt_tokens={usage.prompt_tokens} "
        f"completion_tokens={usage.completion_tokens} elapsed={elapsed:.2f}s "
        f"response_len={len(content)}"
    )
    return content


async def openai_vision_func(
    prompt: str,
    image_data: str,  # base64-encoded image
    system_prompt: str | None = None,
    image_media_type: str = "image/jpeg",
    **kwargs,
) -> str:
    """
    Async vision function using GPT-4o for image analysis.
    image_data: base64-encoded image bytes (no data URI prefix).
    """
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    vision_model = os.getenv("VISION_MODEL", "gpt-4o")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_media_type};base64,{image_data}",
                    "detail": "auto",
                },
            },
            {"type": "text", "text": prompt},
        ],
    })

    response = await client.chat.completions.create(
        model=vision_model,
        messages=messages,
        max_tokens=kwargs.get("max_tokens", 2048),
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Safe VDB operation with retry
# ---------------------------------------------------------------------------

async def safe_vdb_operation_with_exception(
    operation: Callable,
    operation_name: str,
    entity_name: str = "",
    max_retries: int = 3,
    retry_delay: float = 0.2,
) -> None:
    for attempt in range(max_retries):
        try:
            await operation()
            return
        except Exception as e:
            if attempt >= max_retries - 1:
                raise Exception(
                    f"VDB {operation_name} failed for '{entity_name}' after {max_retries} attempts: {e}"
                ) from e
            logger.warning(
                f"VDB {operation_name} attempt {attempt + 1} failed for '{entity_name}': {e}, retrying..."
            )
            if retry_delay > 0:
                await asyncio.sleep(retry_delay)
