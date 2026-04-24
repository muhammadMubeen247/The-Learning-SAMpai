# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Note on README.md

The root `README.md` is outdated. It describes a React + Vite frontend and an older topic-extraction pipeline. The current reality:
- Frontend is **Next.js 15 + React 19** (App Router), not Vite.
- The `topic` model/service/extractor has been removed on the `refactored-backend` branch.
- RAG is now **LightRAG** (graph + vector hybrid) with multimodal ingestion, not plain ChromaDB + OpenAI.

Trust this file and the code over the README until the README is refreshed.

## Common Commands

### Local dev (without Docker)
```bash
# Backend — uses start_dev.bat on Windows (sets env vars + runs uvicorn against the dockerized DB on :5433)
cd backend && start_dev.bat

# Backend — manual
cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && pnpm dev    # or: npm run dev
```

Frontend runs on `:3000`, backend on `:8000`, Postgres on `:5433` (host) / `:5432` (container), Neo4j on `:7474` (browser) / `:7687` (bolt).

### Docker (full stack)
```bash
docker compose up          # builds + starts db, neo4j, backend, frontend
docker compose up db neo4j # just the data services — useful when running backend locally via start_dev.bat
```

The compose setup mounts `backend/chroma_data` as a volume so vector data survives container restarts. Use `.env.docker` (copy from `.env.docker.example`).

### Database migrations
```bash
cd backend
alembic upgrade head                               # apply all
alembic revision --autogenerate -m "description"   # new migration
alembic downgrade -1                               # rollback one
```

Note: `app.database.init_db.init_db()` also calls `Base.metadata.create_all()` on startup — this is a safety net, but Alembic is the source of truth for schema. RAG-layer tables (`rag_kv_store`, `rag_doc_status`) live only in the Alembic migration `b1c2d3e4f5a6_add_rag_tables.py`.

### Tests
```bash
cd backend
pytest                               # all tests (pytest.ini sets asyncio_mode=auto)
pytest -m "not llm"                  # skip tests that make real OpenAI calls
pytest -m "not integration"          # skip tests needing Postgres/Neo4j/Chroma
pytest app/tests/test_rag_unit.py    # single file
pytest app/tests/test_rag_unit.py::test_name -v   # single test
```

Markers defined in `pytest.ini`:
- `llm` — hits real LLM APIs (costs money, skip in CI unless intended)
- `integration` — needs real Postgres + Neo4j + Chroma

`conftest.py` at the repo-root-adjacent `backend/` sets safe env defaults (`OPENAI_API_KEY=sk-test-placeholder`, `SECRET_KEY=test-...`) so unit tests don't fail on module-level imports. It deliberately does NOT set `DATABASE_URL` / `NEO4J_URI`, so integration tests self-skip when services are unavailable.

### Linting
```bash
# Backend (matches CI — syntax/undefined only)
cd backend && flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Frontend
cd frontend && pnpm lint
cd frontend && npx tsc --noEmit      # type check (no `type-check` script defined)
```

## Architecture

### Request flow: upload → process → ask

1. **Upload** (`POST /files/upload/{folder_id}`, `routes/file.py`) — access-checks classroom membership, pushes bytes to Cloudflare R2, creates a `File` row with `PENDING`, schedules `file_processor.process_file` as a FastAPI `BackgroundTask`.
2. **Process** (`services/file_processor.py`) — sets `PROCESSING`, resolves the classroom's `LightRAGEngine` via `classroom_rag_service.get_engine(classroom_id)`, runs `MultimodalPipeline.process_document(...)` with a 600s timeout, generates a 2-3 sentence LLM summary into `File.description`, sets `COMPLETED` (or `FAILED` on error/timeout).
3. **Ask** (`POST /chat/files/{file_id}/ask`, `routes/chat.py`) — loads last 10 chat turns, resolves the classroom engine, calls `engine.aquery(question, QueryParam(mode="mix", ...))`, persists both the user message and assistant reply into `chat_messages`, returns answer + source file paths.

The `_get_file_and_classroom()` helper in `routes/chat.py` is the canonical access-control pattern: every file-scoped route resolves file → folder → classroom and checks `current_user in classroom.members`.

### LightRAG layer (`backend/app/rag/`)

This is a from-scratch port/implementation of LightRAG's graph-based RAG, not an imported library. The key abstraction is **workspace isolation**: each classroom gets `workspace="classroom_{id}"` and that string is part of every storage key (Postgres row, Chroma collection, Neo4j label). Engines never cross classrooms.

- `engine.py` — `LightRAGEngine` dataclass owns all storage objects and exposes `ainsert`, `aquery`, `adelete_file`, `finalize`. Created per-classroom, cached in `services/classroom_rag.py` as a module-level singleton `ClassroomRAGService`, initialized lazily on first access with a double-checked `asyncio.Lock`.
- `base.py` — abstract storage interfaces (`BaseKVStorage`, `BaseVectorStorage`, `BaseGraphStorage`, `DocStatusStorage`) and `QueryParam` (supports modes: `local`, `global`, `hybrid`, `naive`, `mix`, `bypass`; the app always uses `mix`). `QueryParam` also has `traversal_hops=2` and `max_graph_neighbors=30` for multi-hop BFS control.
- `namespace.py` — string constants identifying which logical store a namespace belongs to (7 KV namespaces, 3 vector namespaces, 1 graph, 1 doc-status).
- `operate.py` — pure functions: `chunking_by_token_size`, `extract_entities`, `merge_nodes_and_edges`, `kg_query`, `naive_query`. `kg_query` uses **multi-hop graph traversal**: after ChromaDB finds seed entities by vector similarity, `_expand_graph_neighbors()` calls `get_neighbors_with_scores()` BFS on Neo4j to discover related entities up to `traversal_hops` hops away, scoring by product(edge_weights)/hop_count. Chunk IDs for both seeds and neighbors are pulled from the `entity_chunks` KV namespace (complete list) rather than the node's `source_id` field (truncated at 50). `DEFAULT_CHUNK_TOKEN_SIZE = 800` (not 1200).
- `storage/` — concrete backends:
  - `postgres_kv.py` — shared JSONB KV store (`rag_kv_store` table) for 7 namespaces (`full_docs`, `text_chunks`, `llm_response_cache`, `full_entities`, `full_relations`, `entity_chunks`, `relation_chunks`). Uses **asyncpg** (separate connection pool from SQLAlchemy's psycopg — see env vars `DATABASE_URL` vs `ASYNCPG_DATABASE_URL`).
  - `chroma_vector.py` — ChromaDB collections for `entities`, `relationships`, `chunks`. Entity `content` field stores `"entity_name\ndescription"` — seed entity descriptions are parsed from this at query time (no Neo4j round-trip needed for seeds).
  - `neo4j_graph.py` — knowledge graph (chunk ↔ entity ↔ relation). `get_neighbors_with_scores()` performs single-query BFS with weighted path scoring via Cypher `MATCH (seed)-[r*1..N]-(neighbor)`.
  - `postgres_doc_status.py` — per-document pipeline status (`rag_doc_status` table).

Shutdown is handled in `app/main.py`'s `lifespan` — it calls `classroom_rag_service.finalize_all()` and `close_pool()` to flush writes and close the asyncpg pool. Add any new per-engine teardown to `LightRAGEngine.finalize()`, not ad-hoc cleanup in routes.

### Multimodal pipeline (`backend/app/multimodal/`)

Dual-track ingestion: Docling parses bytes once, output is split into text vs. modal items (images, tables, equations), each runs concurrently.

- `parser.py` — `parse_bytes()` + `separate_content()` wrap Docling. Uses `python-pptx` natively (no LibreOffice). Supports `.pdf`, `.docx`, `.pptx`, `.txt`.
- `processors.py` — `ImageModalProcessor`, `TableModalProcessor`, `EquationModalProcessor`. Images/tables go through the vision model (`gpt-4o` via `openai_vision_func`); equations go through the LLM.
- `pipeline.py` — `MultimodalPipeline.process_document()` owns a temp dir that must outlive modal processing (Docling writes image files to disk that the vision processor later base64-encodes; cleaning up too early was a real past bug — see comments at `pipeline.py:112`). Text insert uses `split_by_character="\n\n"` to honor slide/paragraph boundaries before falling back to token splitting. Modal concurrency is capped at `asyncio.Semaphore(6)`.

The file's canonical citation key in the knowledge base is `file.file_url` (the R2 URL), not the filename or DB id — this is what appears in RAG source references.

### Relational models (`backend/app/models/`)

`user`, `classroom` (many-to-many `classroom_members`), `folder`, `file` (with `ProcessingStatus` enum: `PENDING`/`PROCESSING`/`COMPLETED`/`FAILED`), `chat_message` (with `MessageRole` enum). The `topic` model has been removed; commented-out legacy code still references it in several files — don't reintroduce it.

Cascade deletes: deleting a classroom cascades to folders → files → chat messages. Deleting a file also requires calling `engine.adelete_file(file.file_url)` to remove KB data — see `routes/file.py` delete endpoint.

### Frontend (`frontend/`)

- **Next.js 15 App Router** (`frontend/app/`). Route segments: `login`, `signup`, `dashboard`, `created`, `joined`, `classroom/[id]/...`.
- Auth is **client-side only**. `middleware.ts` logs navigation and lets every request through; token lives in `localStorage` and is attached by `frontend/api/axios.ts`.
- UI primitives via Radix + Tailwind v4 (no `tailwind.config` file — v4 uses `@theme` in CSS). `components/ui/` holds shadcn-style wrappers.
- 3D/motion stack: `@react-three/fiber`, `@react-three/drei`, `@react-three/rapier`, `framer-motion`, `gsap`, `ogl`, `three`, `postprocessing` — primarily used in `components/backgrounds/` and `components/landingpage/`.
- No test harness configured on the frontend (CI's test job skips if `test` script is missing).

### CI (`.github/workflows/`)

Backend CI spins up Postgres 16 + Neo4j 5.18 as services, runs `alembic upgrade head`, then `pytest`. It does NOT pass `OPENAI_API_KEY` by default — `llm`-marked tests will fail there unless the secret is wired up and the test opts in. Integration tests self-skip when services aren't reachable, so they pass locally without Docker too.

## Gotchas

- **NumPy 2.x shim**: `backend/app/main.py` and `backend/conftest.py` both patch `np.float_`, `np.bool_`, `np.int_` *before* any chromadb import. chromadb 0.4.24 and chroma-hnswlib 0.7.3 still reference the removed aliases. If you reorder imports or split `main.py`, preserve this ordering.
- **Logging**: uvicorn's `dictConfig` disables loggers created at import time. `_configure_logging()` runs inside the lifespan startup to re-enable every logger and install a unified format — don't add module-level `logging.basicConfig` calls elsewhere.
- **Two Postgres URLs**: `DATABASE_URL` is for SQLAlchemy (`postgresql+psycopg://`), `ASYNCPG_DATABASE_URL` is for the RAG layer's asyncpg pool (`postgresql://`). They point at the same DB but use different drivers.
- **Dockerized DB port**: host port is `5433`, not `5432`. Local scripts (`start_dev.bat`) already account for this; custom scripts must too.
- **File URLs are citation keys**: don't rename `file.file_url` or change its shape without rewriting stored KB data — it's embedded in graph node properties and vector metadata.
- **Legacy commented code**: `routes/file.py` has a very large block of commented-out old implementation at the bottom. Leave it alone unless deliberately cleaning up — it's been intentionally preserved during the RAG refactor.
- **Package managers on frontend**: both `pnpm-lock.yaml` and `package-lock.json` exist. Pick one per session — the CICD guide uses pnpm.
