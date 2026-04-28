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

Frontend runs on `:3000`, backend on `:8000`, Postgres on `:5433` (host) / `:5432` (container), Neo4j on `:7474` (browser) / `:7687` (bolt), ChromaDB on `:8001` (host) / `:8000` (container).

### Docker (full stack)
```bash
docker compose up                      # builds + starts db, neo4j, chroma, backend, frontend
docker compose up -d db neo4j chroma   # just the data services — useful when running backend locally via start_dev.bat
```

ChromaDB runs as its own container (`chromadb/chroma:0.4.24`, host port **8001** → container 8000) and the backend talks to it via HTTP (see Gotchas). Postgres / Neo4j / Chroma each have a named volume (`postgres_data`, `neo4j_data`, `chroma_data`) so data survives restarts. Use `.env.docker` (copy from `.env.docker.example`); for local-venv dev, the backend reads `CHROMA_HOST` (default `localhost`) and `CHROMA_PORT` (default `8001`) from `.env`.

### Database migrations
```bash
cd backend
alembic upgrade head                               # apply all
alembic revision --autogenerate -m "description"   # new migration
alembic downgrade -1                               # rollback one
```

Note: `app.database.init_db.init_db()` also calls `Base.metadata.create_all()` on startup — this is a safety net, but Alembic is the source of truth for schema. RAG-layer tables (`rag_kv_store`, `rag_doc_status`) live only in the Alembic migration `b1c2d3e4f5a6_add_rag_tables.py`.

**Fallback**: `scripts/reset_all_dbs.py` drops + recreates the `public` schema via asyncpg, runs `Base.metadata.create_all()`, and applies the RAG migration DDL inline — bypassing Alembic entirely. Use this when (a) you need a guaranteed clean slate for E2E runs, or (b) alembic can't load psycopg's `pq` DLL (see Smart App Control gotcha). Also wipes Neo4j and drops Chroma collections matching the connected instance.

### E2E smoke test
```bash
# Full flow: signup → login → classroom → folder → upload → poll → ask, with per-stage timings
.venv\Scripts\python.exe scripts\e2e_driver.py --file "..\Chapter1_HRM_With_Cartoons_Icons_and_Video.pptx" --out logs\e2e_report.json

# Infra-only checks (Postgres / Neo4j / Chroma / OpenAI reachability)
.venv\Scripts\python.exe scripts\smoke_test.py
```
`scripts/monitor_session.py` and `scripts/watch_kg.py` give live KG + Postgres telemetry during ingestion; `scripts/backend_log_tail.py` greps the backend log for errors in real time.

### RAG benchmarking
```bash
cd backend

# Step 1 — ask all questions in ground_truth.json through the live chat path (naive mode)
.venv\Scripts\python.exe app/evaluation/run_benchmark_lightrag.py `
    --classroom-id <id> --file-url "<r2_url>" [--resume]

# Step 2 — compute ROUGE-L F1 / BERTScore F1 / Semantic Similarity / latency / cost
.venv\Scripts\python.exe app/evaluation/compute_metrics.py `
    --input app/evaluation/results/lightrag_raw.json --system naive

# Step 3 — side-by-side comparison vs old LangChain system
.venv\Scripts\python.exe app/evaluation/compare.py `
    --new app/evaluation/results/naive_metrics.json --old <old_metrics.json>
```
Ground truth lives in `backend/app/evaluation/ground_truth.json`. The benchmark uses the same `QueryParam(mode="naive", file_filter=..., chunk_top_k=20)` shape as `routes/chat.py`, so its numbers reflect production chat behavior. `preflight.py` verifies Postgres / Neo4j / Chroma / OpenAI reachability and that the file is `COMPLETED` before burning tokens. Results save incrementally to `app/evaluation/results/` — `--resume` skips already-completed questions if a run is interrupted.

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
3. **Ask** (`POST /chat/files/{file_id}/ask`, `routes/chat.py`) — loads last 10 chat turns, resolves the classroom engine, calls `engine.aquery(question, QueryParam(mode="naive", chunk_top_k=20, file_filter=file.file_url, ...))`, persists both the user message and assistant reply into `chat_messages`, returns answer + source file paths. Chat is scoped to a single file via `file_filter` and uses pure ChromaDB vector search on the `chunks` collection — **no Neo4j hop at query time**. The KG is preserved for quiz generation and future mind-map features (which still use `mode="mix"` internally).

The `_get_file_and_classroom()` helper in `routes/chat.py` is the canonical access-control pattern: every file-scoped route resolves file → folder → classroom and checks `current_user in classroom.members`.

### LightRAG layer (`backend/app/rag/`)

This is a from-scratch port/implementation of LightRAG's graph-based RAG, not an imported library. The key abstraction is **workspace isolation**: each classroom gets `workspace="classroom_{id}"` and that string is part of every storage key (Postgres row, Chroma collection, Neo4j label). Engines never cross classrooms.

- `engine.py` — `LightRAGEngine` dataclass owns all storage objects and exposes `ainsert`, `aquery`, `adelete_file`, `finalize`. Created per-classroom, cached in `services/classroom_rag.py` as a module-level singleton `ClassroomRAGService`, initialized lazily on first access with a double-checked `asyncio.Lock`.
- `base.py` — abstract storage interfaces (`BaseKVStorage`, `BaseVectorStorage`, `BaseGraphStorage`, `DocStatusStorage`) and `QueryParam` (supports modes: `local`, `global`, `hybrid`, `naive`, `mix`, `bypass`). **Mode policy**: chat (`routes/chat.py`) uses `naive`; quiz generation and other KG-dependent callers use `mix`. `QueryParam` also has `traversal_hops=2` and `max_graph_neighbors=30` for multi-hop BFS control (mix mode only — naive ignores them). `file_filter` scopes retrieval to a single document (used by chat and quiz).
- `namespace.py` — string constants identifying which logical store a namespace belongs to (7 KV namespaces, 3 vector namespaces, 1 graph, 1 doc-status).
- `operate.py` — pure functions: `chunking_by_token_size`, `extract_entities`, `merge_nodes_and_edges`, `kg_query`, `naive_query`. `kg_query` uses **multi-hop graph traversal**: after ChromaDB finds seed entities by vector similarity, `_expand_graph_neighbors()` calls `get_neighbors_with_scores()` BFS on Neo4j to discover related entities up to `traversal_hops` hops away, scoring by product(edge_weights)/hop_count. Chunk IDs for both seeds and neighbors are pulled from the `entity_chunks` KV namespace (complete list) rather than the node's `source_id` field (truncated at 50). `DEFAULT_CHUNK_TOKEN_SIZE = 800` (not 1200).
- `storage/` — concrete backends:
  - `postgres_kv.py` — shared JSONB KV store (`rag_kv_store` table) for 7 namespaces (`full_docs`, `text_chunks`, `llm_response_cache`, `full_entities`, `full_relations`, `entity_chunks`, `relation_chunks`). Uses **asyncpg** (separate connection pool from SQLAlchemy's psycopg — see env vars `DATABASE_URL` vs `ASYNCPG_DATABASE_URL`).
  - `chroma_vector.py` — ChromaDB collections for `entities`, `relationships`, `chunks`, via **`chromadb.HttpClient`** against the standalone `chroma` container (NOT `PersistentClient` — see Smart App Control gotcha). Telemetry forced off via `Settings(anonymized_telemetry=False)`. Entity `content` field stores `"entity_name\ndescription"` — seed entity descriptions are parsed from this at query time (no Neo4j round-trip needed for seeds).
  - `neo4j_graph.py` — knowledge graph (chunk ↔ entity ↔ relation). `get_neighbors_with_scores()` performs single-query BFS with weighted path scoring via Cypher `MATCH (seed)-[r*1..N]-(neighbor)`. Note: Neo4j 5.x requires **`size(r)`**, not `length(r)`, to count relationships in a variable-length path — `length()` expects a `Path`, not `List<Relationship>`, and the server raises a type-mismatch at query time.
  - `postgres_doc_status.py` — per-document pipeline status (`rag_doc_status` table).

Shutdown is handled in `app/main.py`'s `lifespan` — it calls `classroom_rag_service.finalize_all()` and `close_pool()` to flush writes and close the asyncpg pool. Add any new per-engine teardown to `LightRAGEngine.finalize()`, not ad-hoc cleanup in routes.

### Multimodal pipeline (`backend/app/multimodal/`)

Dual-track ingestion: Docling parses bytes once, output is split into text vs. modal items (images, tables, equations), each runs concurrently.

- `parser.py` — `parse_bytes()` + `separate_content()` wrap Docling. Uses `python-pptx` natively (no LibreOffice). Supports `.pdf`, `.docx`, `.pptx`, `.txt`. Has two Windows-specific workarounds installed at module top (see SAC gotcha below) and a `_extract_pptx_media()` helper that pulls raster images directly from the PPTX zip because Docling's PPTX backend yields zero `PictureItem`s.
- `processors.py` — `ImageModalProcessor`, `TableModalProcessor`, `EquationModalProcessor`. Images/tables go through the vision model (`gpt-4o` via `openai_vision_func`); equations go through the LLM.
- `pipeline.py` — `MultimodalPipeline.process_document()` owns a temp dir that must outlive modal processing (Docling writes image files to disk that the vision processor later base64-encodes; cleaning up too early was a real past bug — see comments at `pipeline.py:112`). Text insert uses `split_by_character="\n\n"` to honor slide/paragraph boundaries before falling back to token splitting. Modal concurrency is capped at `asyncio.Semaphore(6)`.

The file's canonical citation key in the knowledge base is `file.file_url` (the R2 URL), not the filename or DB id — this is what appears in RAG source references.

### Quiz system (`backend/app/services/quiz_service.py`, `routes/quiz.py`)

Four endpoints under `/quiz/`:
- `POST /quiz/files/{file_id}/generate` (202) — creates a `Quiz` row, dispatches `generate_quiz_task` as a `BackgroundTask`.
- `GET /quiz/{quiz_id}` — polls status; returns questions once `READY`, includes attempt if already submitted.
- `POST /quiz/{quiz_id}/submit` — grades answers, persists `QuizAttempt`.
- `GET /quiz/files/{file_id}/history` — all past attempts for a file.

**Difficulty inference** (`infer_difficulty`): fetches last 20 chat turns + last 3 `QuizAttempt` rows, calls the LLM with heuristics (score ≥ 0.8 → step up; < 0.5 → step down; confusion language in chat → step down). Falls back to `MEDIUM` if inference fails.

**Background task** (`generate_quiz_task`):
1. Fetches recent chat history via `get_conversation_history_for_rag`; calls `_extract_chat_topics` to pull up to 8 recent user questions as topic hints (deduped, truncated to 200 chars each). Falls back silently to empty list on error.
2. `build_quiz_context` seeds the RAG query with those topic hints if present (mode `mix`, `only_need_context=True`, `file_filter=file_url`, difficulty-scaled params). Without chat history, uses the generic seed.
3. `generate_questions` → `_call_generate_llm`: produces a 70 % MCQ / 30 % T/F mix grounded strictly in retrieved context. When topic hints are present, the system prompt adds a `FOCUS AREAS` block directing the LLM to weight 60–70 % of questions toward those topics. One retry at `temperature=0` fills any missing questions.
4. Persists `questions` (JSONB), `generation_meta` (includes `chat_topics_count` for observability), sets status `READY`.

**`generation_meta`** stored on each Quiz: `context_chars`, `chat_topics_count`, `traversal_hops`, `max_graph_neighbors`, `top_k`, `chunk_top_k`, `elapsed_s`, `model`.

**Grading** (`grade_attempt`): pure function, no I/O — takes stored questions + submitted answers, coerces types, returns `score`, `correct_count`, `total_count`, and per-question review. Unanswered questions (sent as `null`) are always marked wrong — `null` is a valid value in `SubmitAnswer.answer` for this purpose.

### Relational models (`backend/app/models/`)

`user`, `classroom` (many-to-many `classroom_members`), `folder`, `file` (with `ProcessingStatus` enum: `PENDING`/`PROCESSING`/`COMPLETED`/`FAILED`), `chat_message` (with `MessageRole` enum), `quiz` (`Quiz` + `QuizAttempt` — `QuizStatus`: `pending`/`generating`/`ready`/`failed`/`submitted`; `QuizDifficulty`: `easy`/`medium`/`hard`). The `topic` model has been removed; commented-out legacy code still references it in several files — don't reintroduce it.

Cascade deletes: deleting a classroom cascades to folders → files → chat messages. Deleting a file also requires calling `engine.adelete_file(file.file_url)` to remove KB data — see `routes/file.py` delete endpoint. `Quiz` has a one-to-one `QuizAttempt` with `cascade="all, delete-orphan"`.

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
- **Windows Smart App Control (SAC)**: on dev machines with SAC enabled, Windows blocks unsigned native `.pyd`/DLL loads. Three specific modules were affected and have workarounds in place:
  1. `chromadb`'s `hnswlib.pyd` — fixed by running chroma in Docker and using `HttpClient` instead of `PersistentClient`.
  2. `psycopg`'s `pq` DLL (used by alembic) — fixed by `scripts/reset_all_dbs.py`, which uses asyncpg only.
  3. `docling_parse.pdf_parsers.pyd` and transformers' `StoppingCriteria` lazy cascade — `backend/app/multimodal/parser.py` installs a `sys.modules` stub for the first and force-populates the transformers module dict for the second. Both are inert on non-SAC machines. PPTX/DOCX/TXT still work; only PDF upload raises a clear error when the stub is active.
  Symptom to recognize: `ImportError: DLL load failed while importing <module>: A dynamic link library (DLL) initialization routine failed.` with `SmartAppControlState: On` in `Get-MpComputerStatus`.
- **ChromaDB telemetry noise**: chromadb 0.4.24 × posthog 7.x have an ABI mismatch (`capture() takes 1 positional argument but 3 were given`). `Settings(anonymized_telemetry=False)` silences post-init events, and `_configure_logging()` in `app/main.py` sets `chromadb.telemetry.product.posthog` to CRITICAL to suppress the one constructor-time `ClientStartEvent` that fires before Settings is read.
- **Async SQLAlchemy — always eager-load relationships**: `db.get(Model, id)` never loads ORM relationships. Accessing a relationship attribute afterward (e.g. `quiz.attempt`) inside an async session triggers a synchronous lazy-load and crashes with `MissingGreenlet`. **Rule**: any route that reads a relationship must use `select(Model).options(selectinload(Model.rel)).where(...)` at query time. `db.get()` is only safe when you need the row itself and will not touch any relationship attribute.
- **LLM model env vars**: `OPENAI_MODEL` selects the text LLM (defaults to `gpt-4o-mini`) used by `openai_llm_func` in `rag/utils.py` — this drives quiz difficulty inference and question generation. `VISION_MODEL` selects the vision LLM (defaults to `gpt-4o`) used by `openai_vision_func` for multimodal ingestion. Neither appears in `.env.docker.example` but both are read at call time.
- **Stale `"mode": "mix"` strings in `routes/chat.py`**: the live ask endpoint uses `mode="naive"`, but the `chat_messages.metadata` JSON written at line 106 still records `"mode": "mix"`, and the `/chat/files/{id}/stats` response at line 173 still reports `"retrieval_mode": "mix"`. These are cosmetic labels not used for routing — left intentionally untouched during the mix→naive switch to keep the change set minimal. Update them in a separate small commit if the values matter for downstream analytics.
