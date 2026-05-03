/**
 * MindmapCanvas — the React Flow canvas that renders the mindmap tree.
 *
 * Props:
 *   root        — MindmapNodeData (tree_data.root)
 *   activeNodeId — currently selected node (highlight ring)
 *   onNodeClick — fired when a non-root node is clicked
 */
"use client";

import { useCallback, useEffect, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { MindmapNodeData } from "@/api/mindmap";
import MindmapNodeComponent from "./mindmap-node";
import { buildFlow, type FlowNodeData } from "./layout";

const nodeTypes = { mindmapNode: MindmapNodeComponent };

interface MindmapCanvasProps {
  root: MindmapNodeData;
  activeNodeId: string | null;
  onNodeClick: (nodeId: string, label: string) => void;
}

export default function MindmapCanvas({
  root,
  activeNodeId,
  onNodeClick,
}: MindmapCanvasProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildFlow(root),
    [root]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowNodeData>>(
    []
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Inject onExplore callback + selected state into node data
  const injectCallbacks = useCallback(
    (raw: Node<FlowNodeData>[]): Node<FlowNodeData>[] =>
      raw.map((n) => ({
        ...n,
        selected: n.id === activeNodeId,
        data: {
          ...n.data,
          onExplore: (id: string) => onNodeClick(id, n.data.label),
        },
      })),
    [activeNodeId, onNodeClick]
  );

  // Re-layout when tree changes
  useEffect(() => {
    setNodes(injectCallbacks(initialNodes));
    setEdges(initialEdges);
  }, [initialNodes, initialEdges]); // eslint-disable-line react-hooks/exhaustive-deps

  // Update selected state without full re-layout
  useEffect(() => {
    setNodes((prev) => injectCallbacks(prev));
  }, [activeNodeId, injectCallbacks]);

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} color="rgba(139,92,246,0.12)" />
        <Controls
          showInteractive={false}
          className="!bg-background !border-border !shadow-sm"
        />
        <MiniMap
          nodeColor={(n) => {
            const depth = (n.data as FlowNodeData).depth;
            if (depth === 0) return "#7c3aed";
            if (depth === 1) return "#a78bfa";
            return "#c4b5fd";
          }}
          pannable
          zoomable
          className="!bg-background/80 !border-border !rounded-lg"
        />
      </ReactFlow>
    </div>
  );
}
