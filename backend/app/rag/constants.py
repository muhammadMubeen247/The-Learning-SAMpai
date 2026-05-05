"""
Centralized configuration constants for the FYP RAG engine.
Ported from LightRAG with educational-domain overrides.
"""

# Extraction settings
DEFAULT_SUMMARY_LANGUAGE = "English"
DEFAULT_MAX_GLEANING = 0          # was 1 — saves ~33% of LLM calls; first-pass extraction is sufficient for academic content
DEFAULT_ENTITY_NAME_MAX_LENGTH = 256

# Description merge thresholds
DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE = 30  # was 15 — string concat used below 30; saves merge LLM calls with no functional quality loss
DEFAULT_SUMMARY_MAX_TOKENS = 1200
DEFAULT_SUMMARY_LENGTH_RECOMMENDED = 600
DEFAULT_SUMMARY_CONTEXT_SIZE = 12000
DEFAULT_MAX_EXTRACT_INPUT_TOKENS = 20480

# Educational entity types (extended from LightRAG defaults)
DEFAULT_ENTITY_TYPES = [
    "Person",
    "Organization",
    "Location",
    "Event",
    "Concept",
    "Method",
    "Content",
    "Data",
    "Artifact",
    # Educational additions
    "Course",
    "Definition",
    "Formula",
    "Theory",
    "Algorithm",
]

# Separator for description, source_id, and relation-key fields
# CRITICAL: Cannot be changed after data has been inserted
GRAPH_FIELD_SEP = "<SEP>"

# Query and retrieval configuration
# Increased from 20/10 — a dense PPTX produces 100+ entities; 20 missed most of them.
DEFAULT_TOP_K = 40
DEFAULT_CHUNK_TOP_K = 20
DEFAULT_MAX_ENTITY_TOKENS = 6000
DEFAULT_MAX_RELATION_TOKENS = 8000
DEFAULT_MAX_TOTAL_TOKENS = 30000
DEFAULT_COSINE_THRESHOLD = 0.2
DEFAULT_RELATED_CHUNK_NUMBER = 5
DEFAULT_KG_CHUNK_PICK_METHOD = "VECTOR"

# Conversation history (deprecated in LightRAG, kept for compatibility)
DEFAULT_HISTORY_TURNS = 0

# Rerank configuration
DEFAULT_MIN_RERANK_SCORE = 0.0

# Source ID limits
DEFAULT_MAX_SOURCE_IDS_PER_ENTITY = 300
DEFAULT_MAX_SOURCE_IDS_PER_RELATION = 300
SOURCE_IDS_LIMIT_METHOD_KEEP = "KEEP"
SOURCE_IDS_LIMIT_METHOD_FIFO = "FIFO"
DEFAULT_SOURCE_IDS_LIMIT_METHOD = SOURCE_IDS_LIMIT_METHOD_FIFO
VALID_SOURCE_IDS_LIMIT_METHODS = {SOURCE_IDS_LIMIT_METHOD_KEEP, SOURCE_IDS_LIMIT_METHOD_FIFO}

# File path display limits
DEFAULT_MAX_FILE_PATHS = 100
DEFAULT_MAX_FILE_PATH_LENGTH = 32768
DEFAULT_FILE_PATH_MORE_PLACEHOLDER = "truncated"

# LLM defaults
DEFAULT_TEMPERATURE = 0.2  # Lower than LightRAG default for more deterministic educational answers

# Async concurrency limits
DEFAULT_MAX_ASYNC = 8             # was 4 — safe for OpenAI standard tier; 2× faster extraction queuing
DEFAULT_MAX_PARALLEL_INSERT = 2

# Tiered concurrency for foreground (interactive) vs background (Phase 2 ingestion) paths.
# Phase 2 uses the lower value so live chat/flashcard calls always have headroom in the
# shared OpenAI rate-limit bucket.
FOREGROUND_MAX_ASYNC = 8
BACKGROUND_MAX_ASYNC = 4

# Minimum chunk token count to warrant an LLM entity-extraction call.
# Chunks below this threshold (lone slide titles, bullet headings) are still stored
# in chunks_vdb and text_chunks KV for vector retrieval — only the LLM call is skipped.
MIN_ENTITY_EXTRACT_TOKENS = 30

# Embedding configuration
DEFAULT_EMBEDDING_FUNC_MAX_ASYNC = 16  # was 8 — embeddings are cheap/fast, higher concurrency is fine
DEFAULT_EMBEDDING_BATCH_NUM = 50

# Chunking — tuned for academic PDFs (smaller than LightRAG's 1200 default)
DEFAULT_CHUNK_TOKEN_SIZE = 800
DEFAULT_CHUNK_OVERLAP_TOKEN_SIZE = 100

# Timeouts
DEFAULT_LLM_TIMEOUT = 180
DEFAULT_EMBEDDING_TIMEOUT = 30
DEFAULT_TIMEOUT = 300

# Graph limits
DEFAULT_MAX_GRAPH_NODES = 1000
