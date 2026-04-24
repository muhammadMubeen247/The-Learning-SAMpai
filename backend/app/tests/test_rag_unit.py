"""
RAG pipeline unit tests — no external services required.
Tests chunking, entity parsing, source ID utilities, and JSON helpers.

Run: pytest app/tests/test_rag_unit.py -v
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

class TestChunking:
    def _tokenizer(self):
        from app.rag.utils import TiktokenTokenizer
        return TiktokenTokenizer()

    def test_basic_chunking(self):
        from app.rag.operate import chunking_by_token_size
        tok = self._tokenizer()
        text = " ".join(["word"] * 2000)
        chunks = chunking_by_token_size(tok, text, chunk_token_size=800, chunk_overlap_token_size=100)
        assert len(chunks) >= 2
        for c in chunks:
            assert "content" in c
            assert "tokens" in c
            assert c["tokens"] <= 850  # small buffer over target

    def test_empty_text_returns_empty(self):
        from app.rag.operate import chunking_by_token_size
        tok = self._tokenizer()
        chunks = chunking_by_token_size(tok, "", chunk_token_size=800, chunk_overlap_token_size=100)
        assert chunks == []

    def test_short_text_is_single_chunk(self):
        from app.rag.operate import chunking_by_token_size
        tok = self._tokenizer()
        chunks = chunking_by_token_size(tok, "Hello world.", chunk_token_size=800, chunk_overlap_token_size=100)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0]["content"]

    def test_chunk_order_indices_are_sequential(self):
        from app.rag.operate import chunking_by_token_size
        tok = self._tokenizer()
        text = " ".join(["token"] * 3000)
        chunks = chunking_by_token_size(tok, text, chunk_token_size=800, chunk_overlap_token_size=100)
        indices = [c["chunk_order_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_overlap_creates_shared_content(self):
        from app.rag.operate import chunking_by_token_size
        tok = self._tokenizer()
        # 1600 words → ~2 chunks with overlap
        words = [f"uniqueword{i}" for i in range(1600)]
        text = " ".join(words)
        chunks = chunking_by_token_size(tok, text, chunk_token_size=800, chunk_overlap_token_size=100)
        if len(chunks) >= 2:
            # Some words from end of chunk 0 should appear in start of chunk 1
            end_words = set(chunks[0]["content"].split()[-50:])
            start_words = set(chunks[1]["content"].split()[:50])
            assert len(end_words & start_words) > 0, "Overlap expected between consecutive chunks"


# ---------------------------------------------------------------------------
# Entity / relation tuple parsing
# ---------------------------------------------------------------------------

class TestEntityParsing:
    """
    _handle_single_entity_extraction / _handle_single_relationship_extraction
    receive a pre-split list[str] (split on the tuple delimiter), plus
    a chunk_key and timestamp.  The first element must contain the word
    "entity" or "relation" as a type marker from the LLM output.
    """

    CHUNK_KEY = "chunk-test-001"
    TS = 0

    def _parse_entity(self, fields: list[str]):
        from app.rag.operate import _handle_single_entity_extraction
        return _handle_single_entity_extraction(fields, self.CHUNK_KEY, self.TS)

    def _parse_relation(self, fields: list[str]):
        from app.rag.operate import _handle_single_relationship_extraction
        return _handle_single_relationship_extraction(fields, self.CHUNK_KEY, self.TS)

    def test_valid_entity_tuple(self):
        # Format: ["entity", name, type, description]
        fields = ['"entity"', '"Newton"', '"person"', '"English physicist and mathematician"']
        result = self._parse_entity(fields)
        assert result is not None
        assert result["entity_name"] == "Newton"
        assert result["entity_type"] == "person"
        assert "physicist" in result["description"]

    def test_entity_missing_fields_returns_none(self):
        result = self._parse_entity(['"entity"', '"Newton"'])  # too few fields
        assert result is None

    def test_entity_without_entity_marker_returns_none(self):
        # First field must contain "entity"
        fields = ['"relationship"', '"Newton"', '"person"', '"A physicist"']
        result = self._parse_entity(fields)
        assert result is None

    def test_valid_relation_tuple(self):
        # Format: ["relation", src, tgt, keywords, description]  weight is optional last field
        fields = [
            '"relation"',
            '"Newton"',
            '"Gravity"',
            '"discovered"',
            '"Newton discovered and described the law of universal gravitation"',
        ]
        result = self._parse_relation(fields)
        assert result is not None
        assert result["src_id"] == "Newton"
        assert result["tgt_id"] == "Gravity"
        assert "discovered" in result["keywords"]

    def test_relation_missing_fields_returns_none(self):
        result = self._parse_relation(['"relation"', '"Newton"'])
        assert result is None


# ---------------------------------------------------------------------------
# Source ID utilities
# ---------------------------------------------------------------------------

class TestSourceIdUtils:
    def test_merge_deduplicates(self):
        from app.rag.utils import merge_source_ids
        merged = merge_source_ids(["a", "b"], ["b", "c"])
        assert sorted(merged) == ["a", "b", "c"]

    def test_merge_preserves_order(self):
        from app.rag.utils import merge_source_ids
        merged = merge_source_ids(["x", "y"], ["z"])
        assert merged == ["x", "y", "z"]

    def test_apply_limit_keep(self):
        from app.rag.utils import apply_source_ids_limit
        ids = ["a", "b", "c", "d", "e"]
        result = apply_source_ids_limit(ids, max_ids=3, method="KEEP")
        assert result == ["a", "b", "c"]

    def test_apply_limit_within_budget(self):
        from app.rag.utils import apply_source_ids_limit
        ids = ["a", "b"]
        result = apply_source_ids_limit(ids, max_ids=5, method="keep_first")
        assert result == ["a", "b"]

    def test_source_ids_to_str(self):
        from app.rag.utils import source_ids_to_str
        from app.rag.constants import GRAPH_FIELD_SEP
        result = source_ids_to_str(["chunk-1", "chunk-2"])
        assert result == f"chunk-1{GRAPH_FIELD_SEP}chunk-2"

    def test_source_ids_to_str_empty(self):
        from app.rag.utils import source_ids_to_str
        assert source_ids_to_str([]) == ""


# ---------------------------------------------------------------------------
# Hashing and ID generation
# ---------------------------------------------------------------------------

class TestHashing:
    def test_compute_mdhash_id_deterministic(self):
        from app.rag.utils import compute_mdhash_id
        id1 = compute_mdhash_id("hello world", prefix="chunk-")
        id2 = compute_mdhash_id("hello world", prefix="chunk-")
        assert id1 == id2

    def test_compute_mdhash_id_differs_by_prefix(self):
        from app.rag.utils import compute_mdhash_id
        id1 = compute_mdhash_id("hello", prefix="chunk-")
        id2 = compute_mdhash_id("hello", prefix="ent-")
        assert id1 != id2

    def test_compute_mdhash_id_differs_by_content(self):
        from app.rag.utils import compute_mdhash_id
        id1 = compute_mdhash_id("hello", prefix="x-")
        id2 = compute_mdhash_id("world", prefix="x-")
        assert id1 != id2


# ---------------------------------------------------------------------------
# JSON parsing helpers (robust_json_parse)
# ---------------------------------------------------------------------------

class TestRobustJsonParse:
    def test_clean_json(self):
        from app.multimodal.processors import robust_json_parse
        result = robust_json_parse('{"detailed_description": "test", "entity_info": {}}')
        assert result["detailed_description"] == "test"

    def test_fenced_code_block(self):
        from app.multimodal.processors import robust_json_parse
        raw = '```json\n{"detailed_description": "hello", "entity_info": {}}\n```'
        result = robust_json_parse(raw)
        assert result["detailed_description"] == "hello"

    def test_trailing_comma_recovery(self):
        from app.multimodal.processors import robust_json_parse
        raw = '{"detailed_description": "x", "entity_info": {},}'
        result = robust_json_parse(raw)
        assert result["detailed_description"] == "x"

    def test_regex_fallback(self):
        from app.multimodal.processors import robust_json_parse
        raw = 'Some text "detailed_description": "extracted", "entity_name": "Thing", "entity_type": "Object", "summary": "A thing" more text'
        result = robust_json_parse(raw)
        # At minimum should not raise and return a dict
        assert isinstance(result, dict)

    def test_think_tags_stripped(self):
        from app.multimodal.processors import robust_json_parse
        raw = '<think>internal reasoning</think>{"detailed_description": "clean", "entity_info": {}}'
        result = robust_json_parse(raw)
        assert result["detailed_description"] == "clean"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class TestTiktokenTokenizer:
    def test_encode_returns_list(self):
        from app.rag.utils import TiktokenTokenizer
        tok = TiktokenTokenizer()
        tokens = tok.encode("Hello world")
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    def test_encode_decode_roundtrip(self):
        from app.rag.utils import TiktokenTokenizer
        tok = TiktokenTokenizer()
        text = "The quick brown fox"
        tokens = tok.encode(text)
        decoded = tok.decode(tokens)
        assert text in decoded

    def test_token_count_scales_with_length(self):
        from app.rag.utils import TiktokenTokenizer
        tok = TiktokenTokenizer()
        short = len(tok.encode("Hi"))
        long = len(tok.encode("Hi " * 100))
        assert long > short
