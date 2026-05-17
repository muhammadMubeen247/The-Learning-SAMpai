# Refined Mindmap — NotebookLM-style Implementation Plan

## Context

The current mindmap renders **every node in `tree_data` at once** via a dagre LR layout — no expand/collapse, no chevrons, no per-node navigation. Users land on a wall of boxes instead of a discoverable, navigable tree. The backend generator does single-shot tree generation but its prompts under-use the depth budget, producing thin trees. The chat split-screen exists but is always-on and not toggleable; there is no full-screen mode.

Goal (validated with user): match the NotebookLM mindmap UX shown in the reference screenshots:

- Start collapsed — only the root visible; each node has a `>` chevron when it has children
- Click chevron → that node expands by one level; click again → collapses (with all descendants)
- Click node **body** → opens chat split-screen for that topic
- Right-side toolbar: expand-all / zoom-in / zoom-out
- Top-right full-screen toggle
- Tree must be deep and correct — keep expanding until each leaf is an atomic concept
- Must work dynamically for any uploaded file (verification target: `3-IntroductionToVirtualization.pptx`)

Decisions (confirmed):

- **Pre-generate** a deeper tree on the backend (single LLM call). Expansion is purely a frontend rendering concern → instant clicks, no per-click backend.
- **Single click on body = chat**; chevron handles tree navigation.
- **Force-regenerate** old mindmaps on next open (auto, one-time) via a `tree_data.version` bump.

## Architecture Overview

1. **Backend (small, surgical)**: bump depth/breadth budgets, rewrite generation prompt to demand atomic leaves, widen context window pulled into the prompt, set `tree_data.version = 2` so the frontend can detect stale trees and trigger regen.
2. **Frontend (the bulk of the work)**: rewrite `buildFlow` to walk only the expanded subtree; rebuild the node component with a chevron; add a custom toolbar (expand-all / zoom / full-screen); make the chat panel toggleable; auto-trigger regen when an old tree is loaded.
3. **No new HTTP endpoints, no DB migrations** — the `tree_data` JSONB is forwards-compatible (new `version` field is the only schema delta).

## Backend Changes

### `backend/app/services/mindmap_generator.py`

- Bump defaults: `MAX_DEPTH` 4 → **5**; `MAX_CHILDREN_PER_NODE` 6 → **7**.
- Rewrite the `tree_system` prompt (currently `mindmap_generator.py:226-238`) to demand real depth:
  - Add: *"Expand each branch until each leaf is a concrete, atomic concept — a specific named entity, a single definition, a single example, or a single mechanism. Categories are never leaves."*
  - Add: *"Aim for depth 3–4 on substantive branches. Use depth 1–2 only for trivially small branches."*
  - Add a one-shot example showing a depth-4 branch to anchor the model.
- Widen LLM input context: `raw_context[:18000]` → `raw_context[:32000]` (mindmap_generator.py:246). Today's `gpt-4o-mini` handles this comfortably.
- Bump generation `asyncio.wait_for` timeout 90s → **180s** (mindmap_generator.py:252) — deeper trees take longer.
- In `assemble_tree` (mindmap_generator.py:120–143), set `tree_data["version"] = 2` (was `1`). The frontend uses this as the regen trigger.
- Add `has_children: bool` to each node in `assemble_tree` output. The frontend currently infers this from `children.length`; making it explicit avoids ambiguity and lets future lazy modes mark "has children but not yet generated" cases.
- Log node count by depth (already counts total; extend `_count_nodes` to return a depth histogram for observability).

### `backend/app/services/mindmap_service.py`

- No code change to the background task itself.
- The auto-regen migration is triggered from the **frontend** (`use-mindmap.ts`) when it sees `version < 2`. Keeping the trigger client-side avoids a server-side "is this user already regenerating?" race and matches the simplest existing flow (frontend calls `generate(force=true)`).

### `backend/app/routes/mindmap.py`

- No change. The existing `POST /mindmap/files/{file_id}/generate?force=true` is exactly what the migration uses.

### `backend/app/models/mindmap.py`

- No change. `tree_data` is JSONB; `version` lives inside it.

## Frontend Changes

### `frontend/api/mindmap.ts`

- Extend `MindmapNodeData` type with `has_children?: boolean` (optional for backward compat — old payloads still work).
- Add `version?: number` to the `tree_data` type.

### `frontend/components/mindmap/layout.ts` — rewrite

- Change `buildFlow` signature: `buildFlow(root, expandedIds: Set<string>)`.
- `flattenTree` only recurses into a node's children if `expandedIds.has(node.id)` — children of collapsed nodes are simply not emitted.
- For every emitted node, set `data.hasChildren` (`node.has_children ?? node.children.length > 0`) and `data.isExpanded` (`expandedIds.has(node.id)`).
- Tune dagre params for the NotebookLM look: `nodesep: 24`, `ranksep: 100`.
- Export helper `collectAllNodeIds(root)` — used by "expand all". Export `collectExpandableIds(root)` — node IDs that have children (used by "expand all", excludes leaves).
- Export `collectDescendantIds(root, nodeId)` — used when collapsing a node, so all descendants are removed from `expandedIds` (otherwise their expansion state survives the parent collapse and resurrects on re-expand — usually fine, but cleaner to clear).

### `frontend/components/mindmap/mindmap-node.tsx` — rewrite

- Add a chevron button rendered to the right of the card (matches screenshots: small circle with `>` or `<`).
- Chevron is rendered **only when `data.hasChildren` is true**.
- Chevron `onClick` → calls `data.onToggleExpand(id)`. Stop propagation so it doesn't also fire body click.
- Body `onClick` → calls `data.onExplore(id, label)`. (Root node is excluded — clicking root opens chat about the document itself, or no-op; match existing behaviour: no-op.)
- Restyle to match screenshots:
  - Root: violet-600 filled pill
  - Branch (depth 1+): dark slate card with rounded-md border
  - Selected (currently exploring): violet ring + slight glow
  - Drop the existing `"Click to explore"` subtext — cleaner, screenshot-aligned
- Re-position the right-side `Handle` to align with the chevron — visually edges flow from the chevron, not from the card edge.

### `frontend/components/mindmap/mindmap-canvas.tsx` — refactor

- Add `expandedIds` state (`useState<Set<string>>`), initialised to `new Set(["n_root"])` (only the root is auto-expanded so users immediately see top-level branches).
- Memoise `buildFlow(root, expandedIds)` and re-derive on either change.
- Inject `onToggleExpand` and `onExplore` into every node's `data` via the existing data-callback pattern.
- `onToggleExpand(id)`:
  - If `id` is in `expandedIds` → drop it AND all descendant IDs (use `collectDescendantIds`)
  - Else → add it
  - Call `fitView({ padding: 0.2, duration: 400 })` from `useReactFlow` after layout settles
- Remove the React Flow built-in `<Controls>` — replaced by `MindmapToolbar` below.
- Surface `expandAll() / collapseAll() / zoomIn() / zoomOut() / fitView()` to the parent shell via either a forwarded ref or by accepting an `onAction` prop. Simpler: render `MindmapToolbar` *inside* the canvas component (it has the `ReactFlow` instance via `useReactFlow`).

### `frontend/components/mindmap/mindmap-toolbar.tsx` — NEW

- Floating vertical pill on the right edge of the canvas (matches screenshot button stack).
- Contains, top to bottom:
  - Expand-all / collapse-all toggle (icon: `ChevronsUpDown` from lucide). State derived: if any expandable node is collapsed → show "expand-all"; else "collapse-all".
  - Zoom in (`Plus`) → `reactFlow.zoomIn()`
  - Zoom out (`Minus`) → `reactFlow.zoomOut()`
- Styling: each button `rounded-full bg-slate-800/70 backdrop-blur w-9 h-9` with subtle hover. (No download button — explicitly out of scope.)

### `frontend/components/mindmap/mindmap-shell.tsx` — refactor

- New state: `isFullScreen: boolean` and `chatOpen: boolean` (default `false`).
- Wrap the outer container so that when `isFullScreen` → `fixed inset-0 z-50 bg-background` (covers entire viewport including app chrome).
- Top header bar (matches screenshots):
  - Left: `{rootTopic}` (large) + `Based on N source(s)` subtitle (placeholder text; we have one file per mindmap → `"Based on 1 source"`)
  - Right: full-screen toggle button (`Maximize2` / `Minimize2`); close button (`X`) — only rendered in full-screen
- Layout:
  - `chatOpen=false`: canvas takes 100% width
  - `chatOpen=true`, not fullscreen: canvas + chat side-by-side (current behaviour)
  - `chatOpen=true`, fullscreen: chat overlays on the right (`absolute right-0 top-header w-96 h-full`)
- `handleNodeClick(nodeId, label)` now also sets `chatOpen=true` in addition to firing explore — clicking a topic auto-opens chat. (Existing behaviour fires explore, but with the new toggle, we also need to open the panel.)
- Pass `onClose` to `MindmapChatPanel`; closing the chat sets `chatOpen=false` (does not clear the chat history).

### `frontend/components/mindmap/mindmap-chat-panel.tsx`

- Add a close `X` button in the header (right side). Calls `onClose` prop.
- Width bump: `w-80` → `w-96` for better reading width.
- No other functional changes — message rendering, polling, input handling stay.

### `frontend/hooks/use-mindmap.ts`

- On first successful fetch of a `READY` mindmap, if `mindmap.tree_data?.version` is `undefined` or `< 2`, auto-call `generate(true)` exactly once (guard with `useRef<boolean>` to avoid re-fire). User sees a brief "Building mindmap…" overlay during regen.
- This is the entire migration path — no server-side migration code, no backfill script.

### `frontend/app/classroom/[id]/.../page.tsx` (file page hosting MindmapShell)

- No structural change. Just confirms props passed to `MindmapShell` are correct; nothing to add.

## Critical Files (paths)

**Backend (edit):**
- `C:\D\FYP\The-Learning-SAMpai\backend\app\services\mindmap_generator.py`

**Backend (no edit, used for context only):**
- `backend\app\services\mindmap_service.py`, `backend\app\services\mindmap_chat.py`, `backend\app\routes\mindmap.py`, `backend\app\models\mindmap.py`

**Frontend (edit):**
- `C:\D\FYP\The-Learning-SAMpai\frontend\api\mindmap.ts`
- `C:\D\FYP\The-Learning-SAMpai\frontend\components\mindmap\layout.ts`
- `C:\D\FYP\The-Learning-SAMpai\frontend\components\mindmap\mindmap-node.tsx`
- `C:\D\FYP\The-Learning-SAMpai\frontend\components\mindmap\mindmap-canvas.tsx`
- `C:\D\FYP\The-Learning-SAMpai\frontend\components\mindmap\mindmap-shell.tsx`
- `C:\D\FYP\The-Learning-SAMpai\frontend\components\mindmap\mindmap-chat-panel.tsx`
- `C:\D\FYP\The-Learning-SAMpai\frontend\hooks\use-mindmap.ts`

**Frontend (new):**
- `C:\D\FYP\The-Learning-SAMpai\frontend\components\mindmap\mindmap-toolbar.tsx`

## Reused Utilities

- `engine.aquery(seed, QueryParam(mode="mix", only_need_context=True, ...))` — pattern at `mindmap_generator.py:170-181`. Keep unchanged.
- `_get_instructor_client()` singleton — `mindmap_generator.py:63-74`. Keep.
- `MindmapNode.model_rebuild()` — `mindmap_generator.py:103`. **Must remain** (recursive Pydantic).
- `_find_node(tree_data, node_id)` — `mindmap_service.py:33-47`. Still works (no schema change).
- `useMindmapChat` hook — already does explore + polling + ask; no changes needed.
- React Flow `useReactFlow().zoomIn/zoomOut/fitView` — used by the new toolbar.
- `dagre` LR layout — kept; only tuning sep params.

## Implementation Order

1. Backend prompt + depth + version bump (single file edit: `mindmap_generator.py`).
2. `api/mindmap.ts` — type updates.
3. `layout.ts` — `expandedIds`-aware `buildFlow` + helper exports.
4. `mindmap-node.tsx` — chevron + dual-click.
5. `mindmap-canvas.tsx` — expansion state, custom toolbar mount, fitView on toggle.
6. `mindmap-toolbar.tsx` — new file.
7. `mindmap-shell.tsx` — full-screen + chat-open state, header bar.
8. `mindmap-chat-panel.tsx` — close button.
9. `use-mindmap.ts` — one-shot auto-regen on stale version.
10. End-to-end test (see Verification).

## Verification

Run the stack:
```bash
docker compose up -d db neo4j chroma
cd backend && start_dev.bat
cd frontend && pnpm dev
```

Then in the browser at `http://localhost:3000`:

1. **Tree quality** — Upload `3-IntroductionToVirtualization.pptx` to a classroom folder. Wait for `COMPLETED`. Open Mindmap tab.
   - First open should auto-trigger regenerate (existing tree is `version 1`); see "Building mindmap…" overlay for ~30–60s.
   - Inspect resulting tree via DevTools: `tree_data.version === 2`; root has 4–7 children; at least 2 branches reach depth ≥ 3; leaves are atomic ("Type 1 Hypervisor", "Live Migration") not categorical ("Concepts", "Topics").
2. **Expand/collapse** — Initial render shows root + its direct children only. Click `>` on a depth-1 node → its children fan out smoothly (fitView animation). Click `<` → collapses; descendants also collapse.
3. **Expand all** — Click expand-all → entire tree visible, dagre repacks; click again → collapses to root.
4. **Zoom** — `+` / `-` zoom buttons fire and clamp at React Flow's min/max.
5. **Chat split-screen** — Click body of any non-root node. Chat panel slides in on right; explore call fires; "Generating summary…" placeholder appears; replaced with assistant text once ready.
6. **Close chat** — `X` on chat panel header → panel hides; canvas reclaims full width.
7. **Full-screen** — Top-right `Maximize2` → mindmap covers viewport (no app chrome). Click `X` → returns to inline tab view. Chat works in both modes.
8. **No-regen path** — Re-open the Mindmap tab in a fresh page load. `tree_data.version === 2` already → no auto-regen, instant render.
9. **Cross-file** — Upload an unrelated file (e.g. an HRM slide deck), regenerate, confirm tree shape is equally deep and topic-faithful. *(This validates the "works for any file" requirement.)*

## Out of Scope

- No new HTTP endpoints.
- No DB migrations (version lives in JSONB).
- No lazy / per-node LLM expansion (decided: pre-generate).
- No persisted expansion state across sessions (in-memory only; default = root expanded on open).
- No download/export button (visible in screenshots but explicitly excluded per user).
- No animation polish beyond React Flow's built-in fitView transition.
- No changes to chat plumbing, quiz, flashcards, group chat, or RAG layer.
