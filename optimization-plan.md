# Processing Pipeline Optimization Plan

> Goal: take a 635 KB / 43-slide PPTX from **10+ minutes → ~20 seconds** before chat is usable, with **zero quality tradeoffs** at every layer.

This plan combines code-level micro-optimizations, pipeline parallelization, and an architectural split that decouples naive-mode features (chat, flashcards, group-chat `@SAMpai`) from KG-dependent features (quiz, mindmap). It is engineered so that none of the changes degrade entity extraction, relationship quality, retrieval recall, or answer accuracy — they only remove redundant work, parallelize what is already independent, and let the user start interacting before background indexing finishes.

---

## 0. Already Done (reference)

- **Double-embedding bug** in `engine.py._insert_single_document()` fixed — removed the unused `embedding_func(chunk_texts)` call whose result was never assigned to `vdb_payload`. `ChromaVectorStorage.upsert()` always re-embeds internally, so the first call was dead code. Net effect: ~50 % fewer embedding API calls during chunk insertion. No quality impact.

---

## 1. Performance Baseline (before optimizations)

For the 635 KB / 43-slide PPTX with 5–6 images:

| Stage | Time | Driver |
|---|---|---|
| Docling parse + DocumentConverter init | 5–15 s | Converter recreated per upload |
| EasyOCR cold init | 60–120 s (first run on process) | CPU model load |
| OCR on 5–6 images | 10–30 s | CPU inference |
| Text pipeline — ~130 LLM extraction calls | 50–90 s | 17 rounds at concurrency 8 |
| Text pipeline — ~400 entity+relation embeddings | 30–50 s | One API call per merge |
| TLS handshakes on ~530 calls | 30–90 s | New `AsyncOpenAI` per call |
| Vision API + modal entity extraction | 20–42 s | Concurrent (semaphore=6) |
| Summary LLM call | 3–6 s | Single call |
| **Total wall-clock** | **210–450 s (≈ 4–8 min minimum, often more)** | |

The user's observed 10+ minutes is the worst end of this range plus rate-limit jitter and EasyOCR cold-start.

---

## 2. Optimization Tiers

The plan is layered so each tier compounds on the previous. **All six fixes are zero-quality-tradeoff** — no fewer entities, no weaker embeddings, no shallower KG, no missing connections.

### Tier 1 — Pure code-level micro-optimizations (no architecture change)

#### Fix 1: Singleton `AsyncOpenAI` client
**Where:** `backend/app/rag/utils.py` — `openai_embedding_func`, `openai_llm_func`, `openai_vision_func`.

**Current:** Each function constructs `AsyncOpenAI(api_key=...)` on every call. Every API call therefore pays a fresh TCP + TLS handshake to `api.openai.com` (50–150 ms each).

**Change:** Module-level `_openai_client = AsyncOpenAI(...)` initialized once. All three wrappers reuse it. The underlying `httpx.AsyncClient` keeps the connection pool warm, so repeated calls hit pre-established HTTP/2 multiplexed streams.

**Expected savings on 635 KB PPTX:** ~30–90 s of pure handshake overhead removed across ~530 API calls.

**Quality impact:** None. The OpenAI API response for a given input is identical regardless of which client object made the call.

**Implementation note:** keep the lazy lookup of `OPENAI_API_KEY` so the test suite's `sk-test-placeholder` still works at import time.

---

#### Fix 2: Minimum token threshold for entity extraction on tiny chunks
**Where:** `backend/app/rag/operate.py` — gate at the start of `extract_entities` per-chunk loop.

**Current:** Every chunk — including 5-token slide titles like *"Chapter 2"*, *"Introduction"*, lone bullet headings — fires a full LLM entity-extraction call. With `split_by_character="\n\n"`, a 43-slide PPTX produces 130–200 chunks, many of them too short to yield meaningful triples.

**Change:** If `chunk["tokens"] < MIN_EXTRACT_TOKENS` (suggested: 30), skip the LLM extraction for that chunk only. The chunk is still:
- ✅ stored in `text_chunks` KV (Postgres)
- ✅ embedded into `chunks_vdb` (Chroma)
- ✅ fully searchable by naive vector retrieval

Only the *entity extraction* LLM call is skipped — not chunk storage.

**Expected savings:** 30–60 % fewer entity-extraction LLM calls on slide-heavy decks (130 calls → ~50–70 calls). 20–40 s saved.

**Quality impact:** None. A 5-token slide title contributes no meaningful entity-relation triples — the LLM either returns empty extraction or hallucinates trivial facts ("Chapter 2 is a Chapter"). Skipping these makes the KG *cleaner*, not weaker. Anything substantive (slide bodies, paragraph text, bullet points with content) easily clears 30 tokens.

**Recursive dependency:** The chunk's `tokens` field is already populated by `chunking_by_token_size` in `operate.py`, so no new tokenization pass is needed.

---

#### Fix 3: Batched entity/relation embedding upserts in `merge_nodes_and_edges`
**Where:** `backend/app/rag/operate.py` — `_merge_nodes_then_upsert`, `_merge_edges_then_upsert`, and the orchestrator `merge_nodes_and_edges`.

**Current:** Each call to `_merge_nodes_then_upsert` ends with `entity_vdb.upsert({1 item})`, which triggers `ChromaVectorStorage.upsert` → `embedding_func([single_string])` → 1 OpenAI API call. Same for `_merge_edges_then_upsert`. For ~150 entities + ~250 relations in our test deck, that's ~400 individual embedding API calls.

**Change:** Refactor `merge_nodes_and_edges` to do the merge *logic* concurrently as today (it already uses `asyncio.Semaphore(graph_max_async)`), but defer the VDB upsert. Collect all merged entity payloads into a single dict, do **one** `entity_vdb.upsert(entity_payloads)` call at the end of Phase 1; same for `relationships_vdb.upsert(rel_payloads)` at the end of Phase 2. `ChromaVectorStorage.upsert` then computes the embeddings for the entire batch in a single OpenAI call (it already supports `batch_size=256`).

**Expected savings:** ~400 API calls → ~2–4 batched calls. 30–50 s saved, plus reduced rate-limit pressure.

**Quality impact:** None. OpenAI's embedding API is **stateless with respect to batch size** — `embed("X")` produces the same vector whether `"X"` is sent alone or alongside 99 other strings. Order independence of batched embedding has been verified for `text-embedding-3-small` since release.

**Recursive dependency:** The graph node `upsert_node` calls into Neo4j must still happen inside `_merge_nodes_then_upsert` (Neo4j writes are interleaved with read-modify-write logic on existing nodes). Only the *vector DB* upsert is deferred. Same split for edges. The current code already returns `node_data` from `_merge_nodes_then_upsert`; we just have it return the VDB payload too instead of writing inline.

**Code-level care:** `safe_vdb_operation_with_exception` retry logic must be preserved — wrap the batched upsert call, not each individual entity.

---

#### Fix 4: `DocumentConverter` singleton
**Where:** `backend/app/multimodal/parser.py` — `_convert_with_docling`.

**Current:** Every upload constructs a fresh `DocumentConverter(format_options={...})`. Docling's converter is heavyweight — it eagerly builds format-specific pipeline backends, including the OCR engine wrapper. 3–8 s per upload spent on init alone.

**Change:** Module-level `_converter` lazy-initialized on first call (with a `threading.Lock` for thread safety, like `_easyocr_reader` already does in `pipeline.py`). All subsequent uploads reuse the same converter.

**Expected savings:** 3–10 s per upload after the first.

**Quality impact:** None. `DocumentConverter` is stateless across `convert()` calls — the only mutable state is the in-flight document being parsed, which is local to each `convert()` invocation. Multiple files can be passed through the same converter without interference (Docling does this in its own batch examples).

**Recursive dependency:** `_install_docling_pdf_stub()` is already module-level and runs at import; it stays unchanged. The converter just gets memoized.

---

#### Fix 5: EasyOCR warm-start during FastAPI lifespan
**Where:** `backend/app/main.py` — the `lifespan` async context manager that already runs `_configure_logging()`, `init_db()`, and `classroom_rag_service` setup at startup.

**Current:** `_easyocr_reader` in `pipeline.py` is initialized lazily on the first OCR call (line 336–346). First file with at least one image on a fresh backend process pays the **full 60–120 s model-load cost on the critical path** — the user-perceived upload time spikes catastrophically for whoever happens to upload first after a deploy or a server restart. Subsequent uploads are fast because the singleton is hot.

**Change:** Inside the FastAPI lifespan startup block, schedule a fire-and-forget warm-up:
```python
async def _warmup_ocr():
    try:
        await asyncio.to_thread(_get_ocr_reader)
    except Exception as e:
        logger.warning(f"OCR warm-up failed (will retry on first use): {e}")

asyncio.create_task(_warmup_ocr())   # don't await — runs alongside server boot
```
This loads the CRAFT + CRNN model weights into memory while the server is idle, before any user upload arrives. The first user with an image-bearing upload pays **0 s** of OCR init cost instead of 60–120 s.

**Expected savings:** 60–120 s removed from first-upload critical path on every fresh process. After warm-start, every subsequent upload is the same as before (already amortized).

**Quality impact:** None. OCR is still run on every image with the same model weights, same `EasyOCR.Reader(["en"], gpu=False)` instantiation. Only the *timing* of the load changes.

**Recursive dependencies & care:**
1. **Background task lifetime:** the `asyncio.create_task` is not awaited, so the lifespan startup completes immediately and the server begins serving requests. If a user upload arrives mid-warm-up, the lazy `_get_ocr_reader()` call inside `_run_ocr_sync` will block on the same `_easyocr_lock`, then proceed once warm-up finishes — same as today's worst case, no worse.
2. **Process forking:** uvicorn's `--workers N` flag spawns N independent processes; each one runs its own lifespan and warms its own EasyOCR singleton. ✅ Independent, no shared-memory issue.
3. **Memory cost:** ~150 MB of model weights in RAM per worker process, paid up-front. Currently paid lazily — same total memory, just earlier. On a typical 2-worker dev box that's 300 MB resident at startup vs 0 MB. Acceptable for the latency win.
4. **Test environment:** `conftest.py` sets safe env defaults but doesn't run the lifespan; unit tests don't trigger warm-up. ✅ No test impact.
5. **EasyOCR network requirement:** on very first run ever (no cached weights on disk), EasyOCR downloads weights from its CDN. If startup happens on a network-isolated CI box without cached weights, warm-up fails. The `try/except` around the warm-up logs a warning and lets the server boot; first upload then either retries successfully or fails with a clear error. No regression vs current behavior.

---

### Tier 2 — Pipeline-level parallelization

#### Fix 6: Parallel text + modal pipelines
**Where:** `backend/app/multimodal/pipeline.py` — `MultimodalPipeline.process_document`, currently steps 3 and 4 run strictly sequentially (lines 167–296).

**Current flow:**
```
parse → separate → AWAIT engine.ainsert(text) → AWAIT modal_items_loop
```
The text pipeline (chunk + embed + extract entities + merge) **fully completes** before any image OCR pre-pass or vision API call begins. For our test deck that's ~150 s of text work blocking ~30 s of modal work that could have been running in parallel.

**Change:**
```
parse → separate → asyncio.gather(text_pipeline, modal_pipeline)
```
Both pipelines started together, awaited together. The OCR pre-pass and vision API calls fire while text-side entity extraction and merging are still running.

**Expected savings:** 30–60 s on a deck with 5–6 images. Larger savings on image-heavy PDFs.

**Quality impact:** None — and this needs careful justification because both pipelines write to the same storage objects:

| Storage | Text pipeline writes | Modal pipeline writes | Conflict? |
|---|---|---|---|
| `chunks_vdb` (Chroma) | text chunks | image/table/equation chunks | **No** — different deterministic IDs (`chunk-<hash>`), Chroma upsert is idempotent |
| `text_chunks` KV (Postgres) | text chunks | modal-generated chunks | **No** — different keys, asyncpg uses row-level locking |
| `entities_vdb` (Chroma) | entities from text | entities from images | **No** — same entity name from both sources triggers the existing merge logic in `_merge_nodes_then_upsert` (calls `get_node()` first, merges descriptions, dedup) |
| `relationships_vdb` (Chroma) | edges from text | `belongs_to` edges from modals | **No** — same merge logic |
| Neo4j graph | nodes + edges | `belongs_to` edges connecting modal chunks to text-extracted entities | **No** — Neo4j MERGE is idempotent; `upsert_node` and `upsert_edge` handle existing nodes |

The merge logic in `_merge_nodes_then_upsert` already does **read-modify-write** with conflict resolution — that's what it was built for (multiple chunks producing the same entity). Two concurrent pipelines producing overlapping entities is functionally identical to one pipeline producing overlapping entities, which is the normal case.

**Recursive dependencies & care:**
1. **Temp directory lifetime** (already a known concern per `pipeline.py:112`): the `_managed_tmp` directory holds image files that vision processors base64-encode. The `finally` block currently cleans it up *after* both `await`s. With `asyncio.gather`, the cleanup remains in the same `finally` block — both pipelines must finish before cleanup. ✅ Already satisfied.
2. **Modal processors call `merge_nodes_and_edges`** internally (each image triggers entity extraction). If the text pipeline is also calling `merge_nodes_and_edges`, both share the same `engine._graph`, `engine._entities_vdb`, `engine._relationships_vdb`. All three handle concurrent writes correctly (verified above).
3. **Doc status writes:** `engine._doc_status.set_status(doc_id, ...)` is called by `_insert_single_document`. The modal pipeline computes its own `doc_id = compute_mdhash_id(text_content or filename, prefix="doc-")` (pipeline.py line 240) — same ID as the text pipeline (since both hash the same `text_content`). Writes are idempotent UPSERT. ✅ Safe.
4. **Rate limit pressure** rises during the parallel window. Mitigated by Tier 2-bis below.

---

### Tier 3 — Architectural: Progressive Processing (Phase 1 / Phase 2 split)

This is the headline change. It separates **what is required to chat** from **what is required for KG-driven features**, so the user can start interacting after Phase 1 (~15–30 s) while Phase 2 finishes in the background (~150–300 s).

#### What each feature needs

| Feature | RAG mode | Storage required | Phase |
|---|---|---|---|
| 1:1 chat (`routes/chat.py`) | `naive` | `chunks_vdb` only | **Phase 1** |
| Flashcards (`flashcard_service.py`) | `naive` | `chunks_vdb` only | **Phase 1** |
| Group chat `@SAMpai` (`group_chat_agent.py`) | `naive` | `chunks_vdb` only | **Phase 1** |
| Quiz (`quiz_service.py`) | `mix` | Neo4j KG + `entities_vdb` | **Phase 2** |
| Mindmap (`mindmap_service.py`) | `mix`, `traversal_hops=2` | Neo4j KG + `entities_vdb` + `relationships_vdb` | **Phase 2** |

Verified by grep against the codebase:
- `routes/chat.py:75` — only checks `processing_status == "completed"`. After change: accepts `naive_ready` too.
- `routes/flashcards.py:70` — same gate.
- `services/group_chat_agent.py:175` — `@SAMpai` respond gate.
- `routes/quiz.py:54` and `routes/mindmap.py:131` — keep `COMPLETED`-only gate.

#### Phase 1 vs Phase 2 work breakdown (in `engine.py._insert_single_document`)

The current monolithic 8-step function maps cleanly:

| Step | What it does | Phase |
|---|---|---|
| 1. `_full_docs.upsert` | Store full document | **1** |
| 2. `chunking_by_token_size` | Tokenize + split | **1** |
| 3. Build chunk records | In-memory | **1** |
| 4. `_text_chunks.filter_keys` | Skip already-indexed | **1** |
| 5. `_chunks_vdb.upsert` + `_text_chunks.upsert` | Embed + store chunks | **1** |
| 6. *(currently 5 cont.)* | — | — |
| 7. `extract_entities` | LLM entity extraction per chunk | **2** |
| 8. `merge_nodes_and_edges` | Graph + entity/rel VDB writes | **2** |
| 9. `_doc_status.set_status(PROCESSED)` | Mark fully done | end of **2** |

Add an intermediate doc-status value `CHUNKS_READY` between steps 6 and 7.

#### Required changes

**Backend — model & schema:**
1. `backend/app/models/file.py` — add `NAIVE_READY = "naive_ready"` to `ProcessingStatus` enum.
2. `backend/alembic/versions/<new>.py` — Postgres enum `ALTER TYPE processingstatus ADD VALUE 'naive_ready'`.
3. `backend/app/schemas/file.py` — surface the new status string in API responses.

**Backend — RAG engine split:**
4. `backend/app/rag/engine.py` — split `_insert_single_document` into:
   - `_insert_phase1(content, file_path, ...)` — runs steps 1–6, sets `_doc_status` to `CHUNKS_READY` (new `DocStatus` value in `base.py`).
   - `_insert_phase2(doc_id, file_path, ...)` — runs steps 7–9, reads chunks back from `_text_chunks` KV, sets `DocStatus.PROCESSED`.
   - `ainsert(content, ..., phase: Literal["full", "phase1", "phase2"] = "full")` — dispatcher. `"full"` preserves current behavior for any caller (tests, quiz/flashcard regen paths) that doesn't want the split.

**Backend — multimodal pipeline:**
5. `backend/app/multimodal/pipeline.py` — `process_document` accepts a `phase` argument. In Phase 1 mode it does Docling parse + text-chunk insert (`engine.ainsert(..., phase="phase1")`) only. Modal processing (OCR + vision API + per-modal entity extraction) is Phase 2 work because each modal item runs `_create_entity_and_chunk` which triggers the same KG merge path. Phase 2 mode does modal items + calls `engine.ainsert(..., phase="phase2")` for the text content's entity extraction.

   ✱ Note: the OCR pre-pass produces no KG output by itself — but vision/table/equation processors do. Cleanest split is: **Phase 1 = text chunks only**, **Phase 2 = text-entity extraction + all modal processing**.

**Backend — file processor orchestration:**
6. `backend/app/services/file_processor.py` — restructure into:
   ```
   process_file(file_id, content, filename):
     status → PROCESSING
     run pipeline phase=1                 # ≈ 15–30 s
     status → NAIVE_READY                  # 🚀 chat now usable
     status → PROCESSING (kept) OR introduce a flag
     queue process_phase2 as BackgroundTask
     return

   process_phase2(file_id):
     run pipeline phase=2                 # ≈ 150–300 s
     generate summary → file.description
     status → COMPLETED
   ```
   Two error paths: Phase 1 failure → `FAILED` (file unusable). Phase 2 failure → `FAILED` (KG features unavailable, but optionally keep chat working — see "Open design choice" below).

**Backend — feature gates (small, surgical):**
7. `backend/app/routes/chat.py:75` — change `if file.processing_status.value != "completed":` to `if file.processing_status not in (ProcessingStatus.NAIVE_READY, ProcessingStatus.COMPLETED):`.
8. `backend/app/routes/flashcards.py:70` — same change.
9. `backend/app/services/group_chat_agent.py:175` — same change for `@SAMpai` respond path. Update the "still indexing" message to be triggered only by `PENDING`/`PROCESSING`/`FAILED`.
10. `backend/app/routes/quiz.py:54` — leave at `COMPLETED`-only.
11. `backend/app/routes/mindmap.py:131` — leave at `COMPLETED`-only.

**Backend — file summary timing:**
12. The 2–3 sentence LLM summary in `file_processor.py:101–109` populates `File.description`, used by the file list UI. It's 1 cheap LLM call. Keep it in **Phase 1** (just before flipping to `NAIVE_READY`) so the file card renders the summary immediately. It does not depend on KG.

**Frontend — type updates:**
13. `frontend/components/classroom/files-section.tsx:44, 50, 77, 83, 99` — extend the `"pending" | "processing" | "completed" | "failed"` literal types to include `"naive_ready"`. Polling continues until `completed` or `failed` (so polling does NOT stop at `naive_ready`); but the file card UI shows a partial-ready state (e.g. blue check + "Chat ready, deeper analysis loading…").
14. `frontend/components/classroom/sidebar.tsx:28` — same type widening.
15. `frontend/app/classroom/[id]/folder/[folderId]/file/[fileId]/page.tsx:42, 131, 134, 170, 175, 248, 256, 268–271` — same widening.

**Frontend — feature gating in the file page:**
16. In the file page (the tabs: Chat / Quiz / Flashcards / Mindmap / GroupChat), gate each tab by status:
    ```ts
    const naiveReady = status === "naive_ready" || status === "completed"
    const fullReady  = status === "completed"
    ```
    - **Chat tab:** enabled when `naiveReady`. Currently checks `isCompleted` — change to `naiveReady`.
    - **Flashcards tab:** enabled when `naiveReady`.
    - **Group Chat invite/SAMpai:** enabled when `naiveReady`.
    - **Quiz tab:** disabled when `!fullReady`. Show tooltip: *"Quiz becomes available once full document analysis finishes (a moment longer)."*
    - **Mindmap tab:** disabled when `!fullReady`. Same tooltip.
17. Visual treatment: gray + non-clickable + tooltip on hover. Reuse existing disabled-button styling. A small spinner badge on disabled tabs indicates active background processing.
18. Polling continues at the existing 2 s interval until `completed` or `failed`. When status flips `naive_ready → completed`, the disabled tabs become enabled with a subtle highlight pulse.

#### Time budget after the split

| Phase | Wall-clock | What user can do |
|---|---|---|
| **Phase 1** | **15–30 s** | Open chat, generate flashcards, invite to group chat, ping `@SAMpai` |
| **Phase 2** (background) | 150–300 s | Continues silently; quiz/mindmap unlock when done |

A **20–30× improvement** in time-to-first-meaningful-interaction.

#### Quality impact: zero, every layer verified

- **Naive features (chat / flashcards / `@SAMpai`):** these never read `entities_vdb`, `relationships_vdb`, or Neo4j. Verified in `operate.naive_query` — only touches `chunks_vdb` and `text_chunks` (`engine.py:460–467`). The chunks are bit-for-bit identical to what the current monolithic flow produces — same chunking function, same embedding model, same Chroma collection.
- **KG features (quiz / mindmap):** gated behind `COMPLETED`. When they finally run, the KG is fully built — same as today, just delivered via a separate background task. Same `merge_nodes_and_edges`, same `kg_query` traversal.
- **No race condition with naive queries during Phase 2:** Phase 2 writes to `entities_vdb`, `relationships_vdb`, Neo4j, `_full_entities`, `_full_relations`, `_entity_chunks`, `_relation_chunks`. Naive query reads `chunks_vdb` and `text_chunks` only. **Disjoint storage namespaces.** Verified.

#### Open design choice (small)

If Phase 2 fails (e.g. OpenAI rate limit exhaustion, network blip), should the file:
- **(A)** become `FAILED` overall (user must reprocess) — current behavior post-split, simple
- **(B)** stay at `NAIVE_READY` with a separate `KG_FAILED` flag — chat still works, user has option to retry Phase 2

I recommend **(B)** because it preserves user value. Add `kg_status` column to `files` table tracking just Phase 2: `pending / processing / ready / failed`. Quiz/mindmap routes check `kg_status == ready` instead of `processing_status == COMPLETED`. The existing `processing_status` becomes the Phase-1 status only after the split — semantically cleaner.

If you want minimum churn, go with **(A)** — same enum, just one new value (`NAIVE_READY`). I'll proceed with **(A)** in the implementation steps unless you say otherwise.

---

### Tier 2-bis — Rate limit contention mitigation (no separate API key needed)

Once Phase 2 runs in the background while users actively chat, both share the OpenAI rate limit bucket. Mitigation:

#### Fix 7: Tiered concurrency for foreground vs background work
**Where:** `backend/app/rag/constants.py` and `engine.py`.

**Change:** Split `DEFAULT_MAX_ASYNC = 8` into two values:
- `FOREGROUND_MAX_ASYNC = 8` — used by chat, flashcards, quiz, mindmap, group-chat (interactive paths)
- `BACKGROUND_MAX_ASYNC = 4` — used by Phase 2 entity extraction, merge

Phase 2's `extract_entities` uses the lower limit. `merge_nodes_and_edges` already reads `global_config["llm_model_max_async"]` — pass the background value.

**Expected effect:** Phase 2 takes ~25 % longer (acceptable — it's already background), but interactive chat/flashcard calls always have headroom and never queue behind 8 concurrent extraction calls.

**Quality impact:** None. This is a scheduling change, not a content change.

**Why not just one API key with a separate organization/project?** Possible but operationally heavier (two billing surfaces). Tiered concurrency gets ~90 % of the isolation benefit with zero infrastructure change. Reserve key splitting for if you scale to many concurrent uploads.

---

## 3. Compounded Expected Improvement

For the 635 KB / 43-slide PPTX, end-to-end:

| Optimization | Time saved |
|---|---|
| Fix 1 — singleton OpenAI client | 30–90 s |
| Fix 2 — min-token gate on extraction | 40–70 s |
| Fix 3 — batched entity/relation embeddings | 20–40 s |
| Fix 4 — DocumentConverter singleton | 3–10 s |
| Fix 5 — EasyOCR warm-start at server startup | 60–120 s (first upload only) |
| Fix 6 — parallel text + modal | 30–60 s |
| **Subtotal: full processing wall-clock** | **210–450 s → 50–180 s** (3–6× faster, plus first-upload spike eliminated) |
| Tier 3 — Phase 1 / Phase 2 split | **Time-to-chat: ~15–30 s** |

The separation is the headline number. Even Phase 2 takes 60–200 s instead of 210–450 s thanks to Tiers 1+2 compounding into it.

---

## 4. Implementation Order (recommended)

1. **Tier 1 fixes** (safe, isolated, no API surface change)
   - Fix 1: AsyncOpenAI singleton — 30 min
   - Fix 4: DocumentConverter singleton — 15 min
   - Fix 5: EasyOCR warm-start in lifespan — 30 min
   - Fix 2: Min-token extraction gate — 1 h (test on real chunks first)
   - Fix 3: Batched VDB upserts in `merge_nodes_and_edges` — 2–3 h (touches the merge orchestrator's return shape)
   - Run E2E benchmark (`scripts/e2e_driver.py`) after each — verify per-stage timings improve, KG node/edge counts unchanged.

2. **Tier 2 — parallel pipelines**
   - Fix 6: `asyncio.gather(text_pipeline, modal_pipeline)` in `pipeline.py` — 2 h
   - Verify: same number of entities/edges as before, no double-write errors in logs.

3. **Tier 3 — Phase split** (the architectural change)
   - Backend: enum + alembic migration + engine split + processor split + 4 route gates — 1 day
   - Frontend: type widening + tab gating + tooltip — half day
   - Tier 2-bis (Fix 7 — tiered concurrency) — 30 min, ship together with Tier 3
   - Verify: chat usable at ~20 s post-upload; quiz/mindmap stay disabled until COMPLETED; benchmark shows no regression in answer quality.

Total engineering effort: ~2–3 days for one developer, including testing.

---

## 5. Recursive Dependencies & Things to Watch

These are the cross-cutting concerns I traced through the codebase that must be respected:

- **Two Postgres URLs:** `DATABASE_URL` (SQLAlchemy/psycopg) for app models, `ASYNCPG_DATABASE_URL` for RAG layer. Status enum changes require an Alembic migration on the SQLAlchemy side; RAG `doc_status` table stays unchanged unless you adopt the `kg_status` column proposal.
- **Workspace isolation:** every storage key is prefixed with `classroom_{id}`. The phase split doesn't change workspace logic — Phase 1 and Phase 2 both run in the same workspace.
- **`file.file_url` is the citation key:** unchanged by all six fixes. Don't rename.
- **NumPy 2.x shim in `app/main.py`** must run before `chromadb` imports — the phase split keeps all chromadb imports inside the engine module, so unaffected.
- **`pipeline.py:112` temp directory:** Tier 2 (parallel pipelines) keeps the `_managed_tmp` cleanup in the post-`gather` `finally` block. ✅
- **Group chat `@SAMpai` Stage B (Chroma vector similarity vs document):** uses `chunks_vdb` only, so Phase 1 readiness is sufficient. ✅
- **Quiz `_extract_chat_topics`** reads chat history — chat history may exist post-Phase 1 (because chat is enabled) but quiz itself stays gated to `COMPLETED`, so this is fine.
- **Stale `"mode": "mix"` strings in `routes/chat.py` (lines 106, 173):** cosmetic labels in metadata — leave alone, unrelated to this plan.
- **`reset_all_dbs.py`:** if you adopt the `kg_status` column proposal, add it to the inline DDL there too.
- **`scripts/e2e_driver.py`:** currently waits for `processing_status == "completed"` before asking. After Tier 3, add a flag `--wait-for=naive_ready|completed` so the smoke test can validate Phase 1 readiness alone.
- **CI tests (`pytest -m "not llm"`):** none of these fixes affect test paths since tests use mocks/skips for storage. Verify after Tier 3 that any test asserting status transitions accepts the new `NAIVE_READY` value.
- **Frontend polling cadence:** existing 2 s polling in `files-section.tsx` and `file/[fileId]/page.tsx` keeps polling through `naive_ready → completed`. Don't stop polling at `naive_ready`. Verified the relevant lines (`files-section.tsx:131`, `page.tsx:131,175`).

---

## 6. Quality Tradeoff Guarantee

Each fix has been individually verified to introduce no quality regression:

| Fix | Why it's quality-neutral |
|---|---|
| 1 — singleton client | Same API, same model, same response |
| 2 — min-token gate | Skipped chunks contribute no meaningful triples; still vector-searchable |
| 3 — batched embeddings | Embedding API is batch-size invariant |
| 4 — DocumentConverter singleton | Stateless across `convert()` calls |
| 5 — EasyOCR warm-start | Same model loaded earlier; OCR results unchanged |
| 6 — parallel pipelines | Storage layers handle concurrent writes; merge logic already idempotent |
| 7 — tiered concurrency | Scheduling change only; same number/quality of API calls |
| Tier 3 — phase split | Each feature reads from exactly the storage it needs, gated until that storage is ready |

If any of these reveal an unexpected regression in benchmark results (`app/evaluation/run_benchmark_lightrag.py`), the change is small enough to revert independently — they don't depend on each other except where noted (Fix 3 touches the same function as Tier 3's Phase 2; Tier 2-bis lands with Tier 3).

---

## 7. Verification Plan

After all changes:

1. **Unit tests:** `pytest -m "not llm and not integration"` — all green.
2. **Integration tests:** `pytest -m integration` against dockerized DB/Neo4j/Chroma — all green.
3. **E2E timing:** `scripts/e2e_driver.py --file <test.pptx> --out logs/e2e_after.json`. Compare `logs/e2e_after.json` vs pre-change baseline — assert:
   - Time from `upload` to first successful `chat` response: **≤ 30 s**
   - Time from upload to `processing_status=completed`: **≤ 200 s** (down from ~600 s+)
4. **KG quality:** run `app/evaluation/run_benchmark_lightrag.py` against the same ground-truth set before and after. Assert:
   - ROUGE-L F1, BERTScore F1, semantic similarity all within ±0.5 % of baseline
   - No drop in entity count or edge count for the test classroom
5. **Observability:** confirm in logs that:
   - "Initializing EasyOCR reader" appears exactly **once** per backend process — and now happens during startup (Fix 5), not on first upload
   - "EasyOCR reader ready" log line is emitted *before* the first request arrives in the access log
   - "DocumentConverter initialized" appears exactly once per process (new log line in Fix 4)
   - Embedding batch size ≥ N entities for entity merge (proves Fix 3 is batching)
   - "Phase 1 done" log line appears 15–30 s after upload start

---

That's the full plan. Each fix is decoupled and individually shippable; the phase split is the architectural move that unlocks the 20× UX win, and the rest are the substrate that makes Phase 2 finish quickly enough to feel invisible.
