/**
 * Converts our tree_data JSONB structure into React Flow nodes + edges,
 * rendering only nodes whose parent is in the expandedIds set.
 */
import dagre from "dagre";
import type { Edge, Node } from "@xyflow/react";
import type { MindmapNodeData } from "@/api/mindmap";

export const NODE_WIDTH = 210;
export const NODE_HEIGHT = 72;

export type FlowNodeData = {
  label: string;
  description: string;
  depth: number;
  hasChildren: boolean;
  isExpanded: boolean;
  onExplore?: (nodeId: string) => void;
  onToggleExpand?: (nodeId: string) => void;
};

function flattenTree(
  node: MindmapNodeData,
  parentId: string | null,
  expandedIds: Set<string>,
  nodes: Node<FlowNodeData>[],
  edges: Edge[]
) {
  const hasChildren = node.has_children ?? node.children.length > 0;
  const isExpanded = expandedIds.has(node.id);

  nodes.push({
    id: node.id,
    type: "mindmapNode",
    data: {
      label: node.topic,
      description: node.description,
      depth: node.depth,
      hasChildren,
      isExpanded,
    },
    position: { x: 0, y: 0 },
  });

  if (parentId) {
    edges.push({
      id: `e-${parentId}-${node.id}`,
      source: parentId,
      target: node.id,
    });
  }

  if (isExpanded) {
    for (const child of node.children) {
      flattenTree(child, node.id, expandedIds, nodes, edges);
    }
  }
}

export function buildFlow(
  root: MindmapNodeData,
  expandedIds: Set<string>
): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
  const nodes: Node<FlowNodeData>[] = [];
  const edges: Edge[] = [];

  flattenTree(root, null, expandedIds, nodes, edges);

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 100 });

  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  const layoutedNodes = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

// ── Tree-walking helpers ──────────────────────────────────────────────────────

/** All node IDs that have children (non-leaves) — used for expand-all. */
export function collectExpandableIds(
  node: MindmapNodeData,
  result = new Set<string>()
): Set<string> {
  const hasChildren = node.has_children ?? node.children.length > 0;
  if (hasChildren) {
    result.add(node.id);
    for (const child of node.children) {
      collectExpandableIds(child, result);
    }
  }
  return result;
}

/** IDs of every descendant of the given node (not including the node itself). */
export function collectDescendantIds(
  root: MindmapNodeData,
  targetId: string
): Set<string> {
  function findNode(node: MindmapNodeData): MindmapNodeData | null {
    if (node.id === targetId) return node;
    for (const child of node.children) {
      const found = findNode(child);
      if (found) return found;
    }
    return null;
  }

  const target = findNode(root);
  if (!target) return new Set();

  const result = new Set<string>();
  function collect(node: MindmapNodeData) {
    for (const child of node.children) {
      result.add(child.id);
      collect(child);
    }
  }
  collect(target);
  return result;
}
