/**
 * MindmapCanvas — React Flow canvas with per-node expand/collapse.
 *
 * Architecture:
 *   MindmapCanvas  — owns expandedIds state + useNodesState/useEdgesState
 *     └─ ReactFlow
 *          └─ FlowContent  — uses useReactFlow() for fitView/zoom, re-builds
 *                            layout when expandedIds changes, renders toolbar
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Panel,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { MindmapNodeData } from "@/api/mindmap";
import MindmapNodeComponent from "./mindmap-node";
import MindmapToolbar from "./mindmap-toolbar";
import {
  buildFlow,
  collectExpandableIds,
  collectDescendantIds,
  type FlowNodeData,
} from "./layout";

const nodeTypes = { mindmapNode: MindmapNodeComponent };

// ── Inner component — has access to ReactFlow context ────────────────────────

interface FlowContentProps {
  root: MindmapNodeData;
  expandedIds: Set<string>;
  setExpandedIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  activeNodeId: string | null;
  onNodeClick: (nodeId: string, label: string) => void;
  setNodes: (
    update:
      | Node<FlowNodeData>[]
      | ((prev: Node<FlowNodeData>[]) => Node<FlowNodeData>[])
  ) => void;
  setEdges: (update: Edge[] | ((prev: Edge[]) => Edge[])) => void;
}

function FlowContent({
  root,
  expandedIds,
  setExpandedIds,
  activeNodeId,
  onNodeClick,
  setNodes,
  setEdges,
}: FlowContentProps) {
  const { fitView } = useReactFlow();

  const { nodes: flowNodes, edges: flowEdges } = useMemo(
    () => buildFlow(root, expandedIds),
    [root, expandedIds]
  );

  const onToggleExpand = useCallback(
    (id: string) => {
      setExpandedIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
          const descendants = collectDescendantIds(root, id);
          for (const did of descendants) next.delete(did);
        } else {
          next.add(id);
        }
        return next;
      });
    },
    [root, setExpandedIds]
  );

  const injectCallbacks = useCallback(
    (raw: Node<FlowNodeData>[]): Node<FlowNodeData>[] =>
      raw.map((n) => ({
        ...n,
        selected: n.id === activeNodeId,
        data: {
          ...n.data,
          onExplore: (id: string) => onNodeClick(id, n.data.label),
          onToggleExpand,
        },
      })),
    [activeNodeId, onNodeClick, onToggleExpand]
  );

  // Full re-layout when the visible node set changes
  useEffect(() => {
    setNodes(injectCallbacks(flowNodes));
    setEdges(flowEdges);
    // Allow React to commit then fit
    setTimeout(() => fitView({ padding: 0.2, duration: 400 }), 60);
  }, [flowNodes, flowEdges]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-apply callbacks when selection or handlers change (no re-layout)
  useEffect(() => {
    setNodes((prev) => injectCallbacks(prev));
  }, [activeNodeId, injectCallbacks]);

  const isFullyExpanded = useMemo(() => {
    const allIds = collectExpandableIds(root);
    return allIds.size > 0 && [...allIds].every((id) => expandedIds.has(id));
  }, [root, expandedIds]);

  const onExpandAll = useCallback(() => {
    setExpandedIds(collectExpandableIds(root));
    setTimeout(() => fitView({ padding: 0.1, duration: 600 }), 60);
  }, [root, setExpandedIds, fitView]);

  const onCollapseAll = useCallback(() => {
    setExpandedIds(new Set());
    setTimeout(() => fitView({ padding: 0.2, duration: 400 }), 60);
  }, [setExpandedIds, fitView]);

  return (
    <>
      <Background gap={16} size={1} color="rgba(96,165,250,0.1)" />
      <Panel position="bottom-right" style={{ marginBottom: 12, marginRight: 12 }}>
        <MindmapToolbar
          isFullyExpanded={isFullyExpanded}
          onExpandAll={onExpandAll}
          onCollapseAll={onCollapseAll}
        />
      </Panel>
    </>
  );
}

// ── Public canvas component ───────────────────────────────────────────────────

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
  // Root pre-expanded so users immediately see top-level branches
  const [expandedIds, setExpandedIds] = useState<Set<string>>(
    () => new Set(["n_root"])
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        minZoom={0.1}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "default",
          style: { stroke: "#60a5fa", strokeWidth: 1.5, opacity: 0.55 },
          animated: false,
        }}
      >
        <FlowContent
          root={root}
          expandedIds={expandedIds}
          setExpandedIds={setExpandedIds}
          activeNodeId={activeNodeId}
          onNodeClick={onNodeClick}
          setNodes={setNodes}
          setEdges={setEdges}
        />
      </ReactFlow>
    </div>
  );
}
