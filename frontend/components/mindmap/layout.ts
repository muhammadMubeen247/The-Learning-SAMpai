/**
 * Converts our tree_data JSONB structure into React Flow nodes + edges
 * with an automatic left-to-right dagre layout.
 */
import dagre from "dagre";
import type { Edge, Node } from "@xyflow/react";
import type { MindmapNodeData } from "@/api/mindmap";

export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 80;

export type FlowNodeData = {
  label: string;
  description: string;
  depth: number;
  isExplored?: boolean;
};

function flattenTree(
  node: MindmapNodeData,
  parentId: string | null,
  nodes: Node<FlowNodeData>[],
  edges: Edge[]
) {
  nodes.push({
    id: node.id,
    type: "mindmapNode",
    data: {
      label: node.topic,
      description: node.description,
      depth: node.depth,
    },
    position: { x: 0, y: 0 }, // dagre fills these in
  });

  if (parentId) {
    edges.push({
      id: `e-${parentId}-${node.id}`,
      source: parentId,
      target: node.id,
      type: "smoothstep",
    });
  }

  for (const child of node.children) {
    flattenTree(child, node.id, nodes, edges);
  }
}

export function buildFlow(root: MindmapNodeData): {
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
} {
  const nodes: Node<FlowNodeData>[] = [];
  const edges: Edge[] = [];

  flattenTree(root, null, nodes, edges);

  // ── Dagre layout (left-to-right) ─────────────────────────────────────
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 30, ranksep: 60 });

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
