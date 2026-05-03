/**
 * Custom React Flow node for mindmap topics.
 *
 * - Root node (depth 0): larger, accent-colored pill
 * - Branch nodes (depth 1-2): medium rounded card
 * - Leaf nodes (depth 3+): compact pill
 *
 * Click fires onExplore via node data callback.
 */
"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { cn } from "@/lib/utils";
import type { FlowNodeData } from "./layout";

const depthStyles: Record<number, string> = {
  0: "bg-violet-600 text-white border-violet-700 shadow-lg min-w-[180px]",
  1: "bg-violet-100 dark:bg-violet-950 text-violet-900 dark:text-violet-100 border-violet-300 dark:border-violet-700",
  2: "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100 border-slate-300 dark:border-slate-600",
};

function getDepthStyle(depth: number): string {
  return (
    depthStyles[depth] ??
    "bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700"
  );
}

interface ExtendedNodeData extends FlowNodeData {
  onExplore?: (nodeId: string) => void;
}

const MindmapNode = memo(function MindmapNode({
  id,
  data,
  selected,
}: NodeProps) {
  const nodeData = data as unknown as ExtendedNodeData;
  const isRoot = nodeData.depth === 0;

  const handleClick = () => {
    if (!isRoot && nodeData.onExplore) {
      nodeData.onExplore(id);
    }
  };

  return (
    <div
      onClick={handleClick}
      className={cn(
        "rounded-xl border px-3 py-2 cursor-pointer select-none transition-all duration-150",
        "hover:shadow-md hover:scale-[1.02]",
        getDepthStyle(nodeData.depth),
        selected && "ring-2 ring-violet-500 ring-offset-1",
        isRoot && "cursor-default"
      )}
      style={{ width: 200, minHeight: 60 }}
    >
      {/* Target handle (incoming edge) */}
      {!isRoot && (
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-violet-400 !w-2 !h-2 !border-0"
        />
      )}

      <div className="flex flex-col gap-0.5">
        <span
          className={cn(
            "font-semibold leading-tight",
            isRoot ? "text-sm" : "text-xs"
          )}
        >
          {nodeData.label}
        </span>
        {nodeData.depth <= 1 && (
          <span
            className={cn(
              "text-[10px] leading-tight line-clamp-2 opacity-70",
              isRoot ? "text-white/80" : ""
            )}
          >
            {nodeData.description}
          </span>
        )}
        {!isRoot && (
          <span className="text-[9px] opacity-50 mt-0.5">Click to explore</span>
        )}
      </div>

      {/* Source handle (outgoing edges) */}
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-violet-400 !w-2 !h-2 !border-0"
      />
    </div>
  );
});

export default MindmapNode;
