"""
Core RAG pipeline operations: chunking, entity extraction, merging, querying.
Ported from LightRAG/lightrag/operate.py and adapted for the FYP stack.

Simplifications vs upstream LightRAG:
- No cancellation tokens or PipelineCancelledException
- No distributed keyed locks (asyncio.Semaphore only)
- No streaming support (all responses are plain strings)
- No reranking
- No performance timing decorators
- No rebuild_knowledge_from_chunks (deletion handled at engine level)
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import Counter, defaultdict
from typing import Any

try:
    import json_repair
    _HAS_JSON_REPAIR = True
except ImportError:
    _HAS_JSON_REPAIR = False

from app.rag.base import (
    BaseGraphStorage,
    BaseKVStorage,
    BaseVectorStorage,
    QueryParam,
    QueryResult,
    TextChunkSchema,
)
from app.rag.constants import (
    DEFAULT_ENTITY_TYPES,
    DEFAULT_MAX_ENTITY_TOKENS,
    DEFAULT_MAX_RELATION_TOKENS,
    DEFAULT_MAX_TOTAL_TOKENS,
    DEFAULT_RELATED_CHUNK_NUMBER,
    DEFAULT_SUMMARY_LANGUAGE,
    GRAPH_FIELD_SEP,
    SOURCE_IDS_LIMIT_METHOD_KEEP,
    SOURCE_IDS_LIMIT_METHOD_FIFO,
)
from app.rag.prompt import PROMPTS
from app.rag.utils import (
    CacheData,
    Tokenizer,
    _cooperative_yield,
    apply_source_ids_limit,
    compute_args_hash,
    compute_mdhash_id,
    fix_tuple_delimiter_corruption,
    handle_cache,
    is_float_regex,
    logger,
    make_relation_chunk_key,
    merge_source_ids,
    pack_user_ass_to_openai_messages,
    remove_think_tags,
    safe_vdb_operation_with_exception,
    sanitize_and_normalize_extracted_text,
    save_to_cache,
    source_ids_to_str,
    split_string_by_multi_markers,
    truncate_list_by_token_size,
    use_llm_func_with_cache,
)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunking_by_token_size(
    tokenizer: Tokenizer,
    content: str,
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    chunk_overlap_token_size: int = 100,
    chunk_token_size: int = 800,
) -> list[dict[str, Any]]:
    """Split content into token-bounded chunks with optional character-level pre-split."""
    tokens = tokenizer.encode(content)
    results: list[dict[str, Any]] = []

    if split_by_character:
        raw_chunks = content.split(split_by_character)
        new_chunks: list[tuple[int, str]] = []

        if split_by_character_only:
            for chunk in raw_chunks:
                _tokens = tokenizer.encode(chunk)
                new_chunks.append((len(_tokens), chunk))
        else:
            for chunk in raw_chunks:
                _tokens = tokenizer.encode(chunk)
                if len(_tokens) > chunk_token_size:
                    for start in range(
                        0, len(_tokens), chunk_token_size - chunk_overlap_token_size
                    ):
                        chunk_content = tokenizer.decode(
                            _tokens[start : start + chunk_token_size]
                        )
                        new_chunks.append(
                            (
                                min(chunk_token_size, len(_tokens) - start),
                                chunk_content,
                            )
                        )
                else:
                    new_chunks.append((len(_tokens), chunk))

        for index, (_len, chunk) in enumerate(new_chunks):
            results.append(
                {
                    "tokens": _len,
                    "content": chunk.strip(),
                    "chunk_order_index": index,
                }
            )
    else:
        for index, start in enumerate(
            range(0, len(tokens), chunk_token_size - chunk_overlap_token_size)
        ):
            chunk_content = tokenizer.decode(tokens[start : start + chunk_token_size])
            results.append(
                {
                    "tokens": min(chunk_token_size, len(tokens) - start),
                    "content": chunk_content.strip(),
                    "chunk_order_index": index,
                }
            )

    return results


# ---------------------------------------------------------------------------
# Entity / relation description summarization
# ---------------------------------------------------------------------------

async def _summarize_descriptions(
    description_type: str,
    description_name: str,
    description_list: list[str],
    global_config: dict,
    llm_response_cache: BaseKVStorage | None = None,
) -> str:
    """Summarize a list of descriptions into one using the LLM."""
    use_llm_func = global_config["llm_model_func"]
    language = global_config["addon_params"].get("language", DEFAULT_SUMMARY_LANGUAGE)
    summary_length = global_config.get("summary_length_recommended", 500)
    tokenizer: Tokenizer = global_config["tokenizer"]
    summary_context_size = global_config.get("summary_context_size", 4000)

    json_descriptions = [{"Description": desc} for desc in description_list]
    truncated = truncate_list_by_token_size(
        json_descriptions,
        key=lambda x: json.dumps(x, ensure_ascii=False),
        max_token_size=summary_context_size,
        tokenizer=tokenizer,
    )
    joined = "\n".join(json.dumps(d, ensure_ascii=False) for d in truncated)

    prompt = PROMPTS["summarize_entity_descriptions"].format(
        description_type=description_type,
        description_name=description_name,
        description_list=joined,
        summary_length=summary_length,
        language=language,
    )
    result, _ = await use_llm_func_with_cache(
        prompt,
        use_llm_func,
        llm_response_cache=llm_response_cache,
        cache_type="summary",
    )
    return result


async def _handle_entity_relation_summary(
    description_type: str,
    entity_or_relation_name: str,
    description_list: list[str],
    separator: str,
    global_config: dict,
    llm_response_cache: BaseKVStorage | None = None,
) -> tuple[str, bool]:
    """Map-reduce description summarization. Returns (final_description, llm_was_used)."""
    if not description_list:
        return "", False
    if len(description_list) == 1:
        return description_list[0], False

    tokenizer: Tokenizer = global_config["tokenizer"]
    summary_context_size = global_config.get("summary_context_size", 4000)
    summary_max_tokens = global_config.get("summary_max_tokens", 500)
    force_llm_summary_on_merge = global_config.get("force_llm_summary_on_merge", 10)

    current_list = list(description_list)
    llm_was_used = False

    while True:
        total_tokens = 0
        for i, desc in enumerate(current_list, start=1):
            total_tokens += len(tokenizer.encode(desc))
            await _cooperative_yield(i)

        if total_tokens <= summary_context_size or len(current_list) <= 2:
            if (
                len(current_list) < force_llm_summary_on_merge
                and total_tokens < summary_max_tokens
            ):
                return separator.join(current_list), llm_was_used
            else:
                summary = await _summarize_descriptions(
                    description_type,
                    entity_or_relation_name,
                    current_list,
                    global_config,
                    llm_response_cache,
                )
                return summary, True

        # Map phase: split into chunks
        chunks: list[list[str]] = []
        current_chunk: list[str] = []
        current_tokens = 0

        for desc in current_list:
            desc_tokens = len(tokenizer.encode(desc))
            if current_tokens + desc_tokens > summary_context_size and current_chunk:
                if len(current_chunk) == 1:
                    current_chunk.append(desc)
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_tokens = 0
                else:
                    chunks.append(current_chunk)
                    current_chunk = [desc]
                    current_tokens = desc_tokens
            else:
                current_chunk.append(desc)
                current_tokens += desc_tokens

        if current_chunk:
            chunks.append(current_chunk)

        # Reduce phase
        new_summaries: list[str] = []
        for chunk in chunks:
            if len(chunk) == 1:
                new_summaries.append(chunk[0])
            else:
                summary = await _summarize_descriptions(
                    description_type,
                    entity_or_relation_name,
                    chunk,
                    global_config,
                    llm_response_cache,
                )
                new_summaries.append(summary)
                llm_was_used = True

        current_list = new_summaries


# ---------------------------------------------------------------------------
# Entity / relation tuple parsers
# ---------------------------------------------------------------------------

def _handle_single_entity_extraction(
    record_attributes: list[str],
    chunk_key: str,
    timestamp: int,
    file_path: str = "unknown_source",
) -> dict | None:
    if len(record_attributes) != 4 or "entity" not in record_attributes[0]:
        return None
    try:
        entity_name = sanitize_and_normalize_extracted_text(
            record_attributes[1], remove_inner_quotes=True
        )
        if not entity_name or not entity_name.strip():
            return None

        entity_type = sanitize_and_normalize_extracted_text(
            record_attributes[2], remove_inner_quotes=True
        )
        if not entity_type.strip() or any(
            c in entity_type for c in ["'", "(", ")", "<", ">", "|", "/", "\\"]
        ):
            return None

        if "," in entity_type:
            tokens = [t.strip() for t in entity_type.split(",")]
            non_empty = [t for t in tokens if t]
            if not non_empty:
                return None
            entity_type = non_empty[0]

        entity_type = entity_type.replace(" ", "").lower()
        entity_description = sanitize_and_normalize_extracted_text(record_attributes[3])
        if not entity_description.strip():
            return None

        return dict(
            entity_name=entity_name,
            entity_type=entity_type,
            description=entity_description,
            source_id=chunk_key,
            file_path=file_path,
            timestamp=timestamp,
        )
    except Exception as e:
        logger.warning(f"Entity extraction error in {chunk_key}: {e}")
        return None


def _handle_single_relationship_extraction(
    record_attributes: list[str],
    chunk_key: str,
    timestamp: int,
    file_path: str = "unknown_source",
) -> dict | None:
    if len(record_attributes) != 5 or "relation" not in record_attributes[0]:
        return None
    try:
        source = sanitize_and_normalize_extracted_text(
            record_attributes[1], remove_inner_quotes=True
        )
        target = sanitize_and_normalize_extracted_text(
            record_attributes[2], remove_inner_quotes=True
        )
        if not source or not target or source == target:
            return None

        edge_keywords = sanitize_and_normalize_extracted_text(
            record_attributes[3], remove_inner_quotes=True
        ).replace("，", ",")
        edge_description = sanitize_and_normalize_extracted_text(record_attributes[4])
        if not edge_description.strip():
            return None

        weight = (
            float(record_attributes[-1].strip('"').strip("'"))
            if is_float_regex(record_attributes[-1].strip('"').strip("'"))
            else 1.0
        )

        return dict(
            src_id=source,
            tgt_id=target,
            weight=weight,
            description=edge_description,
            keywords=edge_keywords,
            source_id=chunk_key,
            file_path=file_path,
            timestamp=timestamp,
        )
    except Exception as e:
        logger.warning(f"Relation extraction error in {chunk_key}: {e}")
        return None


async def _process_extraction_result(
    result: str,
    chunk_key: str,
    timestamp: int,
    file_path: str = "unknown_source",
    tuple_delimiter: str = "<|#|>",
    completion_delimiter: str = "<|COMPLETE|>",
) -> tuple[dict, dict]:
    """Parse a raw LLM extraction string into nodes and edges dicts."""
    maybe_nodes: dict[str, list] = defaultdict(list)
    maybe_edges: dict[tuple, list] = defaultdict(list)

    records = split_string_by_multi_markers(
        result,
        ["\n", completion_delimiter, completion_delimiter.lower()],
    )

    # Fix records where tuple_delimiter was used as row separator
    fixed_records: list[str] = []
    for i, record in enumerate(records, start=1):
        record = record.strip()
        if not record:
            continue
        entity_records = split_string_by_multi_markers(
            record, [f"{tuple_delimiter}entity{tuple_delimiter}"]
        )
        for entity_record in entity_records:
            if not entity_record.startswith("entity") and not entity_record.startswith("relation"):
                entity_record = f"entity{tuple_delimiter}{entity_record}"
            rel_records = split_string_by_multi_markers(
                entity_record,
                [
                    f"{tuple_delimiter}relationship{tuple_delimiter}",
                    f"{tuple_delimiter}relation{tuple_delimiter}",
                ],
            )
            for rel_record in rel_records:
                if not rel_record.startswith("entity") and not rel_record.startswith("relation"):
                    rel_record = f"relation{tuple_delimiter}{rel_record}"
                fixed_records.append(rel_record)
        await _cooperative_yield(i)

    delimiter_core = tuple_delimiter[2:-2]  # "#" from "<|#|>"
    for i, record in enumerate(fixed_records, start=1):
        record = record.strip()
        if not record:
            continue
        record = fix_tuple_delimiter_corruption(record, delimiter_core, tuple_delimiter)

        attrs = split_string_by_multi_markers(record, [tuple_delimiter])

        entity_data = _handle_single_entity_extraction(attrs, chunk_key, timestamp, file_path)
        if entity_data is not None:
            maybe_nodes[entity_data["entity_name"]].append(entity_data)
            await _cooperative_yield(i)
            continue

        rel_data = _handle_single_relationship_extraction(attrs, chunk_key, timestamp, file_path)
        if rel_data is not None:
            maybe_edges[(rel_data["src_id"], rel_data["tgt_id"])].append(rel_data)
        await _cooperative_yield(i)

    return dict(maybe_nodes), dict(maybe_edges)


# ---------------------------------------------------------------------------
# Entity extraction (insert pipeline)
# ---------------------------------------------------------------------------

async def extract_entities(
    chunks: dict[str, TextChunkSchema],
    global_config: dict,
    llm_response_cache: BaseKVStorage | None = None,
) -> list[tuple[dict, dict]]:
    """Run LLM entity extraction on all chunks. Returns list of (nodes, edges) per chunk."""
    use_llm_func = global_config["llm_model_func"]
    entity_extract_max_gleaning = global_config.get("entity_extract_max_gleaning", 1)
    language = global_config["addon_params"].get("language", DEFAULT_SUMMARY_LANGUAGE)
    entity_types = global_config["addon_params"].get("entity_types", DEFAULT_ENTITY_TYPES)
    tokenizer: Tokenizer = global_config["tokenizer"]
    max_extract_input_tokens = global_config.get("max_extract_input_tokens", 32000)

    examples = "\n".join(PROMPTS["entity_extraction_examples"])
    context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=",".join(entity_types),
        examples=examples.format(
            tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
            completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
            entity_types=", ".join(entity_types),
            language=language,
        ),
        language=language,
    )

    ordered_chunks = list(chunks.items())
    total_chunks = len(ordered_chunks)
    processed_chunks = 0
    logger.info("extract_entities: starting on %d chunks", total_chunks)

    async def _process_single_chunk(
        chunk_key: str, chunk_dp: TextChunkSchema
    ) -> tuple[dict, dict]:
        nonlocal processed_chunks
        _chunk_t0 = time.time()
        content = chunk_dp["content"]
        file_path = chunk_dp.get("file_path", "unknown_source")
        logger.debug("extract_entities: chunk %s start (file=%s)", chunk_key[:16], file_path)

        system_prompt = PROMPTS["entity_extraction_system_prompt"].format(**context_base)
        user_prompt = PROMPTS["entity_extraction_user_prompt"].format(
            **{**context_base, "input_text": content}
        )
        continue_prompt = PROMPTS["entity_continue_extraction_user_prompt"].format(
            **{**context_base, "input_text": content}
        )

        final_result, timestamp = await use_llm_func_with_cache(
            user_prompt,
            use_llm_func,
            llm_response_cache=llm_response_cache,
            system_prompt=system_prompt,
            cache_type="extract",
            chunk_id=chunk_key,
        )

        history = pack_user_ass_to_openai_messages(user_prompt, final_result)

        maybe_nodes, maybe_edges = await _process_extraction_result(
            final_result,
            chunk_key,
            timestamp,
            file_path,
            tuple_delimiter=context_base["tuple_delimiter"],
            completion_delimiter=context_base["completion_delimiter"],
        )

        # Gleaning: one follow-up extraction pass
        if entity_extract_max_gleaning > 0:
            full_ctx = system_prompt + json.dumps(history) + continue_prompt
            if len(tokenizer.encode(full_ctx)) <= max_extract_input_tokens:
                glean_result, glean_ts = await use_llm_func_with_cache(
                    continue_prompt,
                    use_llm_func,
                    llm_response_cache=llm_response_cache,
                    system_prompt=system_prompt,
                    history_messages=history,
                    cache_type="extract",
                    chunk_id=chunk_key,
                )
                glean_nodes, glean_edges = await _process_extraction_result(
                    glean_result,
                    chunk_key,
                    glean_ts,
                    file_path,
                    tuple_delimiter=context_base["tuple_delimiter"],
                    completion_delimiter=context_base["completion_delimiter"],
                )
                # Merge gleaning results (keep longer description)
                for ename, glean_list in glean_nodes.items():
                    if ename in maybe_nodes:
                        orig_len = len(maybe_nodes[ename][0].get("description", "") or "")
                        new_len = len(glean_list[0].get("description", "") or "")
                        if new_len > orig_len:
                            maybe_nodes[ename] = list(glean_list)
                    else:
                        maybe_nodes[ename] = list(glean_list)
                for ekey, glean_list in glean_edges.items():
                    if ekey in maybe_edges:
                        orig_len = len(maybe_edges[ekey][0].get("description", "") or "")
                        new_len = len(glean_list[0].get("description", "") or "")
                        if new_len > orig_len:
                            maybe_edges[ekey] = list(glean_list)
                    else:
                        maybe_edges[ekey] = list(glean_list)

        processed_chunks += 1
        logger.info(
            "extract_entities: chunk %d/%d done in %.2fs — %d entities, %d relations [%s]",
            processed_chunks, total_chunks, time.time() - _chunk_t0,
            len(maybe_nodes), len(maybe_edges), chunk_key[:16],
        )
        return maybe_nodes, maybe_edges

    chunk_max_async = global_config.get("llm_model_max_async", 4)
    semaphore = asyncio.Semaphore(chunk_max_async)

    async def _run_with_sem(chunk_key: str, chunk_dp: TextChunkSchema):
        async with semaphore:
            return await _process_single_chunk(chunk_key, chunk_dp)

    tasks = [
        asyncio.create_task(_run_with_sem(k, v)) for k, v in ordered_chunks
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    logger.debug("extract_entities: %d tasks done, %d pending", len(done), len(pending))

    first_exception = None
    results: list[tuple[dict, dict]] = []

    for task in done:
        try:
            exception = task.exception()
            if exception is not None:
                if first_exception is None:
                    first_exception = exception
                else:
                    logger.debug(
                        "extract_entities: additional task failure suppressed "
                        "(first already captured): %s", exception
                    )
            else:
                results.append(task.result())
        except Exception as e:
            if first_exception is None:
                first_exception = e

    if first_exception is not None:
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.wait(pending)
        raise first_exception

    total_entities = sum(len(r[0]) for r in results)
    total_edges = sum(len(r[1]) for r in results)
    logger.info(
        "extract_entities: complete — %d chunks processed, %d entity mentions, %d relation mentions",
        len(results), total_entities, total_edges,
    )
    return results


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

async def _merge_nodes_then_upsert(
    entity_name: str,
    nodes_data: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    entity_vdb: BaseVectorStorage | None,
    global_config: dict,
    llm_response_cache: BaseKVStorage | None = None,
    entity_chunks_storage: BaseKVStorage | None = None,
) -> dict | None:
    """Merge entity data from multiple chunks, upsert to graph + vector DB."""
    already_entity_types: list[str] = []
    already_source_ids: list[str] = []
    already_description: list[str] = []
    already_file_paths: list[str] = []

    already_node = await knowledge_graph_inst.get_node(entity_name)
    if already_node:
        etype = already_node.get("entity_type", "UNKNOWN")
        if not isinstance(etype, str) or not etype.strip():
            etype = "UNKNOWN"
        if "," in etype:
            tokens = [t.strip() for t in etype.split(",")]
            etype = next((t for t in tokens if t), "UNKNOWN")
        already_entity_types.append(etype)

        src_str = already_node.get("source_id") or ""
        already_source_ids = [s for s in src_str.split(GRAPH_FIELD_SEP) if s]

        fp_str = already_node.get("file_path") or ""
        already_file_paths = [f for f in fp_str.split(GRAPH_FIELD_SEP) if f]

        desc_str = (already_node.get("description") or "").strip()
        if desc_str:
            already_description = [desc_str]

    new_source_ids = [dp["source_id"] for dp in nodes_data if dp.get("source_id")]

    # Full source id tracking
    existing_full_source_ids: list[str] = []
    if entity_chunks_storage is not None:
        stored = await entity_chunks_storage.get_by_id(entity_name)
        if stored and isinstance(stored, dict):
            existing_full_source_ids = [c for c in stored.get("chunk_ids", []) if c]
    if not existing_full_source_ids:
        existing_full_source_ids = list(already_source_ids)

    full_source_ids = merge_source_ids(existing_full_source_ids, new_source_ids)

    if entity_chunks_storage is not None and full_source_ids:
        await entity_chunks_storage.upsert(
            {entity_name: {"chunk_ids": full_source_ids, "count": len(full_source_ids)}}
        )

    limit_method = global_config.get("source_ids_limit_method", SOURCE_IDS_LIMIT_METHOD_KEEP)
    max_source_limit = global_config.get("max_source_ids_per_entity", 50)
    source_ids = apply_source_ids_limit(full_source_ids, max_source_limit, limit_method)
    source_id = source_ids_to_str(source_ids)

    # Best-vote entity type
    entity_type = sorted(
        Counter(
            [dp["entity_type"] for dp in nodes_data] + already_entity_types
        ).items(),
        key=lambda x: x[1],
        reverse=True,
    )[0][0] if nodes_data or already_entity_types else "UNKNOWN"

    # Deduplicate by description text
    unique_nodes: dict[str, dict] = {}
    for i, dp in enumerate(nodes_data, start=1):
        desc = dp.get("description")
        if desc and desc not in unique_nodes:
            unique_nodes[desc] = dp
        await _cooperative_yield(i)

    sorted_nodes = sorted(
        unique_nodes.values(),
        key=lambda x: (x.get("timestamp", 0), -len(x.get("description", ""))),
    )
    sorted_descriptions = [dp["description"] for dp in sorted_nodes]
    description_list = already_description + sorted_descriptions

    if not description_list:
        description_list = [f"Entity {entity_name}"]

    description, llm_was_used = await _handle_entity_relation_summary(
        "Entity",
        entity_name,
        description_list,
        GRAPH_FIELD_SEP,
        global_config,
        llm_response_cache,
    )

    # Build file_path
    seen_paths: set[str] = set()
    file_paths_list: list[str] = []
    for fp in already_file_paths + [dp.get("file_path", "") for dp in nodes_data]:
        if fp and fp not in seen_paths:
            file_paths_list.append(fp)
            seen_paths.add(fp)
    file_path = GRAPH_FIELD_SEP.join(file_paths_list)

    node_data = dict(
        entity_id=entity_name,
        entity_type=entity_type,
        description=description,
        source_id=source_id,
        file_path=file_path,
        created_at=int(time.time()),
    )
    await knowledge_graph_inst.upsert_node(entity_name, node_data=node_data)
    node_data["entity_name"] = entity_name

    if entity_vdb is not None:
        vdb_id = compute_mdhash_id(entity_name, prefix="ent-")
        vdb_content = f"{entity_name}\n{description}"
        vdb_payload = {
            vdb_id: {
                "entity_name": entity_name,
                "entity_type": entity_type,
                "content": vdb_content,
                "source_id": source_id,
                "file_path": file_path,
            }
        }
        await safe_vdb_operation_with_exception(
            operation=lambda p=vdb_payload: entity_vdb.upsert(p),
            operation_name="entity_upsert",
            entity_name=entity_name,
        )

    if llm_was_used:
        logger.info(f"LLMmrg: `{entity_name}`")
    else:
        logger.debug(f"Merged: `{entity_name}`")
    return node_data


async def _merge_edges_then_upsert(
    src_id: str,
    tgt_id: str,
    edges_data: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    relationships_vdb: BaseVectorStorage | None,
    entity_vdb: BaseVectorStorage | None,
    global_config: dict,
    llm_response_cache: BaseKVStorage | None = None,
    added_entities: list | None = None,
    relation_chunks_storage: BaseKVStorage | None = None,
    entity_chunks_storage: BaseKVStorage | None = None,
) -> dict | None:
    """Merge relationship data from multiple chunks, upsert to graph + vector DB."""
    if src_id == tgt_id:
        return None

    already_weights: list[float] = []
    already_source_ids: list[str] = []
    already_description: list[str] = []
    already_keywords: list[str] = []
    already_file_paths: list[str] = []

    if await knowledge_graph_inst.has_edge(src_id, tgt_id):
        already_edge = await knowledge_graph_inst.get_edge(src_id, tgt_id)
        if already_edge:
            already_weights.append(float(already_edge.get("weight", 1.0)))
            src_str = already_edge.get("source_id") or ""
            already_source_ids = [s for s in src_str.split(GRAPH_FIELD_SEP) if s]
            fp_str = already_edge.get("file_path") or ""
            already_file_paths = [f for f in fp_str.split(GRAPH_FIELD_SEP) if f]
            desc_str = already_edge.get("description") or ""
            if desc_str:
                already_description = [desc_str]
            kw_str = already_edge.get("keywords") or ""
            if kw_str:
                already_keywords = [kw_str]

    new_source_ids = [dp["source_id"] for dp in edges_data if dp.get("source_id")]

    storage_key = make_relation_chunk_key(src_id, tgt_id)
    existing_full_source_ids: list[str] = []
    if relation_chunks_storage is not None:
        stored = await relation_chunks_storage.get_by_id(storage_key)
        if stored and isinstance(stored, dict):
            existing_full_source_ids = [c for c in stored.get("chunk_ids", []) if c]
    if not existing_full_source_ids:
        existing_full_source_ids = list(already_source_ids)

    full_source_ids = merge_source_ids(existing_full_source_ids, new_source_ids)
    if relation_chunks_storage is not None and full_source_ids:
        await relation_chunks_storage.upsert(
            {storage_key: {"chunk_ids": full_source_ids, "count": len(full_source_ids)}}
        )

    limit_method = global_config.get("source_ids_limit_method", SOURCE_IDS_LIMIT_METHOD_KEEP)
    max_source_limit = global_config.get("max_source_ids_per_relation", 50)
    source_ids = apply_source_ids_limit(full_source_ids, max_source_limit, limit_method)
    source_id = source_ids_to_str(source_ids)

    weight = sum([dp["weight"] for dp in edges_data] + already_weights)

    # Merge keywords
    all_kw: set[str] = set()
    for kw_str in already_keywords:
        all_kw.update(k.strip() for k in kw_str.split(",") if k.strip())
    for dp in edges_data:
        if dp.get("keywords"):
            all_kw.update(k.strip() for k in dp["keywords"].split(",") if k.strip())
    keywords = ",".join(sorted(all_kw))

    # Deduplicate descriptions
    unique_edges: dict[str, dict] = {}
    for dp in edges_data:
        desc = dp.get("description")
        if desc and desc not in unique_edges:
            unique_edges[desc] = dp

    sorted_edges = sorted(
        unique_edges.values(),
        key=lambda x: (x.get("timestamp", 0), -len(x.get("description", ""))),
    )
    description_list = already_description + [dp["description"] for dp in sorted_edges]

    if not description_list:
        logger.warning(f"Relation {src_id}~{tgt_id} has no description; skipping")
        return None

    description, llm_was_used = await _handle_entity_relation_summary(
        "Relation",
        f"({src_id}, {tgt_id})",
        description_list,
        GRAPH_FIELD_SEP,
        global_config,
        llm_response_cache,
    )

    # Build file_path
    seen_paths: set[str] = set()
    file_paths_list: list[str] = []
    for fp in already_file_paths + [dp.get("file_path", "") for dp in edges_data]:
        if fp and fp not in seen_paths:
            file_paths_list.append(fp)
            seen_paths.add(fp)
    file_path = GRAPH_FIELD_SEP.join(file_paths_list)

    created_at = int(time.time())

    # Ensure both endpoint nodes exist
    for need_id in [src_id, tgt_id]:
        existing_node = await knowledge_graph_inst.get_node(need_id)
        if existing_node is None:
            node_data = {
                "entity_id": need_id,
                "source_id": source_id,
                "description": description,
                "entity_type": "UNKNOWN",
                "file_path": file_path,
                "created_at": created_at,
            }
            await knowledge_graph_inst.upsert_node(need_id, node_data=node_data)
            if entity_chunks_storage is not None and full_source_ids:
                await entity_chunks_storage.upsert(
                    {need_id: {"chunk_ids": full_source_ids, "count": len(full_source_ids)}}
                )
            if entity_vdb is not None:
                vdb_id = compute_mdhash_id(need_id, prefix="ent-")
                vdb_payload = {
                    vdb_id: {
                        "content": f"{need_id}\n{description}",
                        "entity_name": need_id,
                        "source_id": source_id,
                        "entity_type": "UNKNOWN",
                        "file_path": file_path,
                    }
                }
                await safe_vdb_operation_with_exception(
                    operation=lambda p=vdb_payload: entity_vdb.upsert(p),
                    operation_name="added_entity_upsert",
                    entity_name=need_id,
                )
            if added_entities is not None:
                added_entities.append({"entity_name": need_id, "entity_type": "UNKNOWN"})

    await knowledge_graph_inst.upsert_edge(
        src_id,
        tgt_id,
        edge_data=dict(
            weight=weight,
            description=description,
            keywords=keywords,
            source_id=source_id,
            file_path=file_path,
            created_at=created_at,
        ),
    )

    # VDB: sort src/tgt alphabetically for stable ID
    sorted_src, sorted_tgt = (src_id, tgt_id) if src_id <= tgt_id else (tgt_id, src_id)
    if relationships_vdb is not None:
        rel_vdb_id = compute_mdhash_id(sorted_src + sorted_tgt, prefix="rel-")
        rel_vdb_id_rev = compute_mdhash_id(sorted_tgt + sorted_src, prefix="rel-")
        try:
            await relationships_vdb.delete([rel_vdb_id, rel_vdb_id_rev])
        except Exception as vdb_del_exc:
            logger.warning(
                "_merge_edges_then_upsert: VDB delete failed for %s~%s: %s",
                src_id, tgt_id, vdb_del_exc,
            )
        rel_content = f"{keywords}\t{sorted_src}\n{sorted_tgt}\n{description}"
        vdb_payload = {
            rel_vdb_id: {
                "src_id": sorted_src,
                "tgt_id": sorted_tgt,
                "source_id": source_id,
                "content": rel_content,
                "keywords": keywords,
                "description": description,
                "weight": weight,
                "file_path": file_path,
            }
        }
        await safe_vdb_operation_with_exception(
            operation=lambda p=vdb_payload: relationships_vdb.upsert(p),
            operation_name="relationship_upsert",
            entity_name=f"{sorted_src}-{sorted_tgt}",
        )

    if llm_was_used:
        logger.info(f"LLMmrg: `{src_id}`~`{tgt_id}`")
    else:
        logger.debug(f"Merged: `{src_id}`~`{tgt_id}`")

    return dict(
        src_id=src_id,
        tgt_id=tgt_id,
        description=description,
        keywords=keywords,
        source_id=source_id,
        file_path=file_path,
        weight=weight,
    )


# ---------------------------------------------------------------------------
# Two-phase merge orchestration
# ---------------------------------------------------------------------------

async def merge_nodes_and_edges(
    chunk_results: list[tuple[dict, dict]],
    knowledge_graph_inst: BaseGraphStorage,
    entity_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    global_config: dict,
    full_entities_storage: BaseKVStorage | None = None,
    full_relations_storage: BaseKVStorage | None = None,
    doc_id: str | None = None,
    llm_response_cache: BaseKVStorage | None = None,
    entity_chunks_storage: BaseKVStorage | None = None,
    relation_chunks_storage: BaseKVStorage | None = None,
    file_path: str = "unknown_source",
) -> list[str]:
    """Phase 1: process all entities; Phase 2: process all relationships.

    Returns the list of entity names that were merged/upserted.
    Used by modal processors to build belongs_to edges.
    """

    # Aggregate all nodes and edges from all chunks
    all_nodes: dict[str, list] = defaultdict(list)
    all_edges: dict[tuple, list] = defaultdict(list)

    for i, (maybe_nodes, maybe_edges) in enumerate(chunk_results, start=1):
        for ename, entities in maybe_nodes.items():
            all_nodes[ename].extend(entities)
        for edge_key, edges in maybe_edges.items():
            sorted_key = tuple(sorted(edge_key))
            all_edges[sorted_key].extend(edges)
        await _cooperative_yield(i)

    _merge_t0 = time.time()
    logger.info(
        "merge_nodes_and_edges: %d entities, %d relations from %s",
        len(all_nodes), len(all_edges), file_path,
    )

    graph_max_async = global_config.get("llm_model_max_async", 4) * 2
    semaphore = asyncio.Semaphore(graph_max_async)

    # ---- Phase 1: entities ----
    processed_entities: list[dict] = []

    async def _process_entity(ename: str, entities: list[dict]):
        async with semaphore:
            return await _merge_nodes_then_upsert(
                ename,
                entities,
                knowledge_graph_inst,
                entity_vdb,
                global_config,
                llm_response_cache,
                entity_chunks_storage,
            )

    entity_tasks = [
        asyncio.create_task(_process_entity(ename, entities))
        for ename, entities in all_nodes.items()
    ]
    if entity_tasks:
        done, pending = await asyncio.wait(entity_tasks, return_when=asyncio.FIRST_EXCEPTION)
        first_exc = None
        for task in done:
            try:
                exc = task.exception()
                if exc is not None:
                    if first_exc is None:
                        first_exc = exc
                    else:
                        logger.debug(
                            "merge entities: additional task failure suppressed: %s", exc
                        )
                else:
                    result = task.result()
                    if result:
                        processed_entities.append(result)
            except Exception as e:
                if first_exc is None:
                    first_exc = e
        if pending:
            for t in pending:
                t.cancel()
            await asyncio.wait(pending)
        if first_exc is not None:
            raise first_exc
        logger.info(
            "merge_nodes_and_edges: Phase 1 done — %d entities processed in %.2fs",
            len(processed_entities), time.time() - _merge_t0,
        )
        await asyncio.sleep(0)

    # ---- Phase 2: relationships ----
    processed_edges: list[dict] = []
    all_added_entities: list[dict] = []

    async def _process_edge(edge_key: tuple, edges: list[dict]):
        async with semaphore:
            added: list[dict] = []
            edge_data = await _merge_edges_then_upsert(
                edge_key[0],
                edge_key[1],
                edges,
                knowledge_graph_inst,
                relationships_vdb,
                entity_vdb,
                global_config,
                llm_response_cache,
                added,
                relation_chunks_storage,
                entity_chunks_storage,
            )
            return edge_data, added

    edge_tasks = [
        asyncio.create_task(_process_edge(ekey, edges))
        for ekey, edges in all_edges.items()
    ]
    if edge_tasks:
        done, pending = await asyncio.wait(edge_tasks, return_when=asyncio.FIRST_EXCEPTION)
        first_exc = None
        for task in done:
            try:
                exc = task.exception()
                if exc is not None:
                    if first_exc is None:
                        first_exc = exc
                    else:
                        logger.debug(
                            "merge edges: additional task failure suppressed: %s", exc
                        )
                else:
                    edge_data, added = task.result()
                    if edge_data:
                        processed_edges.append(edge_data)
                    all_added_entities.extend(added)
            except Exception as e:
                if first_exc is None:
                    first_exc = e
        if pending:
            for t in pending:
                t.cancel()
            await asyncio.wait(pending)
        if first_exc is not None:
            raise first_exc
        logger.info(
            "merge_nodes_and_edges: Phase 2 done — %d edges processed, "
            "%d entity additions from edges, total elapsed %.2fs",
            len(processed_edges), len(all_added_entities), time.time() - _merge_t0,
        )
        await asyncio.sleep(0)

    # ---- Phase 3: update full entity/relation index ----
    if full_entities_storage and full_relations_storage and doc_id:
        try:
            entity_names: set[str] = set()
            for e in processed_entities:
                if e and e.get("entity_name"):
                    entity_names.add(e["entity_name"])
            for e in all_added_entities:
                if e and e.get("entity_name"):
                    entity_names.add(e["entity_name"])

            relation_pairs: set[tuple] = set()
            for ed in processed_edges:
                if ed:
                    s, t = ed.get("src_id"), ed.get("tgt_id")
                    if s and t:
                        relation_pairs.add(tuple(sorted([s, t])))

            if entity_names:
                await full_entities_storage.upsert(
                    {doc_id: {"entity_names": list(entity_names), "count": len(entity_names)}}
                )
            if relation_pairs:
                await full_relations_storage.upsert(
                    {doc_id: {"relation_pairs": [list(p) for p in relation_pairs], "count": len(relation_pairs)}}
                )
        except Exception as e:
            logger.error(f"Failed to update entity-relation index for {doc_id}: {e}")

    logger.info(
        f"Merge complete: {len(processed_entities)} entities "
        f"({len(all_added_entities)} added via relations), "
        f"{len(processed_edges)} relations"
    )

    # Collect all entity names for the caller (used by modal processors for belongs_to edges)
    all_entity_names: set[str] = set()
    for e in processed_entities:
        if e and e.get("entity_name"):
            all_entity_names.add(e["entity_name"])
    for e in all_added_entities:
        if e and e.get("entity_name"):
            all_entity_names.add(e["entity_name"])
    return list(all_entity_names)


# ---------------------------------------------------------------------------
# Keyword extraction (query routing)
# ---------------------------------------------------------------------------

async def extract_keywords_only(
    text: str,
    param: QueryParam,
    global_config: dict,
    hashing_kv: BaseKVStorage | None = None,
) -> tuple[list[str], list[str]]:
    """Extract high-level and low-level keywords from a query via LLM."""
    language = global_config["addon_params"].get("language", DEFAULT_SUMMARY_LANGUAGE)
    examples = "\n".join(PROMPTS["keywords_extraction_examples"])

    args_hash = compute_args_hash(param.mode, text, language)
    cached = await handle_cache(hashing_kv, args_hash, text, cache_type="keywords")
    if cached is not None:
        try:
            cached_content, _ = cached
            kw_data = _parse_json_robust(cached_content)
            if kw_data:
                return kw_data.get("high_level_keywords", []), kw_data.get("low_level_keywords", [])
        except Exception:
            pass

    kw_prompt = PROMPTS["keywords_extraction"].format(
        query=text,
        examples=examples,
        language=language,
    )

    use_llm_func = global_config["llm_model_func"]
    result = await use_llm_func(kw_prompt)
    result = remove_think_tags(result)

    kw_data = _parse_json_robust(result)
    if not kw_data:
        logger.warning(f"Keyword extraction failed to parse JSON for query: {text[:80]}")
        return [], []

    hl = kw_data.get("high_level_keywords", [])
    ll = kw_data.get("low_level_keywords", [])

    if (hl or ll) and hashing_kv is not None:
        await save_to_cache(
            hashing_kv,
            CacheData(
                args_hash=args_hash,
                content=json.dumps({"high_level_keywords": hl, "low_level_keywords": ll}),
                prompt=text,
            ),
            cache_type="keywords",
        )

    return hl, ll


def _parse_json_robust(text: str) -> dict | None:
    from app.rag.utils import parse_json_robust
    return parse_json_robust(text)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

async def _get_entity_context(
    keywords: str,
    entities_vdb: BaseVectorStorage,
    knowledge_graph_inst: BaseGraphStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict,
    entity_chunks_db: "BaseKVStorage | None" = None,
) -> tuple[list[dict], list[str]]:
    """Search entities VDB → collect seeds from ChromaDB → BFS expand → collect chunk IDs.

    Seeds are built directly from ChromaDB metadata (skipping the redundant
    get_node() round-trip since ChromaDB already holds description + source_id).
    Neighbors are discovered via get_neighbors_with_scores() BFS traversal.
    """
    if not keywords:
        return [], []

    entity_results = await entities_vdb.query(
        keywords, top_k=query_param.top_k, file_filter=query_param.file_filter,
    )
    if not entity_results:
        return [], []

    entity_nodes: list[dict] = []
    chunk_ids: list[str] = []
    seen_chunk_ids: set[str] = set()
    seed_names: list[str] = []

    # --- Seeds: use ChromaDB metadata directly (no Neo4j round-trip needed) ---
    for item in entity_results:
        ename = item.get("entity_name", item.get("id", ""))
        if not ename:
            continue
        # ChromaDB stores content as "entity_name\ndescription"
        content = item.get("content", "")
        _, _, description = content.partition("\n")
        entity_nodes.append({
            "id": ename,
            "entity": ename,
            "type": item.get("entity_type", "UNKNOWN"),
            "description": description,
            "source_id": item.get("source_id", ""),
            "file_path": item.get("file_path", ""),
        })
        seed_names.append(ename)

        # Prefer entity_chunks KV for complete chunk list
        if entity_chunks_db is not None:
            mapping = await entity_chunks_db.get_by_id(ename)
            if mapping:
                for cid in mapping.get("chunk_ids", []):
                    if cid and cid not in seen_chunk_ids:
                        seen_chunk_ids.add(cid)
                        chunk_ids.append(cid)
                continue
        # Fallback: parse source_id from ChromaDB metadata
        src_str = item.get("source_id", "")
        for cid in src_str.split(GRAPH_FIELD_SEP):
            cid = cid.strip()
            if cid and cid not in seen_chunk_ids:
                seen_chunk_ids.add(cid)
                chunk_ids.append(cid)

    # --- BFS expansion from seeds into graph neighborhood ---
    neighbor_nodes, neighbor_chunk_ids = await _expand_graph_neighbors(
        seed_names=seed_names,
        knowledge_graph_inst=knowledge_graph_inst,
        entity_chunks_db=entity_chunks_db,
        query_param=query_param,
    )
    entity_nodes.extend(neighbor_nodes)
    for cid in neighbor_chunk_ids:
        if cid not in seen_chunk_ids:
            seen_chunk_ids.add(cid)
            chunk_ids.append(cid)

    return entity_nodes, chunk_ids


async def _expand_graph_neighbors(
    seed_names: list[str],
    knowledge_graph_inst: BaseGraphStorage,
    entity_chunks_db: "BaseKVStorage | None",
    query_param: QueryParam,
) -> tuple[list[dict], list[str]]:
    """BFS from seed entity names into Neo4j graph neighborhood.
    Uses entity_chunks KV for complete chunk lists when available,
    falling back to node.source_id (may be truncated at 50 entries).
    """
    if not seed_names or query_param.traversal_hops < 1:
        return [], []

    neighbors = await knowledge_graph_inst.get_neighbors_with_scores(
        entity_ids=seed_names,
        max_hops=query_param.traversal_hops,
        max_results=query_param.max_graph_neighbors,
        exclude_ids=set(seed_names),
        file_filter=query_param.file_filter,
    )

    neighbor_nodes: list[dict] = []
    chunk_ids: list[str] = []
    seen_chunk_ids: set[str] = set()

    for n in neighbors:
        eid = n.get("entity_id", "")
        if not eid:
            continue
        neighbor_nodes.append({
            "id": eid,
            "entity": eid,
            "type": n.get("entity_type", "UNKNOWN"),
            "description": n.get("description", ""),
            "source_id": n.get("source_id", ""),
            "file_path": n.get("file_path", ""),
            "hop_distance": n.get("hop_distance", 1),
            "graph_score": round(float(n.get("best_score", 0.0)), 4),
        })

        if entity_chunks_db is not None:
            mapping = await entity_chunks_db.get_by_id(eid)
            if mapping:
                for cid in mapping.get("chunk_ids", []):
                    if cid and cid not in seen_chunk_ids:
                        seen_chunk_ids.add(cid)
                        chunk_ids.append(cid)
                continue

        # Fallback: parse source_id from node (may be truncated to 50 entries)
        src_str = n.get("source_id", "")
        for cid in src_str.split(GRAPH_FIELD_SEP):
            cid = cid.strip()
            if cid and cid not in seen_chunk_ids:
                seen_chunk_ids.add(cid)
                chunk_ids.append(cid)

    return neighbor_nodes, chunk_ids


async def _get_relation_context(
    keywords: str,
    relationships_vdb: BaseVectorStorage,
    knowledge_graph_inst: BaseGraphStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict,
) -> tuple[list[dict], list[str]]:
    """Search relationships VDB → fetch graph edges → collect related chunk IDs."""
    if not keywords:
        return [], []

    top_k = query_param.top_k
    rel_results = await relationships_vdb.query(
        keywords, top_k=top_k, file_filter=query_param.file_filter,
    )
    if not rel_results:
        return [], []

    relations: list[dict] = []
    chunk_ids: list[str] = []

    for item in rel_results:
        src_id = item.get("src_id", "")
        tgt_id = item.get("tgt_id", "")
        if not src_id or not tgt_id:
            continue
        edge = await knowledge_graph_inst.get_edge(src_id, tgt_id)
        if edge is None:
            continue
        relations.append({
            "id": f"{src_id}-{tgt_id}",
            "src": src_id,
            "tgt": tgt_id,
            "keywords": edge.get("keywords", ""),
            "description": edge.get("description", ""),
            "weight": edge.get("weight", 1.0),
            "source_id": edge.get("source_id", ""),
            "file_path": edge.get("file_path", ""),
        })
        src_str = edge.get("source_id", "")
        for cid in src_str.split(GRAPH_FIELD_SEP):
            if cid.strip() and cid not in chunk_ids:
                chunk_ids.append(cid.strip())

    return relations, chunk_ids


async def _fetch_text_chunks(
    chunk_ids: list[str],
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict,
    max_tokens: int,
) -> list[dict]:
    """Fetch and token-truncate text chunks from KV store."""
    if not chunk_ids:
        return []

    tokenizer: Tokenizer | None = global_config.get("tokenizer")
    related_chunk_number = global_config.get(
        "related_chunk_number", DEFAULT_RELATED_CHUNK_NUMBER
    )
    # Limit IDs considered
    chunk_ids = list(dict.fromkeys(chunk_ids))[:related_chunk_number * 2]

    raw_chunks = await text_chunks_db.get_by_ids(chunk_ids)
    valid_chunks: list[dict] = []
    for chunk in raw_chunks:
        if chunk and chunk.get("content"):
            valid_chunks.append(chunk)

    # Defensive file_filter: an entity merged across files holds chunk IDs
    # from each contributing file; if the caller restricted retrieval to a
    # single file, drop any chunks whose stored file_path doesn't match.
    if query_param.file_filter:
        valid_chunks = [
            c for c in valid_chunks
            if c.get("file_path") == query_param.file_filter
        ]

    # Token-aware truncation
    truncated = truncate_list_by_token_size(
        valid_chunks,
        key=lambda c: c.get("content", ""),
        max_token_size=max_tokens,
        tokenizer=tokenizer,
    )
    return truncated


def _build_kg_context_str(
    entity_nodes: list[dict],
    relations: list[dict],
    text_chunks: list[dict],
    max_entity_tokens: int,
    max_relation_tokens: int,
    max_total_tokens: int,
    tokenizer: Tokenizer | None,
) -> str:
    """Assemble the KG context string to inject into the LLM prompt."""
    entities_str = json.dumps(entity_nodes[:max_entity_tokens // 4], ensure_ascii=False, indent=2)
    relations_str = json.dumps(relations[:max_relation_tokens // 4], ensure_ascii=False, indent=2)

    chunks_for_context: list[dict] = []
    seen_content: set[str] = set()
    for chunk in text_chunks:
        content = chunk.get("content", "")
        if content and content not in seen_content:
            chunks_for_context.append({
                "content": content,
                "file_path": chunk.get("file_path", "unknown"),
            })
            seen_content.add(content)

    chunks_str = json.dumps(chunks_for_context, ensure_ascii=False, indent=2)

    # Build reference list
    file_paths: list[str] = []
    seen_fps: set[str] = set()
    for chunk in chunks_for_context:
        fp = chunk.get("file_path", "")
        if fp and fp not in seen_fps:
            file_paths.append(fp)
            seen_fps.add(fp)
    reference_list_str = "\n".join(
        f"[{i + 1}] {fp}" for i, fp in enumerate(file_paths)
    )

    return PROMPTS["kg_query_context"].format(
        entities_str=entities_str,
        relations_str=relations_str,
        text_chunks_str=chunks_str,
        reference_list_str=reference_list_str or "N/A",
    )


# ---------------------------------------------------------------------------
# KG query (mix mode — recommended default)
# ---------------------------------------------------------------------------

async def kg_query(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict,
    hashing_kv: BaseKVStorage | None = None,
    chunks_vdb: BaseVectorStorage | None = None,
    entity_chunks_db: BaseKVStorage | None = None,
) -> QueryResult | None:
    """
    Execute a KG-based query (mix/local/global/hybrid modes).

    The "mix" mode (default) uses both low-level (entity) and high-level
    (relation) keywords plus vector chunks for comprehensive retrieval.
    """
    if not query:
        return QueryResult(content=PROMPTS["fail_response"])

    use_llm_func = global_config["llm_model_func"]

    # Extract keywords
    hl_keywords, ll_keywords = await extract_keywords_only(
        query, query_param, global_config, hashing_kv
    )
    ll_str = ", ".join(ll_keywords) if ll_keywords else ""
    hl_str = ", ".join(hl_keywords) if hl_keywords else ""

    logger.debug(f"[kg_query] HL: {hl_str} | LL: {ll_str}")

    # Fall back to original query if nothing extracted
    if not ll_keywords and not hl_keywords:
        if len(query) < 50:
            ll_keywords = [query]
            ll_str = query
        else:
            return QueryResult(content=PROMPTS["fail_response"])

    mode = query_param.mode  # "local", "global", "hybrid", "mix"
    max_entity_tokens = query_param.max_entity_tokens or DEFAULT_MAX_ENTITY_TOKENS
    max_relation_tokens = query_param.max_relation_tokens or DEFAULT_MAX_RELATION_TOKENS
    max_total_tokens = query_param.max_total_tokens or DEFAULT_MAX_TOTAL_TOKENS
    tokenizer: Tokenizer | None = global_config.get("tokenizer")
    chunk_budget = max(max_total_tokens - max_entity_tokens - max_relation_tokens, 2000)

    entity_nodes: list[dict] = []
    relations: list[dict] = []
    chunk_ids: list[str] = []

    # Local retrieval: LL keywords → entities + BFS graph expansion
    if mode in ("local", "hybrid", "mix") and ll_str:
        ents, e_chunks = await _get_entity_context(
            ll_str, entities_vdb, knowledge_graph_inst, text_chunks_db,
            query_param, global_config,
            entity_chunks_db=entity_chunks_db,
        )
        entity_nodes.extend(ents)
        chunk_ids.extend(c for c in e_chunks if c not in chunk_ids)

    # Global retrieval: HL keywords → relations
    if mode in ("global", "hybrid", "mix") and hl_str:
        rels, r_chunks = await _get_relation_context(
            hl_str, relationships_vdb, knowledge_graph_inst, text_chunks_db, query_param, global_config
        )
        relations.extend(rels)
        chunk_ids.extend(c for c in r_chunks if c not in chunk_ids)

    # Vector chunk retrieval (mix mode)
    vector_chunks: list[dict] = []
    if mode == "mix" and chunks_vdb is not None:
        search_top_k = query_param.chunk_top_k or query_param.top_k
        v_results = await chunks_vdb.query(
            query, top_k=search_top_k, file_filter=query_param.file_filter,
        )
        for v in v_results:
            if v.get("content"):
                vector_chunks.append({
                    "content": v["content"],
                    "file_path": v.get("file_path", "unknown"),
                })

    # No KG context found
    if not entity_nodes and not relations and not vector_chunks:
        logger.info("[kg_query] No context found; returning no-result.")
        return None

    # Fetch text chunks from KG source IDs
    text_chunks = await _fetch_text_chunks(
        chunk_ids, text_chunks_db, query_param, global_config, chunk_budget
    )

    # Merge vector chunks with KG text chunks (deduplicate by content)
    seen_content: set[str] = set(c.get("content", "") for c in text_chunks)
    for vc in vector_chunks:
        if vc.get("content") and vc["content"] not in seen_content:
            text_chunks.append(vc)
            seen_content.add(vc["content"])

    context_str = _build_kg_context_str(
        entity_nodes,
        relations,
        text_chunks,
        max_entity_tokens,
        max_relation_tokens,
        max_total_tokens,
        tokenizer,
    )

    if query_param.only_need_context:
        return QueryResult(content=context_str)

    user_prompt_extra = f"\n\n{query_param.user_prompt}" if query_param.user_prompt else "n/a"
    response_type = query_param.response_type or "Multiple Paragraphs"

    sys_prompt = PROMPTS["rag_response"].format(
        response_type=response_type,
        user_prompt=user_prompt_extra,
        context_data=context_str,
    )

    if query_param.only_need_prompt:
        return QueryResult(content="\n\n".join([sys_prompt, "---User Query---", query]))

    # Check LLM cache
    args_hash = compute_args_hash(
        query_param.mode, query, response_type, query_param.top_k,
        query_param.max_entity_tokens, query_param.max_relation_tokens,
        query_param.max_total_tokens, hl_str, ll_str,
        query_param.user_prompt or "",
    )
    cached = await handle_cache(hashing_kv, args_hash, query, cache_type="query")
    if cached is not None:
        response, _ = cached
        logger.info("[kg_query] Cache hit.")
    else:
        response = await use_llm_func(
            query,
            system_prompt=sys_prompt,
            history_messages=query_param.conversation_history or [],
        )
        if isinstance(response, str):
            response = remove_think_tags(response)

        if hashing_kv is not None:
            await save_to_cache(
                hashing_kv,
                CacheData(args_hash=args_hash, content=response, prompt=query),
                cache_type="query",
            )

    # Build reference list from retrieved chunks
    ref_fps: list[str] = []
    seen_ref: set[str] = set()
    for chunk in text_chunks + vector_chunks:
        fp = chunk.get("file_path", "")
        if fp and fp not in seen_ref:
            ref_fps.append(fp)
            seen_ref.add(fp)
    references = [{"file_path": fp} for fp in ref_fps]

    return QueryResult(content=response or "", raw_data={"data": {"references": references}})


# ---------------------------------------------------------------------------
# Naive query (pure vector mode)
# ---------------------------------------------------------------------------

async def naive_query(
    query: str,
    chunks_vdb: BaseVectorStorage,
    query_param: QueryParam,
    global_config: dict,
    hashing_kv: BaseKVStorage | None = None,
) -> QueryResult | None:
    """Pure vector retrieval: no KG traversal, no keyword extraction."""
    if not query:
        return QueryResult(content=PROMPTS["fail_response"])

    use_llm_func = global_config["llm_model_func"]
    tokenizer: Tokenizer | None = global_config.get("tokenizer")
    search_top_k = query_param.chunk_top_k or query_param.top_k
    max_total_tokens = query_param.max_total_tokens or DEFAULT_MAX_TOTAL_TOKENS

    results = await chunks_vdb.query(
        query, top_k=search_top_k, file_filter=query_param.file_filter,
    )
    if not results:
        logger.info("[naive_query] No chunks found.")
        return None

    valid_chunks = [r for r in results if r.get("content")]
    if not valid_chunks:
        return None

    # Token-aware truncation
    chunk_budget = max_total_tokens - 500  # leave room for prompt + query
    truncated = truncate_list_by_token_size(
        valid_chunks,
        key=lambda c: c.get("content", ""),
        max_token_size=chunk_budget,
        tokenizer=tokenizer,
    )

    # Build chunks context
    chunks_context = [
        {"content": c["content"], "file_path": c.get("file_path", "unknown")}
        for c in truncated
    ]

    # Build reference list
    file_paths: list[str] = []
    seen_fps: set[str] = set()
    for c in chunks_context:
        fp = c.get("file_path", "")
        if fp and fp not in seen_fps:
            file_paths.append(fp)
            seen_fps.add(fp)
    reference_list_str = "\n".join(f"[{i+1}] {fp}" for i, fp in enumerate(file_paths))

    context_str = PROMPTS["naive_query_context"].format(
        text_chunks_str=json.dumps(chunks_context, ensure_ascii=False, indent=2),
        reference_list_str=reference_list_str or "N/A",
    )

    if query_param.only_need_context:
        return QueryResult(content=context_str)

    user_prompt_extra = f"\n\n{query_param.user_prompt}" if query_param.user_prompt else "n/a"
    response_type = query_param.response_type or "Multiple Paragraphs"

    sys_prompt = PROMPTS["naive_rag_response"].format(
        response_type=response_type,
        user_prompt=user_prompt_extra,
        content_data=context_str,
    )

    if query_param.only_need_prompt:
        return QueryResult(content="\n\n".join([sys_prompt, "---User Query---", query]))

    args_hash = compute_args_hash(
        query_param.mode, query, response_type, query_param.top_k,
        query_param.chunk_top_k, query_param.max_total_tokens,
        query_param.user_prompt or "",
    )
    cached = await handle_cache(hashing_kv, args_hash, query, cache_type="query")
    if cached is not None:
        response, _ = cached
        logger.info("[naive_query] Cache hit.")
    else:
        response = await use_llm_func(
            query,
            system_prompt=sys_prompt,
            history_messages=query_param.conversation_history or [],
        )
        if isinstance(response, str):
            response = remove_think_tags(response)

        if hashing_kv is not None:
            await save_to_cache(
                hashing_kv,
                CacheData(args_hash=args_hash, content=response, prompt=query),
                cache_type="query",
            )

    # Build deduplicated reference list from retrieved chunks
    seen_nq: set[str] = set()
    deduped_refs: list[dict] = []
    for c in chunks_context:
        fp = c.get("file_path", "")
        if fp and fp not in seen_nq:
            deduped_refs.append({"file_path": fp})
            seen_nq.add(fp)

    return QueryResult(content=response or "", raw_data={"data": {"references": deduped_refs}})
