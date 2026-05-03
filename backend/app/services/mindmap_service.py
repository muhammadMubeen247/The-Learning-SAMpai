"""
Mindmap service — background task, CRUD helpers, and tree utilities.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.models.file import File
from app.models.folder import Folder
from app.models.classroom import Classroom
from app.models.mindmap import Mindmap, MindmapStatus
from app.services.classroom_rag import classroom_rag_service
from app.services.mindmap_generator import (
    MindmapTooShallowError,
    FilePreconditionError,
    _count_nodes,
    build_mindmap_tree,
)

logger = logging.getLogger("mindmap")


# ---------------------------------------------------------------------------
# Tree traversal helpers
# ---------------------------------------------------------------------------


def _find_node(tree_data: dict, node_id: str) -> Optional[dict]:
    """Walk the tree_data JSONB blob and return the node dict or None."""
    if not tree_data or "root" not in tree_data:
        return None

    def _walk(node: dict) -> Optional[dict]:
        if node.get("id") == node_id:
            return node
        for child in node.get("children", []):
            found = _walk(child)
            if found:
                return found
        return None

    return _walk(tree_data["root"])


def _all_node_ids(tree_data: dict) -> list[str]:
    """Return all node ids in the tree."""
    ids: list[str] = []

    def _walk(node: dict) -> None:
        ids.append(node["id"])
        for child in node.get("children", []):
            _walk(child)

    if tree_data and "root" in tree_data:
        _walk(tree_data["root"])
    return ids


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _load_or_create_mindmap_row(
    db: AsyncSession,
    file_id: int,
    classroom_id: int,
    force: bool = False,
) -> Mindmap:
    """Return existing Mindmap row or create a fresh PENDING one."""
    result = await db.execute(
        select(Mindmap).where(Mindmap.file_id == file_id)
    )
    mindmap = result.scalar_one_or_none()

    if mindmap is None:
        mindmap = Mindmap(
            file_id=file_id,
            classroom_id=classroom_id,
            status=MindmapStatus.PENDING,
            tree_data={},
            node_count=0,
        )
        db.add(mindmap)
        await db.flush()
    elif force:
        mindmap.status = MindmapStatus.PENDING
        mindmap.tree_data = {}
        mindmap.node_count = 0
        mindmap.root_topic = None
        mindmap.root_description = None
        mindmap.error_message = None

    return mindmap


async def get_mindmap_by_file(db: AsyncSession, file_id: int) -> Optional[Mindmap]:
    result = await db.execute(
        select(Mindmap).where(Mindmap.file_id == file_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def generate_mindmap_task(
    file_id: int,
    classroom_id: int,
    force: bool = False,
) -> None:
    """
    Background task: generate (or regenerate) the mindmap tree.
    Mirrors the quiz/flashcard background-task pattern.
    """
    async with AsyncSessionLocal() as db:
        mindmap = await _load_or_create_mindmap_row(
            db, file_id, classroom_id, force=force
        )

        # Fast-path: already READY and not forced
        if mindmap.status == MindmapStatus.READY and not force:
            return

        mindmap.status = MindmapStatus.GENERATING
        await db.commit()

        try:
            file = await db.get(File, file_id)
            if file is None:
                raise FilePreconditionError(f"File {file_id} not found")

            engine = await classroom_rag_service.get_engine(classroom_id)

            tree, meta = await build_mindmap_tree(engine, file)

            mindmap.tree_data = tree
            mindmap.root_topic = tree["root"]["topic"]
            mindmap.root_description = tree["root"]["description"]
            mindmap.node_count = _count_nodes(tree["root"])
            mindmap.generation_meta = meta
            mindmap.status = MindmapStatus.READY
            mindmap.error_message = None

        except MindmapTooShallowError as exc:
            logger.warning("mindmap too shallow for file_id=%s: %s", file_id, exc)
            mindmap.status = MindmapStatus.FAILED
            mindmap.error_message = str(exc)[:500]

        except Exception as exc:
            logger.exception("mindmap generation failed for file_id=%s", file_id)
            mindmap.status = MindmapStatus.FAILED
            mindmap.error_message = str(exc)[:500]

        finally:
            await db.commit()
