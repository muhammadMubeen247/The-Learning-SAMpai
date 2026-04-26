# Benchmark Plan: LightRAG vs. LangChain RAG Evaluation

## Project Context

This is "The Learning SAMpai v2" — a university classroom learning platform (FYP project).
The RAG backend was migrated from **LangChain + ChromaDB** (old system) to a custom
**LightRAG** implementation using a knowledge graph (Neo4j) + vector store (ChromaDB) +
JSONB key-value store (PostgreSQL via asyncpg).

**Goal:** Evaluate the new LightRAG system (in **naive mode** — pure vector retrieval, no KG at query time) on 30 ground-truth Q&A questions and produce a side-by-side comparison table against the old system's documented metrics for the FYP thesis.

**Architecture decision:** Chat queries now use `mode="naive"` (direct ChromaDB vector search on the `chunks` collection). The knowledge graph (Neo4j) is preserved and used only for quiz generation and future mind map features. This is a one-line change in `backend/app/routes/chat.py`.

---

## Ground Truth Dataset

File: `backend/app/evaluation/ground_truth.json`

- **Document:** Chapter #1 Introduction to Psychology.pdf
- **30 questions** covering 3 topic areas (topic_id 15, 16, 17) across 3 categories (factual, reasoning, application)
- **Fields per question:** `id`, `question`, `ground_truth`, `relevant_page`, `topic_id`, `category`

> Note: `relevant_page` and `topic_id` are **informational only** in this benchmark.
> Neither field affects any computed metric. Do not remove them from the JSON — they
> document provenance. Do not use them in any metric calculation.

---

## What Was Done on the Old System (Reference — Do NOT Re-run)

The old system (`langchain_rag_service.ask_question()` + `langchain_vector_store.search_similar_chunks()`)
was evaluated on **9 metrics**:

### Answer Quality (3 metrics)
| Metric | Library | Method |
|---|---|---|
| ROUGE-L F1 | `rouge-score` | LCS overlap between generated answer and ground truth |
| BERTScore F1 | `bert-score` | BERT token-level semantic similarity |
| Semantic Similarity | `sentence-transformers` (`all-MiniLM-L6-v2`) | Cosine similarity of sentence embeddings |

### Retrieval Quality (3 metrics)
| Metric | Method |
|---|---|
| Hit Rate@5 | Whether `relevant_page` appeared in any top-5 retrieved chunk's `page_number` metadata |
| MRR | `1 / rank` of first retrieved chunk whose `page_number` matched `relevant_page` |
| Precision@5 | Fraction of top-5 chunks whose `page_number` matched `relevant_page` |

These metrics required `search_similar_chunks()` to return raw chunk metadata including
`page_number` (stored as int in ChromaDB with fields: `file_id`, `page_number`, `chunk_index`).

### System Performance (3 metrics)
| Metric | Method |
|---|---|
| Avg Latency (s) | `time.perf_counter()` around each `ask_question()` call |
| Avg Output Tokens | `tiktoken` (`cl100k_base`) on the answer string |
| Estimated Cost (USD) | gpt-3.5-turbo pricing: $0.50/1M input, $1.50/1M output |

---

## Why Retrieval Metrics Are Dropped for the New System

The new LightRAG `engine.aquery()` returns a `QueryResult` with:
- `content` — the synthesized answer string
- `reference_list` — `[{"file_path": "R2_URL"}]` — **file-level citations only, no page numbers**

In `mode="naive"`, the system performs direct cosine similarity search on the `chunks` ChromaDB
collection and synthesises an answer from the top-k chunks. The response surfaces which *file*
was cited, not which *page*.

There is no `page_number` in any returned data. Hit Rate, MRR, and Precision@5 are excluded.
The comparison table will note:

> *"Retrieval attribution metrics not applicable — naive vector synthesis does not expose
> chunk-level page provenance. The new system returns file-level citations (R2 URLs) only."*

---

## Metrics for the New System (Option B — 6 metrics)

### Answer Quality (3)
| Metric | Library | Method |
|---|---|---|
| ROUGE-L F1 | `rouge-score` | `RougeScorer(["rougeL"])` per question, average `fmeasure` |
| BERTScore F1 | `bert-score` | `score(predictions, references, lang="en", model_type="distilbert-base-uncased")`, average F1 |
| Semantic Similarity | `sentence-transformers` | `SentenceTransformer("all-MiniLM-L6-v2")` embeddings, cosine similarity, average |

### System Performance (3)
| Metric | Method |
|---|---|
| Avg Latency (s) | `time.perf_counter()` around each `engine.aquery()` call |
| Avg Output Tokens | `tiktoken` (`cl100k_base`) on `result.content` |
| Estimated Cost (USD) | gpt-4o pricing: $5.00/1M input, $15.00/1M output. Estimate input as `avg_output_tokens * 10` (LightRAG builds large context internally; input tokens are not directly observable from outside the engine). Mark as "estimated". |

---

## Tasks

### Task 1 — Switch chat route to naive mode

File: `backend/app/routes/chat.py`

Find the `QueryParam` construction inside the ask endpoint (the line that currently sets `mode="mix"`) and change it to:

```python
param = QueryParam(
    mode="naive",
    chunk_top_k=20,
    conversation_history=history,
    file_filter=file_url,
)
```

Remove `top_k=40` — it is only used by the KG entity/relation retrieval paths and has no effect in naive mode.

**Do NOT touch any other line in `chat.py`.** The `_get_file_and_classroom()` helper, the chat history loading, the `engine.aquery()` call, the DB persistence, and the response schema all stay identical.

---

### Task 2 — Re-run benchmark in naive mode

All evaluation files already exist:
```
backend/app/evaluation/__init__.py          ← exists
backend/app/evaluation/ground_truth.json    ← exists
backend/app/evaluation/run_benchmark_lightrag.py  ← exists (needs mode updated)
backend/app/evaluation/compute_metrics.py   ← exists
backend/app/evaluation/compare.py          ← exists
backend/app/evaluation/results/            ← exists, contains prior mix-mode results
```

Update `run_benchmark_lightrag.py` to use `mode="naive"` (see per-question call pattern below), then re-run the benchmark.

---

## Script Specifications

### `run_benchmark_lightrag.py`

**CLI:** `python app/evaluation/run_benchmark_lightrag.py --classroom-id INT --file-url STR`

**Implementation rules (in order):**

1. **NumPy 2.x shim — must be the very first code that runs**, before any other import:
   ```python
   import numpy as np
   if not hasattr(np, "float_"):
       np.float_ = np.float64
   if not hasattr(np, "int_"):
       np.int_ = np.intp
   ```
   chromadb 0.4.24 references removed NumPy 2.x aliases. If this runs after any chromadb
   import, it is too late.

2. **Set service URLs via `os.environ.setdefault()` BEFORE loading any `.env` file:**
   ```python
   os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:password@localhost:5433/Learning_SAMpai_db")
   os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
   os.environ.setdefault("NEO4J_USERNAME", "neo4j")
   os.environ.setdefault("NEO4J_PASSWORD", "sampai_neo4j_password")
   os.environ.setdefault("CHROMA_HOST", "localhost")
   os.environ.setdefault("CHROMA_PORT", "8001")
   os.environ.setdefault("SECRET_KEY", "benchmark-dummy-secret")
   ```
   Then load `.env.docker` (or `.env`) with `override=False` to pick up `OPENAI_API_KEY`
   without overwriting the service URLs above.

   **Why this order matters:** `.env.docker` contains Docker-internal URLs (`db:5432`,
   `neo4j:7687`). If `load_dotenv()` runs first, it will set those values and
   `setdefault()` will have no effect. The script runs on the host machine, not inside
   Docker, so Docker-internal hostnames will fail.

3. **Fully async.** Use `asyncio.run(main())`. Do NOT use `loop.run_until_complete()`.

4. **Per-question call pattern:**
   ```python
   from app.services.classroom_rag import classroom_rag_service
   from app.rag.base import QueryParam

   engine = await classroom_rag_service.get_engine(classroom_id)
   param = QueryParam(
       mode="naive",             # pure vector retrieval — NO KG traversal
       chunk_top_k=20,
       conversation_history=[],  # each question is independent — no history
       file_filter=file_url,     # scope to this document only
   )
   t0 = time.perf_counter()
   result = await engine.aquery(question_text, param)
   latency = time.perf_counter() - t0
   answer = result.content or ""
   output_tokens = len(enc.encode(answer))
   ```

   **Note:** `top_k` is intentionally omitted. In naive mode `engine.aquery()` only uses `chunk_top_k` for the ChromaDB chunks query. `top_k` controls KG entity retrieval which is not executed.

5. **Reuse the engine** across all 30 questions. Do not reinitialize or recreate it.

6. **Shutdown after all questions:**
   ```python
   await classroom_rag_service.finalize_all()
   from app.rag.storage.postgres_kv import close_pool
   await close_pool()
   ```

7. **Output** — save to `backend/app/evaluation/results/lightrag_raw.json`:
   ```json
   {
     "benchmark_info": {
       "system": "lightrag_naive",
       "classroom_id": 3,
       "file_url": "...",
       "timestamp": "..."
     },
     "results": [
       {
         "id": 1,
         "question": "...",
         "ground_truth": "...",
         "generated_answer": "...",
         "latency_s": 4.21,
         "output_tokens": 87,
         "category": "factual"
       }
     ]
   }
   ```
   `relevant_page` and `topic_id` are NOT written to the output — they are unused.

---

### `compute_metrics.py`

**CLI:** `python app/evaluation/compute_metrics.py --input app/evaluation/results/lightrag_raw.json --system naive`

Reads the raw results JSON, computes all 6 metrics, prints a table, saves
`backend/app/evaluation/results/naive_metrics.json`.

---

### `compare.py`

**CLI:**
```
python app/evaluation/compare.py \
  --new app/evaluation/results/naive_metrics.json \
  --old-values '{"rouge_l": 0.XX, "bertscore": 0.XX, "semantic_sim": 0.XX, "avg_latency": X.XX, "avg_output_tokens": XXX, "cost": X.XX, "hit_rate": 0.XX, "mrr": 0.XX, "precision": 0.XX}'
```

Also accept `--old app/evaluation/results/old_metrics.json` as an alternative.

**Output table format:**
```
Metric                     | LangChain + ChromaDB | LightRAG (Naive)
---------------------------|----------------------|------------------
ROUGE-L F1                 |               0.XX   |            0.XX
BERTScore F1               |               0.XX   |            0.XX
Semantic Similarity        |               0.XX   |            0.XX
Avg Latency (s)            |               X.XX   |            X.XX
Avg Output Tokens          |               XXX    |            XXX
Estimated Cost (30 Qs)     |              $X.XX   |           $X.XX
Hit Rate@5                 |               0.XX   |            N/A *
MRR                        |               0.XX   |            N/A *
Precision@5                |               0.XX   |            N/A *

* Retrieval attribution metrics not applicable for the new system.
  LightRAG naive mode does not expose chunk-level page provenance.
  The new system returns file-level citations (R2 URLs) only.
```

---

## What NOT to Do

| Rule | Reason |
|---|---|
| Do NOT use `topic_id` for anything | Topics were removed from the new system entirely |
| Do NOT use `relevant_page` for any metric | That data path does not exist in the new system |
| Do NOT use `chromadb.PersistentClient` | Windows Smart App Control blocks the native `.pyd` it requires; new system uses `HttpClient` |
| Do NOT use `db:5432` as the Postgres host | That is the Docker-internal hostname; scripts run on the host must use `localhost:5433` |
| Do NOT call `load_dotenv()` before setting service URLs | `.env.docker` contains Docker-internal values that will overwrite host-accessible ones |
| Do NOT use synchronous LightRAG calls | Everything in `app/rag/` is async; the benchmark must use `asyncio.run()` |
| Do NOT add Hit Rate, MRR, Precision@5 to new system output | Mark them `N/A` in the comparison table |
| Do NOT create a new `ClassroomRAGService` | Import the module-level singleton: `from app.services.classroom_rag import classroom_rag_service` |
| Do NOT skip `finalize_all()` and `close_pool()` | The asyncpg pool will hang the process if not explicitly closed |

---

## Services Required at Runtime

| Service | Host:Port | Docker Container |
|---|---|---|
| PostgreSQL | `localhost:5433` | `learning-sampai-db` |
| Neo4j (Bolt) | `localhost:7687` | `learning-sampai-neo4j` |
| ChromaDB | `localhost:8001` | `learning-sampai-chroma` |
| OpenAI API | (cloud) | via `OPENAI_API_KEY` in `.env.docker` |

Start data services: `docker compose up -d db neo4j chroma`

---

## Prerequisite: Psychology PDF Must Be Ingested

**Already done.** The Psychology PDF was ingested into classroom_id=3, folder_id=3.

- `classroom_id`: **3**
- `file_url`: `https://d099dd13d3d9c68abd2a13929abba54e.r2.cloudflarestorage.com/classroom-files/folders/3/Chapter #1 Introduction to Psychology.pdf`
- `processing_status`: `completed`

No re-ingestion needed. The chunks collection (`classroom_3__chunks`) in ChromaDB already contains all embeddings for this file. Start data services and run the benchmark directly.

---

## Run Order

```powershell
cd "c:\Mubeen\FYP\Project\The Learning SAMpai v2\backend"

# Step 0 — Apply the one-line chat route change (done once, not per benchmark run)
# In backend/app/routes/chat.py, change mode="mix" → mode="naive", remove top_k=40
# (See Task 1 above)

# Step 1 — Run 30 questions through LightRAG naive mode (~3–6 min)
# classroom_id=3, file already ingested
.venv\Scripts\python.exe app/evaluation/run_benchmark_lightrag.py `
  --classroom-id 3 `
  --file-url "https://d099dd13d3d9c68abd2a13929abba54e.r2.cloudflarestorage.com/classroom-files/folders/3/Chapter #1 Introduction to Psychology.pdf"

# Step 2 — Compute 6 metrics from raw results
.venv\Scripts\python.exe app/evaluation/compute_metrics.py `
  --input app/evaluation/results/lightrag_raw.json `
  --system naive

# Step 3 — Print comparison table (provide old system values)
.venv\Scripts\python.exe app/evaluation/compare.py `
  --new app/evaluation/results/naive_metrics.json `
  --old-values '{"rouge_l": 0.XX, "bertscore": 0.XX, "semantic_sim": 0.XX, "avg_latency": X.XX, "avg_output_tokens": XXX, "cost": X.XX, "hit_rate": 0.XX, "mrr": 0.XX, "precision": 0.XX}'
```

> **Note on prior mix-mode results:** `lightrag_raw.json` and `lightrag_metrics.json` in the results
> folder are from the previous `mode="mix"` benchmark run. Step 1 above will overwrite `lightrag_raw.json`
> with the naive-mode run. If you want to preserve the mix-mode data, rename it first:
> ```powershell
> Rename-Item app/evaluation/results/lightrag_raw.json lightrag_mix_raw.json
> Rename-Item app/evaluation/results/lightrag_metrics.json lightrag_mix_metrics.json
> ```

---

## Python Dependencies (all already installed in `.venv`)

- `rouge-score`
- `bert-score`
- `sentence-transformers`
- `tiktoken`
- `asyncpg`
- `chromadb==0.4.24` (HttpClient only)
- `neo4j` (Python driver)
- `python-dotenv`
