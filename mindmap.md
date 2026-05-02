# Mindmap Feature — Implementation Plan

A per-file, AI-generated, interactive mindmap that mirrors the document's conceptual structure as a navigable tree. Clicking any node opens a chat in the centre that summarises that topic via RAG and lets the user follow-up. Modeled on NotebookLM's mindmap UX.

This document is the single source of truth. It is structured so it can be handed to Claude Code and implemented end-to-end.

---

## 1. Goals & Non-Goals

### Goals
- **One mindmap per file**. Anchored to a single `File`, generated on demand, cached after first build.
- **Entry point**: a "Mindmap" button beneath each file card in the folder view. Click → dedicated `/classroom/{id}/folder/{fid}/file/{fileId}/mindmap` route.
- **Root node = topic**: a 2–5 word, well-defined topic name (e.g. "Human Resource Management"), not the literal filename.
- **Recursive expansion**: each node, when expanded, reveals 2–6 child sub-topics. Children expand into grandchildren until leaf nodes (max 4 levels).
- **Click-to-chat**: clicking any node collapses the mindmap to a side panel (~30%) and opens a chat (~70%) in the centre. Right-side metadata panel from NotebookLM is **out of scope** (per user).
- **Initial summary** is generated for the clicked node via RAG with a system prompt; subsequent messages are normal RAG chat scoped to the file.
- **Multi-node chat thread**: clicking another node appends its summary to the **same chat timeline**, separated by a "📍 Exploring: {topic}" marker. The user can keep asking follow-ups about whatever node is currently active.
- **Persistent chat per (user, mindmap)**: on revisit, the entire conversation history is restored, including prior summaries and learnings. A previously-explored node is detected and the chat scrolls to the most recent occurrence rather than regenerating.
- **Quality-of-life UI**: scroll-wheel zoom, +/- zoom buttons, "expand all" button, "collapse all" button, fullscreen toggle, fit-view, mini-map.
- **Document-grounded**: every summary and answer cites `file.file_url` via the existing `LightRAGEngine` — no fabricated content.

### Non-Goals (v1)
- Cross-file mindmaps (one anchor file).
- Editing the mindmap (no add/rename/delete nodes).
- Shared/collaborative mindmaps (each user gets their own chat history; the tree itself is shared per file).
- Drag-and-drop layout (auto-layout only).
- Node bookmarking / tagging.
- Right-side NotebookLM-style detail panel.
- Streaming token-by-token responses (engine.aquery returns complete result).

---

## 2. Architecture Decisions & Tradeoffs

| Decision | Choice | Why | Tradeoff |
|---|---|---|---|
| Tree storage | **Single JSONB blob in `mindmaps.tree_data`** | The full tree is fetched in one shot, easier to render and version, no recursive-CTE acrobatics | Whole tree is rewritten on regeneration; fine for the size we expect (~50–150 nodes) |
| Per-user chat | **`mindmap_node_chats` thread keyed by (user_id, mindmap_id)** | One chat per (user, mindmap) — same shape as `chat_messages` for files | Doubles the chat persistence pattern; reusing `chat_messages` would couple file-chat and mindmap-chat semantics |
| Layout engine | **Dagre via `@xyflow/react`** | React Flow is the dominant React node-graph lib; dagre gives free top-down or left-right layouts | Radial layout would be prettier; punted to v2 |
| Tree generation | **Hybrid: KG-seeded + LLM-structured** | Use existing Neo4j entities (scoped via `file_filter`) as topic candidates, then hand them to an LLM with `instructor` to produce a hierarchical JSON tree | Pure-LLM generation hallucinates; pure-KG is structurally correct but reads like a thesaurus dump |
| Structured LLM output | **`instructor` library** (already added for group chat) | Pydantic-validated JSON; the tree schema is non-trivial and prompt-engineering it raw is brittle | None new — already a dep |
| Retrieval mode | **`mix` mode for both generation and per-node chat** | See §3 below — graph multi-hop is the natural fit | Slightly higher latency & cost than `naive` |
| Caching | **Persist tree once; regenerate only on explicit user action** | LLM cost is non-trivial; mindmap structure is stable for a given document | Need a "regenerate" button + clear UX when stale |
| Streaming | **No streaming** (matches existing chat) | `engine.aquery` returns complete results; consistent with file-chat and quiz | "Loading…" spinner instead of tokens flowing in |
| Frontend lib | **`@xyflow/react` + `dagre`** | Built-in pan/zoom/fullscreen/minimap, custom node support, MIT licence, ~30kb gz | Adds two deps |

---

## 3. Mode Recommendation — `mix` vs `naive`

**Use `mode="mix"` for both mindmap generation and per-node chat.** You're right that the mindmap is connected — the entire premise of a mindmap is "Topic A relates to Topic B relates to Topic C", which is exactly what the knowledge graph encodes. Using `naive` here would throw that information away.

**For initial tree generation**, the graph is load-bearing:
- Top-level topics correspond to high-degree entities in the file's subgraph.
- Sub-topics correspond to entities reachable in 1–2 hops.
- Edges in the KG (e.g. `is_a`, `part_of`, `relates_to`) inform parent-child relationships.

Using `mix` (with `traversal_hops=2`, `chunk_top_k=20`) gives the LLM both:
1. Rich entity-level context (which entities exist, how they're connected).
2. Chunk-level evidence (definitions, examples) needed to write good descriptions.

**For per-node chat**:
- The first message — initial summary of the node's topic — benefits enormously from `mix` because the topic is rarely a single chunk. It's spread across 5–15 chunks plus the entities that surround it.
- Follow-up questions can stay on `mix` for consistency. Latency is the only argument for naive, and the existing chat already uses `mix` for quiz/mindmap-style depth.

**Concrete settings** (env-tunable):

| Path | mode | top_k | chunk_top_k | traversal_hops | max_graph_neighbors |
|---|---|---|---|---|---|
| Tree generation (initial) | `mix` | 30 | 25 | 2 | 40 |
| Node initial summary | `mix` | 20 | 15 | 2 | 30 |
| Node follow-up Q&A | `mix` | 15 | 10 | 1 | 20 |

Follow-up uses `traversal_hops=1` and a smaller chunk window — most follow-ups are clarifications, not "re-explore the whole graph". This keeps latency under ~3s.

If cost ever becomes a real problem, the **only** path I'd downgrade to `naive` is follow-up Q&A — never tree generation, never initial summary.

---

## 4. New Dependencies

### Backend (`backend/requirements.txt`)
No new Python deps. `instructor==1.5.0` was already added for the group-chat feature; we reuse it. `engine.aquery` and Neo4j access are already in place.

### Frontend (`frontend/package.json`)
```json
"@xyflow/react": "^12.3.5",
"dagre": "^0.8.5",
"@types/dagre": "^0.7.52"
```

`react-markdown` and `remark-gfm` are already installed (added for group-chat) — reuse them for chat rendering.

### Docker / env
No new infra. Add three env vars to `.env.docker.example`:
```
MINDMAP_MAX_DEPTH=4
MINDMAP_MAX_CHILDREN_PER_NODE=6
MINDMAP_GENERATION_MODEL=gpt-4o-mini
```

---

## 5. Database Schema

A single Alembic migration: `alembic revision -m "add mindmap tables"`. Models live in `backend/app/models/mindmap.py`.

### 5.1 `mindmaps`

The cached tree, one per file.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `file_id` | int FK `files(id)` ON DELETE CASCADE, **UNIQUE** | One mindmap per file |
| `classroom_id` | int FK `classrooms(id)` ON DELETE CASCADE | Denormalized for membership checks |
| `root_topic` | varchar(120) | The well-defined topic, e.g. "Human Resource Management" |
| `root_description` | text | 1–2 sentence framing of the document's central thesis |
| `tree_data` | jsonb NOT NULL default `'{}'` | Full hierarchical tree — see §5.3 |
| `status` | enum `MindmapStatus(PENDING, GENERATING, READY, FAILED)` default PENDING | |
| `error_message` | varchar(500) nullable | Set when status=FAILED |
| `node_count` | int default 0 | Denormalized — for UI ("153 topics") and instrumentation |
| `generation_meta` | jsonb default `'{}'` | `{model, traversal_hops, max_neighbors, elapsed_s, tokens_in, tokens_out}` |
| `created_at` | timestamptz default now() | |
| `updated_at` | timestamptz default now() | Bumped on regeneration |

Index: `(file_id)` UNIQUE (already implied), `(classroom_id, status)`.

### 5.2 `mindmap_node_chats`

One row per message in a (user × mindmap) chat thread. Mirrors `chat_messages` but cleanly separated so file-chat and mindmap-chat don't share schema churn.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `mindmap_id` | int FK `mindmaps(id)` ON DELETE CASCADE | |
| `user_id` | int FK `users(id)` ON DELETE CASCADE | |
| `node_id` | varchar(64) nullable | Stable id of the active node when this message was created (see §5.3). NULL for messages predating any node click — rare. |
| `role` | enum `MindmapMessageRole(USER, ASSISTANT, MARKER)` | MARKER = the "📍 Exploring: X" header inserted on node click |
| `content` | text NOT NULL | For MARKER, content = the topic name |
| `message_metadata` | jsonb default `'{}'` | `{mode, sources, traversal_hops, elapsed_s, pending}` for assistant rows. **Attribute named `message_metadata` — not `metadata` — because `metadata` is reserved on SQLAlchemy's declarative `Base`. Matches the convention in `app/models/chat_message.py`.** |
| `created_at` | timestamptz default now() | |

Indexes: `(mindmap_id, user_id, created_at)` — primary fetch path. `(mindmap_id, user_id, node_id)` — for "scroll to last occurrence of this node".

### 5.3 `tree_data` JSONB shape

Stable schema, versioned for future migrations:

```json
{
  "version": 1,
  "root": {
    "id": "n_root",
    "topic": "Human Resource Management",
    "description": "Strategic and operational practices for managing people in organisations.",
    "depth": 0,
    "children": [
      {
        "id": "n_001",
        "topic": "Recruitment & Selection",
        "description": "Processes for sourcing, evaluating, and hiring candidates.",
        "depth": 1,
        "children": [
          {
            "id": "n_002",
            "topic": "Job Analysis",
            "description": "Identifying duties, responsibilities, and required qualifications for a role.",
            "depth": 2,
            "children": []
          }
        ]
      }
    ]
  }
}
```

Node `id` is stable across regenerations only when content matches; on regeneration we mint fresh ids. Chat messages keyed to old ids become "orphaned" (still visible in chat history with their original `node_id`, just no longer clickable in the new tree). UI handles this gracefully — orphaned MARKER messages render greyed-out.

### 5.4 Enums

```python
class MindmapStatus(enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"

class MindmapMessageRole(enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    MARKER = "marker"
```

---

## 6. Routes & API Surface

New router: `backend/app/routes/mindmap.py`, prefix `/mindmap`. Mounted in `app/main.py` next to the other routers.

### HTTP endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/mindmap/files/{file_id}/generate` | Returns 202 + the mindmap row. Idempotent: if status=READY returns it; if status=GENERATING returns the in-flight one; otherwise dispatches `generate_mindmap_task` as a `BackgroundTask`. Optional body `{force: true}` triggers regeneration. | classroom member |
| `GET` | `/mindmap/files/{file_id}` | Polls status; returns full mindmap row when READY. | classroom member |
| `DELETE` | `/mindmap/files/{file_id}` | Soft-clear the cached tree; next `generate` call rebuilds. Does **not** clear chat history. Owner of the classroom only — students see a frozen tree. | classroom owner |
| `POST` | `/mindmap/{mindmap_id}/nodes/{node_id}/explore` | **Click-a-node**. Inserts a MARKER row + a placeholder ASSISTANT row (with `message_metadata.pending=true`), dispatches `generate_node_summary_task` as a BackgroundTask. Returns the inserted row ids. Idempotent: if the node was already explored in this user's history, returns `{already_explored: true, last_message_id: int}` and does **not** generate a new summary. | classroom member |
| `GET` | `/mindmap/{mindmap_id}/chat?after_id=&limit=` | Paginated chat history for the current user. Reverse-chronological by default; `after_id` for "messages newer than X". | classroom member |
| `POST` | `/mindmap/{mindmap_id}/chat/ask` | Body `{content, active_node_id}`. Standard RAG chat, scoped to the file, but the question is silently augmented to mention the active node's topic. Returns the assistant message. | classroom member |
| `DELETE` | `/mindmap/{mindmap_id}/chat` | Clear the user's chat for this mindmap. Confirmation prompt on the client. | classroom member |

### Access control

Every endpoint resolves `file → folder → classroom` and asserts `current_user ∈ classroom.members` — same pattern as `_get_file_and_classroom` in `routes/chat.py`. Add a small helper `_get_mindmap_and_classroom(mindmap_id, ...)` to mirror it.

### Pre-condition

`/mindmap/files/{file_id}/generate` requires `file.processing_status == COMPLETED`. If not: return 409 with `detail: "File is still being processed; mindmap will be available once processing completes."`. The frontend disables the button + shows a tooltip when the file isn't ready.

---

## 7. Backend — Mindmap Generation Pipeline

Module: `backend/app/services/mindmap_service.py`. Owns the public API; calls into `mindmap_generator.py` for the heavy lifting and `mindmap_chat.py` for per-node chat.

### 7.1 `generate_mindmap_task(file_id, classroom_id, force=False)` — BackgroundTask

```python
async def generate_mindmap_task(file_id: int, classroom_id: int, force: bool = False):
    async with AsyncSessionLocal() as db:
        mindmap = await _load_or_create_mindmap_row(db, file_id, classroom_id, force=force)
        if mindmap.status == MindmapStatus.READY and not force:
            return

        mindmap.status = MindmapStatus.GENERATING
        await db.commit()

        try:
            file = await db.get(File, file_id)
            engine = await classroom_rag_service.get_engine(classroom_id)

            tree, meta = await build_mindmap_tree(engine, file)   # tree is a plain dict

            mindmap.tree_data = tree
            mindmap.root_topic = tree["root"]["topic"]
            mindmap.root_description = tree["root"]["description"]
            mindmap.node_count = _count_nodes(tree["root"])
            mindmap.generation_meta = meta
            mindmap.status = MindmapStatus.READY
            mindmap.error_message = None
        except Exception as e:
            logger.exception("mindmap generation failed for file_id=%s", file_id)
            mindmap.status = MindmapStatus.FAILED
            mindmap.error_message = str(e)[:500]
        finally:
            await db.commit()
```

Mirrors the quiz / flashcard background-task pattern exactly.

### 7.2 `build_mindmap_tree(engine, file)` — the heart of generation

Three-step funnel:

**Step 1 — Pull file-scoped graph context.**

```python
context_query = """
List the document's main topic, the major sub-topics it covers, and the
relationships between them. Include named entities, key concepts, and concrete
examples. Be exhaustive — this is the source material for a hierarchical mindmap.
"""

context_result = await engine.aquery(
    context_query,
    QueryParam(
        mode="mix",
        only_need_context=True,            # we want the raw retrieved context, not an answer
        chunk_top_k=25,
        top_k=30,
        traversal_hops=2,
        max_graph_neighbors=40,
        file_filter=file.file_url,
    ),
)
```

`only_need_context=True` skips the LLM answer step — we use the retrieved chunks + entities as input for our own structured call.

**Step 2 — Determine root topic.**

A short LLM call with `instructor`:

```python
class RootTopic(BaseModel):
    topic: str = Field(min_length=2, max_length=120, description="2–5 word topic")
    description: str = Field(min_length=20, max_length=400)

system = """
You name documents by their core topic. Return a 2–5 word topic that captures
the document's central subject — not the literal filename, not a chapter
heading. Then a 1–2 sentence description.

Example:
  filename: "Chapter1_HRM_With_Cartoons_Icons_and_Video.pptx"
  topic: "Human Resource Management"
  description: "Foundational practices for managing people in organisations,
                covering recruitment, training, and performance evaluation."
"""
prompt = f"FILENAME: {file.filename}\n\nDOCUMENT CONTEXT:\n{context_result[:6000]}"
root = await instructor_client.chat.completions.create(
    model=os.getenv("MINDMAP_GENERATION_MODEL", "gpt-4o-mini"),
    messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    response_model=RootTopic,
    temperature=0.2,
)
```

**Step 3 — Generate the hierarchical tree.**

The hardest part. We use `instructor` with a recursive Pydantic model and an explicit budget:

```python
class MindmapNode(BaseModel):
    topic: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=20, max_length=400)
    children: list["MindmapNode"] = Field(default_factory=list, max_length=6)

# Required: resolves the self-referencing "MindmapNode" forward reference
# before instructor introspects the schema. Without this, the recursive
# children field stays as a string and Pydantic raises at first validation.
MindmapNode.model_rebuild()

class MindmapTreePayload(BaseModel):
    children: list[MindmapNode] = Field(min_length=2, max_length=8)

system = f"""
You build hierarchical mindmaps from study material. Output a tree of topics
with the central topic "{root.topic}" as the implicit root.

Constraints:
- Root has 2-8 direct children (top-level branches).
- Each non-leaf has 2-{MAX_CHILDREN_PER_NODE} children.
- Maximum tree depth is {MAX_DEPTH} levels below the root.
- Each topic is a 2-5 word noun phrase, no verbs, no questions.
- Each description is 1-2 sentences, drawn strictly from the document.
- Do NOT invent topics absent from the document.
- Prefer breadth at level 1 (major sub-topics) and depth at deeper levels.
- Skip a level rather than padding with redundant siblings.

Output JSON only.
"""
tree_payload = await instructor_client.chat.completions.create(
    model=os.getenv("MINDMAP_GENERATION_MODEL", "gpt-4o-mini"),
    messages=[
        {"role": "system", "content": system},
        {"role": "user", "content": f"DOCUMENT CONTEXT:\n{context_result[:18000]}"},
    ],
    response_model=MindmapTreePayload,
    temperature=0.3,
    max_retries=2,
)
```

Then convert to the `tree_data` shape, minting stable ids:

```python
def assemble_tree(root: RootTopic, payload: MindmapTreePayload) -> Tree:
    counter = itertools.count(1)
    def assign_ids(node: MindmapNode, depth: int) -> dict:
        nid = f"n_{next(counter):04d}"
        return {
            "id": nid,
            "topic": node.topic.strip(),
            "description": node.description.strip(),
            "depth": depth,
            "children": [assign_ids(c, depth + 1) for c in node.children],
        }
    return {
        "version": 1,
        "root": {
            "id": "n_root",
            "topic": root.topic,
            "description": root.description,
            "depth": 0,
            "children": [assign_ids(c, 1) for c in payload.children],
        },
    }
```

### 7.3 Failure modes & retries

- `instructor` validation error → automatic retry up to 2× (built-in).
- Empty / one-child tree → raise `MindmapTooShallowError`, mark FAILED with a clear error message. UI offers "Try again".
- LLM timeout (>90s) → wrap each call in `asyncio.wait_for(..., timeout=90.0)`. On timeout: status=FAILED, `error_message="Generation timed out"`.
- File not COMPLETED → guarded at the route layer; if it slips through, raise `FilePreconditionError` early in the task.

### 7.4 Cost & observability

`generation_meta` records `tokens_in`, `tokens_out`, `elapsed_s`, `model`, `traversal_hops`, `max_neighbors`. Surface in logs:

```python
logger.info(
    "mindmap generated",
    extra={
        "file_id": file.id,
        "node_count": node_count,
        "root_topic": root.topic,
        "elapsed_s": round(elapsed, 2),
        "tokens_in": meta["tokens_in"],
        "tokens_out": meta["tokens_out"],
    },
)
```

---

## 8. Backend — Per-Node Chat

Module: `backend/app/services/mindmap_chat.py`.

### 8.1 `explore_node(mindmap_id, node_id, user_id)` — node click

```python
async def explore_node(db, mindmap_id, node_id, user_id) -> ExploreResult:
    mindmap = await _load_mindmap(db, mindmap_id)
    node = _find_node(mindmap.tree_data, node_id)   # walks the JSONB tree
    if not node:
        raise NodeNotFoundError(node_id)

    # Idempotency: has this user explored this node before?
    prior = await db.execute(
        select(MindmapNodeChat)
        .where(
            MindmapNodeChat.mindmap_id == mindmap_id,
            MindmapNodeChat.user_id == user_id,
            MindmapNodeChat.node_id == node_id,
            MindmapNodeChat.role == MindmapMessageRole.ASSISTANT,
        )
        .order_by(MindmapNodeChat.created_at.desc())
        .limit(1)
    )
    existing = prior.scalar_one_or_none()
    if existing:
        return ExploreResult(already_explored=True, last_message_id=existing.id)

    # First-time click → marker + placeholder, then schedule generation
    marker = MindmapNodeChat(
        mindmap_id=mindmap_id, user_id=user_id, node_id=node_id,
        role=MindmapMessageRole.MARKER, content=node["topic"],
    )
    placeholder = MindmapNodeChat(
        mindmap_id=mindmap_id, user_id=user_id, node_id=node_id,
        role=MindmapMessageRole.ASSISTANT, content="…",
        message_metadata={"pending": True},
    )
    db.add_all([marker, placeholder])
    await db.commit()

    return ExploreResult(
        already_explored=False,
        marker_id=marker.id,
        placeholder_id=placeholder.id,
    )
```

The route then schedules a BackgroundTask that fills the placeholder:

```python
async def generate_node_summary_task(mindmap_id, node_id, placeholder_id, file_id, classroom_id):
    async with AsyncSessionLocal() as db:
        mindmap = await _load_mindmap(db, mindmap_id)
        node = _find_node(mindmap.tree_data, node_id)
        file = await db.get(File, file_id)

        engine = await classroom_rag_service.get_engine(classroom_id)
        question = build_summary_question(node, mindmap.root_topic, file.filename)
        result = await engine.aquery(
            question,
            QueryParam(
                mode="mix",
                chunk_top_k=15,
                top_k=20,
                traversal_hops=2,
                max_graph_neighbors=30,
                file_filter=file.file_url,
                include_references=True,
            ),
        )

        placeholder = await db.get(MindmapNodeChat, placeholder_id)
        placeholder.content = result.content
        placeholder.message_metadata = {
            "mode": "mix",
            "traversal_hops": 2,
            "elapsed_s": elapsed,
            "sources": [s.file_path for s in (result.references or [])][:5],
            "pending": False,
        }
        await db.commit()
```

`build_summary_question` constructs:

```
You are explaining the topic "{node.topic}" in the context of the document
"{filename}", whose central thesis is "{mindmap.root_topic}".

Provide a focused summary that covers:
1. What "{node.topic}" is (definition / framing).
2. Key concepts, sub-points, or components.
3. A concrete example from the document if one is available.
4. How it connects to the surrounding topics in the document.

Use Markdown. Aim for 150-300 words. If the document does not say enough about
this topic to fill the structure above, say so honestly rather than padding.
```

### 8.2 `ask_in_thread(mindmap_id, user_id, content, active_node_id)` — follow-up Q&A

```python
async def ask_in_thread(db, mindmap_id, user_id, content, active_node_id):
    mindmap = await _load_mindmap(db, mindmap_id)
    file = await _file_from_mindmap(db, mindmap)

    # 1. Persist the user message
    user_msg = MindmapNodeChat(
        mindmap_id=mindmap_id, user_id=user_id, node_id=active_node_id,
        role=MindmapMessageRole.USER, content=content,
    )
    db.add(user_msg)
    await db.commit()

    # 2. Build conversation history scoped to (a) the recent thread and (b)
    #    the active node's prior assistant messages — so context stays sharp
    #    even after long meanders.
    history = await _build_history(db, mindmap_id, user_id, active_node_id, limit=10)

    # 3. Augment the question with the active topic
    node = _find_node(mindmap.tree_data, active_node_id) if active_node_id else None
    augmented = (
        f"[Currently exploring: {node['topic']}] {content}"
        if node else content
    )

    engine = await classroom_rag_service.get_engine(mindmap.classroom_id)
    result = await engine.aquery(
        augmented,
        QueryParam(
            mode="mix",
            chunk_top_k=10,
            top_k=15,
            traversal_hops=1,                  # follow-ups: shorter graph walk
            max_graph_neighbors=20,
            file_filter=file.file_url,
            conversation_history=history,
            include_references=True,
        ),
    )

    assistant_msg = MindmapNodeChat(
        mindmap_id=mindmap_id, user_id=user_id, node_id=active_node_id,
        role=MindmapMessageRole.ASSISTANT, content=result.content,
        message_metadata={"mode": "mix", "elapsed_s": elapsed, "sources": [...]},
    )
    db.add(assistant_msg)
    await db.commit()
    return assistant_msg
```

### 8.3 History builder

```python
async def _build_history(db, mindmap_id, user_id, active_node_id, limit=10):
    """
    Last `limit` non-marker messages globally + the most recent assistant
    message for `active_node_id` (anchors the topic). Deduped, time-ordered.
    """
    ...
```

The "anchor the topic" trick: even if the user has been chatting about another node for ten messages and now asks a question that refers back to the active node, the LLM still has that node's summary in its context window.

### 8.4 Concurrency

- Per-`(user, mindmap)` `asyncio.Semaphore(1)` keyed in an in-memory dict — prevents two near-simultaneous node clicks from interleaving placeholder rows. Acquired in the BackgroundTask, not in the request handler, so the HTTP response stays fast.
- Generation tasks use `AsyncSessionLocal()` — same pattern as `file_processor.py` and `quiz_service.py`.

---

## 9. Frontend Architecture

### 9.1 Routes & components

```
frontend/
├── app/classroom/[id]/folder/[folderId]/file/[fileId]/
│   └── mindmap/
│       └── page.tsx                       # the mindmap + chat shell
├── components/mindmap/
│   ├── mindmap-shell.tsx                  # top-level layout (mindmap | chat)
│   ├── mindmap-canvas.tsx                 # @xyflow/react wrapper
│   ├── mindmap-node.tsx                   # custom node renderer (topic, desc, expand caret)
│   ├── mindmap-controls.tsx               # zoom +/-, fit-view, expand-all, fullscreen
│   ├── mindmap-chat-panel.tsx             # chat shell (timeline + composer)
│   ├── mindmap-chat-message.tsx           # bubble (user / assistant / marker)
│   ├── mindmap-chat-composer.tsx          # input + send
│   ├── mindmap-status-overlay.tsx         # PENDING/GENERATING/FAILED states
│   └── use-mindmap-layout.ts              # dagre layout hook
└── hooks/
    ├── use-mindmap.ts                     # fetch tree + poll status
    └── use-mindmap-chat.ts                # fetch chat history + send messages
```

### 9.2 Entry point — folder view

In `frontend/components/classroom/files-section.tsx`, beneath each file card add a small button:

```tsx
<button
  onClick={(e) => {
    e.stopPropagation();
    router.push(`/classroom/${classroomId}/folder/${folderId}/file/${file.id}/mindmap`);
  }}
  disabled={file.processing_status !== "completed"}
  title={file.processing_status === "completed" ? "Open mindmap" : "File still processing"}
  className="mt-1 inline-flex items-center gap-1 rounded-full border border-violet-400/50 bg-violet-500/10 px-3 py-1.5 text-xs text-violet-300 hover:bg-violet-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
>
  <Network className="h-3.5 w-3.5" />
  Mindmap
</button>
```

Placement: under the existing "Delete" button on owner cards; underneath the filename for non-owners. Disabled (with tooltip) until `processing_status === "completed"`.

### 9.3 Mindmap page layout

```
┌──────────────────────────────────────────────────────────────┐
│  ClassroomHeader (existing)                                  │
├──────────────────────────────────────────────────────────────┤
│  [← Back to file]   "Mindmap: Human Resource Management"     │
├───────────────────────┬──────────────────────────────────────┤
│                       │                                      │
│                       │                                      │
│                       │                                      │
│   MindmapCanvas       │      MindmapChatPanel                │
│   (full width when    │      (hidden until first node click) │
│    no node selected)  │                                      │
│                       │                                      │
│                       │                                      │
│                       │                                      │
├───────────────────────┴──────────────────────────────────────┤
│  MindmapControls (zoom, fit, expand-all, fullscreen)         │
└──────────────────────────────────────────────────────────────┘
```

State-driven layout:
- `selectedNodeId === null` → mindmap takes 100% width, chat panel `display: none`.
- `selectedNodeId !== null` → mindmap shrinks to 30% (left), chat takes 70% (right). Smooth `framer-motion` transition (300ms ease).
- Fullscreen mode: a separate prop `isFullscreen` that lifts the shell to `position: fixed` over the whole viewport.

### 9.4 `MindmapCanvas` (React Flow + dagre)

```tsx
import { ReactFlow, Background, MiniMap, useNodesState, useEdgesState } from "@xyflow/react";
import dagre from "dagre";

function layoutDagre(nodes: Node[], edges: Edge[], direction: "LR" | "TB" = "LR") {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100 });
  nodes.forEach((n) => g.setNode(n.id, { width: 240, height: 80 }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const { x, y } = g.node(n.id);
    return { ...n, position: { x, y } };
  });
}
```

Node rendering: a custom node type registered as `topicNode`. Renders the topic, a chevron for expand/collapse, and a subtle highlight when explored. Default tree state: only the root and its direct children visible; deeper sub-trees collapsed.

**Two distinct click targets per node** — keep these strictly separate or the UX gets confusing fast:
- **Chevron click** (small target on the trailing edge of the node, only shown when the node has children): toggles that node's children visibility. Does **not** select the node, does **not** open or change the chat panel. Use this to explore tree structure without committing to a topic.
- **Body click** (the rest of the node — topic text + description): selects the node, opens the chat panel (sliding in from the right if not already open), and auto-expands one level of children if currently collapsed (so the user sees what's underneath the topic they just opened). Triggers `POST /explore`. If the chat is already open, it stays open and the timeline scrolls to the new MARKER.

Clicking the same body twice is a no-op for the tree; the second click hits the `already_explored` branch on the server and just scrolls the chat to the existing summary — no regeneration, no new MARKER row.

State:
```tsx
const [expanded, setExpanded] = useState<Set<string>>(new Set(["n_root"]));
const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
const visibleNodes = useMemo(() => deriveVisible(tree, expanded), [tree, expanded]);
```

`deriveVisible` walks the tree and includes a node iff its parent is expanded.

### 9.5 Controls

`MindmapControls` is a fixed bottom-centre toolbar:

| Button | Action |
|---|---|
| `−` | `reactFlowInstance.zoomOut()` |
| `+` | `reactFlowInstance.zoomIn()` |
| `⊕` (fit) | `reactFlowInstance.fitView({ padding: 0.2 })` |
| `⤢` (fullscreen) | toggles `document.documentElement.requestFullscreen()` + a CSS class |
| `Expand all` | `setExpanded(new Set(allNodeIds))` |
| `Collapse all` | `setExpanded(new Set(["n_root"]))` |
| `Regenerate` | confirm dialog → `POST /generate` with `{force: true}`; status overlay reappears |

Scroll-wheel zoom is already on by default via React Flow.

### 9.6 Status overlay

While `mindmap.status ∈ {PENDING, GENERATING}`:
```tsx
<MindmapStatusOverlay status={status} />
```
Shows the existing `LoadingOrb` with messages: "Analysing document…", "Building topic graph…", "Generating mindmap…". Polls `GET /mindmap/files/{file_id}` every 2s until READY or FAILED. On FAILED: error message + "Try again" button → `POST /generate` with `{force: true}`.

### 9.7 Chat panel

Two-pane shell (`MindmapChatPanel`):
- Top: timeline of `MindmapChatMessage` rows. MARKER rows render as a thin pill ("📍 Exploring: Job Analysis") with an anchor link. ASSISTANT rows render Markdown via `react-markdown` + `remark-gfm`. USER rows are right-aligned bubbles.
- Bottom: `MindmapChatComposer` — textarea + send button, disabled when no `selectedNodeId`.

On node click:
1. Optimistically scroll the timeline to bottom.
2. `POST /mindmap/{id}/nodes/{node_id}/explore`.
3. If `already_explored: true` → scroll to message id `last_message_id` and flash-highlight (like the group-chat reply scroll behaviour). Show a small toast: "You've explored this before — scrolled to your last conversation."
4. If `already_explored: false` → server returns marker + placeholder ids. Optimistically render both; the placeholder shows a "thinking" spinner.

**Pending-message polling.** While any rendered message has `message_metadata.pending === true`, the hook polls `GET /mindmap/{id}/chat?after_id={lastSeenId}` every **1.5 seconds** and merges new/updated rows into local state. Polling stops as soon as no rendered row is pending, OR the user navigates away (cleanup in the hook's `useEffect` return). Same mechanism handles `POST /chat/ask` follow-ups — the user message renders immediately, an assistant placeholder is rendered with `pending: true`, the poll resolves it. Mirrors the quiz/flashcard status-poll cadence; no WebSocket needed for v1.

### 9.8 Persistence on revisit

`useMindmapChat` does the following on mount:
1. `GET /mindmap/{id}/chat?limit=200` — full history for this user.
2. Render in time order.
3. The "active node" defaults to the most recently explored node (last MARKER's `node_id`), so follow-ups continue where the user left off. If none: composer is disabled until a node is clicked.

### 9.9 State management

No Redux/Zustand. `useMindmap(fileId)` and `useMindmapChat(mindmapId)` are local hooks. Cross-component state (selected node, expanded set) lives in the `mindmap-shell.tsx` and is passed down. Chat scroll-to-id is exposed via a ref forwarded from `MindmapChatPanel`.

---

## 10. Implementation Phases

Each phase is one Claude Code session. Phases 1–4 are backend; 5–7 are frontend. Phase 8 is polish.

### Phase 1 — Schema + models (½ day)

1. Add `Mindmap` and `MindmapNodeChat` models in `backend/app/models/mindmap.py`. Add the two enums.
2. Register imports in `backend/app/models/__init__.py`.
3. `alembic revision --autogenerate -m "add mindmap tables"`. Verify the autogen — check the UNIQUE constraint on `mindmaps.file_id` and the `(mindmap_id, user_id, created_at)` index.
4. `alembic upgrade head` and smoke-test inserts.
5. Extend cascade delete on `files.id` to cover the new tables (already covered by `ON DELETE CASCADE`).

**Acceptance**: `pytest -k "not llm and not integration"` green; manual insert/select.

### Phase 2 — Generation pipeline (1 day)

1. `backend/app/schemas/mindmap.py` — Pydantic in/out models for routes (`MindmapOut`, `MindmapNodeOut`, etc.).
2. `backend/app/services/mindmap_generator.py` — `build_mindmap_tree`, the two `instructor` calls, `assemble_tree`, `_count_nodes`.
3. `backend/app/services/mindmap_service.py` — `generate_mindmap_task`, `get_or_create_mindmap`, `_load_mindmap`, `_find_node`.
4. Tests: `test_mindmap_generator.py` — monkeypatch `engine.aquery` and the `instructor` client; assert tree shape, depth, max-children clamping.

**Acceptance**: a smoke run on a real `COMPLETED` file produces a sensible 50–150 node tree with a 2–5 word root. `node_count > 20`.

### Phase 3 — Routes + background task (½ day)

1. `backend/app/routes/mindmap.py` — `POST /generate`, `GET /files/{file_id}`, `DELETE /files/{file_id}` (owner only).
2. Mount in `app/main.py`.
3. Wire `BackgroundTasks.add_task(generate_mindmap_task, ...)` in the generate endpoint.
4. Tests: `test_mindmap_routes.py` — auth, idempotency, force regeneration, file-not-completed precondition.

**Acceptance**: `curl POST /mindmap/files/{id}/generate` → 202; subsequent `GET` returns READY within ~30s.

### Phase 4 — Per-node chat (1 day)

1. `backend/app/services/mindmap_chat.py` — `explore_node`, `generate_node_summary_task`, `ask_in_thread`, `_build_history`.
2. Routes: `POST /mindmap/{id}/nodes/{node_id}/explore`, `POST /chat/ask`, `GET /chat`, `DELETE /chat`.
3. Idempotency on explore (already-explored detection).
4. Tests: `test_mindmap_chat.py` — explore inserts marker+placeholder; second explore of same node returns `already_explored=True`; `ask_in_thread` includes the active topic in the question.

**Acceptance**: end-to-end shell — generate → explore root → see summary → ask follow-up → see grounded answer → explore another node → see new marker + summary appended → revisit first node → `already_explored=True`.

### Phase 5 — Frontend mindmap canvas (1.5 days)

1. `pnpm add @xyflow/react dagre @types/dagre`.
2. Route: `app/classroom/[id]/folder/[folderId]/file/[fileId]/mindmap/page.tsx`.
3. Components: `mindmap-shell.tsx`, `mindmap-canvas.tsx`, `mindmap-node.tsx`, `use-mindmap-layout.ts`.
4. `useMindmap(fileId)` hook: fetch + status polling.
5. Status overlay using existing `LoadingOrb`.
6. Manual test on two real files; verify zoom, expand/collapse, fit-view.

**Acceptance**: a generated mindmap renders, can be zoomed and panned, expand/collapse works at every level, fit-view recentres.

### Phase 6 — Frontend chat panel + interaction (1 day)

1. `mindmap-chat-panel.tsx`, `mindmap-chat-message.tsx`, `mindmap-chat-composer.tsx`.
2. `useMindmapChat(mindmapId)` hook: history fetch + ask + explore.
3. Layout transition: `framer-motion` width animation when `selectedNodeId` toggles.
4. Click handler on node body → `explore` → optimistic render → poll until placeholder filled.
5. `already_explored` path: scroll-to-id + toast.
6. Composer disabled until first node click.

**Acceptance**: clicking a node shows the chat panel sliding in, summary appears within ~5s, follow-up questions work, clicking a second node appends a new marker + summary to the same chat, revisit shows entire history.

### Phase 7 — Controls + folder-view button (½ day)

1. `mindmap-controls.tsx`: zoom +/-, fit-view, fullscreen toggle, expand-all / collapse-all, regenerate (with confirm).
2. Add the "Mindmap" button to `files-section.tsx` (disabled when not COMPLETED).
3. Test: every control behaves as expected; fullscreen survives node clicks.

**Acceptance**: §1 Goals all verifiably met in the browser.

### Phase 8 — Polish, tests, CLAUDE.md (½ day)

1. Error toasts on 4xx/5xx + network failure.
2. Mobile responsiveness — vertical-stack layout (`<sm`), chat below mindmap.
3. CLAUDE.md: add a "Mindmap system" subsection parallel to Quiz / Flashcard / Group-chat.
4. Verify `npx tsc --noEmit` and `pnpm lint` clean. `pytest` green.

**Total estimate**: ~5 working days for a single dev with Claude Code.

---

## 11. Edge Cases & Error Handling

| Case | Handling |
|---|---|
| File deleted while a mindmap exists | `ON DELETE CASCADE` removes the mindmap + chat. Live mindmap pages get a 404 on next poll → redirect to folder. |
| File re-uploaded (re-processed) | New file row → no mindmap. Owner regenerates explicitly. Old mindmap stays attached to the old file row until that row is deleted. |
| Tree generation produces 0 or 1 children | Mark FAILED with `error_message="Document too short for a useful mindmap"`. |
| Per-node summary times out (>90s) | Replace placeholder content with: "I had trouble summarising this topic. Click again to retry." `metadata.failed=true`. |
| User clicks a node mid-generation of another | Per-thread semaphore queues; UI shows the second placeholder with a "queued" hint. |
| Tree regenerated → old `node_id`s gone | Old MARKER messages render greyed-out, not clickable. A small banner at the top of the chat: "Mindmap was regenerated; some links may no longer match the current map." |
| Chat thread deleted (DELETE `/chat`) | Tree stays intact; on next node click, summaries regenerate fresh. |
| File still PENDING/PROCESSING | Mindmap button disabled, tooltip says "Available once processing completes". |
| RAG returns empty context for a leaf node | Summary message reads: "The document only briefly mentions {topic} — no detailed treatment is available. Try the parent topic for broader context." |
| User asks a question while no node is active | Composer is disabled in that state; can't happen unless someone bypasses the UI. |
| Concurrent regeneration requests | Idempotent at the service layer: if status=GENERATING, return the in-flight row instead of starting a new task. |

---

## 12. Observability

`logger = logging.getLogger("mindmap")` with structured `extra=`:

- Generation start / success / failure — `{file_id, classroom_id, node_count, elapsed_s, model, tokens_in, tokens_out}`.
- Node explore — `{mindmap_id, node_id, user_id, already_explored, elapsed_s}`.
- Follow-up Q&A — `{mindmap_id, user_id, active_node_id, history_size, elapsed_s}`.
- Failed validations — `{stage, error}`.

Counts via Prometheus: punted to v2; structured logs are enough for debugging in v1.

---

## 13. Security & Abuse

- Same access control as file chat: every endpoint resolves `file → folder → classroom` and asserts membership.
- DELETE mindmap restricted to classroom **owner** (regenerating costs LLM tokens; we don't want any member nuking it).
- Per-user rate limit on `POST /chat/ask` and `POST /explore`: reuse `realtime/rate_limit.py`'s sliding-window helper. 30 messages / 60s and 20 explores / 60s — generous enough for normal use, tight enough to stop a runaway loop.
- LLM prompt injection: the active node's topic and the user's content are wrapped in `<<<TOPIC>>>` / `<<<MESSAGE>>>` delimiters in the system prompt, with explicit instruction to treat them as untrusted input — same pattern as group-chat.

---

## 14. Open Questions (decide before Phase 1)

1. **Layout direction**: left-to-right (NotebookLM-style) or top-to-bottom? Recommend **LR** — better fit for wide-screen reading and matches the video.
2. **Per-classroom share vs per-user**: should every member of the classroom see the same mindmap tree? Recommend **yes — shared tree, per-user chat**. The tree is a representation of the document; the conversation is personal.
3. **Auto-generate on file upload** vs **on first click**? Recommend **on first click**. Saves money on files no one ever opens. Status polling makes the wait acceptable.
4. **Streaming**: do we want to plumb token-by-token streaming into the chat panel? Punt to v2 — `engine.aquery` doesn't stream and changing that is a separate epic.
5. **Mindmap regeneration after file edit**: out of scope — current code doesn't support file editing in place.

---

## 15. Files That Will Be Created

```
backend/
├── app/
│   ├── models/mindmap.py
│   ├── schemas/mindmap.py
│   ├── routes/mindmap.py
│   ├── services/
│   │   ├── mindmap_service.py
│   │   ├── mindmap_generator.py
│   │   └── mindmap_chat.py
│   └── tests/
│       ├── test_mindmap_models.py
│       ├── test_mindmap_generator.py
│       ├── test_mindmap_routes.py
│       └── test_mindmap_chat.py
└── migrations/versions/<hash>_add_mindmap_tables.py

frontend/
├── app/classroom/[id]/folder/[folderId]/file/[fileId]/mindmap/page.tsx
├── components/mindmap/
│   ├── mindmap-shell.tsx
│   ├── mindmap-canvas.tsx
│   ├── mindmap-node.tsx
│   ├── mindmap-controls.tsx
│   ├── mindmap-chat-panel.tsx
│   ├── mindmap-chat-message.tsx
│   ├── mindmap-chat-composer.tsx
│   ├── mindmap-status-overlay.tsx
│   └── use-mindmap-layout.ts
└── hooks/
    ├── use-mindmap.ts
    └── use-mindmap-chat.ts
```

## 16. Files That Will Be Modified

```
backend/
├── app/main.py                                  # mount mindmap router
└── app/models/__init__.py                       # import new models

frontend/
├── package.json                                 # +@xyflow/react, +dagre, +@types/dagre
└── components/classroom/files-section.tsx       # +Mindmap button per file card

.env.docker.example                              # +MINDMAP_MAX_DEPTH, +MINDMAP_MAX_CHILDREN_PER_NODE, +MINDMAP_GENERATION_MODEL
CLAUDE.md                                        # +"Mindmap system" subsection
```

---

## 17. Definition of Done (v1)

- [ ] Folder view shows a "Mindmap" button under every COMPLETED file.
- [ ] Clicking the button navigates to the mindmap page and triggers generation on first visit.
- [ ] Status overlay shows progress; tree appears within ~30s for a typical file.
- [ ] Root node is a 2–5 word topic (not the filename) and the description is 1–2 sentences grounded in the document.
- [ ] Tree has 2–4 levels, 2–6 children per non-leaf, and node count between 30 and 200.
- [ ] Clicking any node smoothly slides the chat panel in (mindmap shrinks to ~30%, chat takes ~70%); summary streams in within ~5s.
- [ ] Clicking a second node appends a new MARKER + summary to the same chat without clearing prior conversation.
- [ ] Follow-up questions in the chat are answered with the active node's topic in scope; switching the active node correctly switches scope.
- [ ] Revisiting the page restores the full chat history. Clicking a previously-explored node scrolls to that section instead of regenerating.
- [ ] Scroll-wheel zoom, +/- buttons, fit-view, expand-all, collapse-all, and fullscreen all work.
- [ ] Mindmap regenerates only when the owner explicitly requests it (DELETE + POST or the "Regenerate" button).
- [ ] All new endpoints are access-controlled via classroom membership.
- [ ] CLAUDE.md updated with a "Mindmap system" subsection parallel to the Quiz / Flashcard / Group-chat sections.
- [ ] Backend unit + integration tests green; frontend `tsc --noEmit` and `pnpm lint` green.

---

## 18. Quick Reference — `mix` vs `naive` decision summary

> **TL;DR — use `mix` everywhere in this feature.** The mindmap *is* the knowledge graph; throwing the graph away during retrieval would defeat the point. Tune `traversal_hops` and `chunk_top_k` per call to control cost: 2 hops for generation and node-summary, 1 hop for follow-ups.

| Path | mode | hops | chunk_top_k | rationale |
|---|---|---|---|---|
| Tree generation | `mix` | 2 | 25 | Tree shape = graph shape |
| Node summary | `mix` | 2 | 15 | Topic spans entities + chunks |
| Follow-up Q&A | `mix` | 1 | 10 | Snappier; topic already pinned |

If latency on follow-ups becomes painful in production, drop them to `naive` — but no other call.
