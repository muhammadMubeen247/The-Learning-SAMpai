"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { ChevronRight, ChevronLeft } from "lucide-react";
import type { FlowNodeData } from "./layout";

function getCardStyle(depth: number, selected: boolean): string {
  const selectedRing = selected ? " ring-2 ring-chart-1/50 ring-offset-1 ring-offset-transparent" : "";

  if (depth === 0) {
    return `bg-chart-1/90 text-white border-chart-1/60 shadow-lg backdrop-blur-sm${selectedRing}`;
  }
  if (depth === 1) {
    return `bg-card/85 backdrop-blur-md border-border/60 shadow-md text-foreground${selectedRing}`;
  }
  return `bg-card/70 backdrop-blur-sm border-border/40 shadow-sm text-foreground${selectedRing}`;
}

interface ExtendedNodeData extends FlowNodeData {
  onExplore?: (nodeId: string) => void;
  onToggleExpand?: (nodeId: string) => void;
}

const MindmapNode = memo(function MindmapNode({ id, data, selected }: NodeProps) {
  const nodeData = data as unknown as ExtendedNodeData;
  const { label, description, depth, hasChildren, isExpanded } = nodeData;
  const isRoot = depth === 0;

  const handleBodyClick = () => {
    if (!isRoot && nodeData.onExplore) {
      nodeData.onExplore(id);
    }
  };

  const handleChevronClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (nodeData.onToggleExpand) {
      nodeData.onToggleExpand(id);
    }
  };

  return (
    <div className="flex items-center gap-1.5" style={{ width: 210, minHeight: 72 }}>
      {/* Incoming edge handle */}
      {!isRoot && (
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-blue-400 !w-2 !h-2 !border-0 !opacity-70"
        />
      )}

      {/* Card body */}
      <div
        onClick={handleBodyClick}
        className={`flex-1 min-w-0 rounded-xl border px-3 py-2.5 select-none transition-all duration-150 ${
          !isRoot ? "cursor-pointer hover:brightness-105 hover:shadow-md" : "cursor-default"
        } ${getCardStyle(depth, !!selected)}`}
        style={{ minHeight: 60 }}
      >
        <span
          className={`font-semibold leading-snug block ${
            isRoot ? "text-sm" : depth === 1 ? "text-xs" : "text-[11px]"
          }`}
        >
          {label}
        </span>
        {depth <= 1 && description && (
          <span
            className={`leading-snug line-clamp-2 block mt-0.5 ${
              isRoot
                ? "text-[10px] text-white/70"
                : "text-[10px] text-muted-foreground/60"
            }`}
          >
            {description}
          </span>
        )}
      </div>

      {/* Expand/collapse chevron */}
      {hasChildren ? (
        <button
          onClick={handleChevronClick}
          className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-card/70 backdrop-blur-sm border border-border/50 text-muted-foreground hover:bg-card/90 hover:border-chart-1/40 hover:text-chart-1 transition-all"
          title={isExpanded ? "Collapse" : "Expand"}
        >
          {isExpanded ? (
            <ChevronLeft className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>
      ) : (
        <div className="shrink-0 w-7" />
      )}

      {/* Outgoing edge handle */}
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-blue-400 !w-2 !h-2 !border-0 !opacity-70"
        style={{ right: 0 }}
      />
    </div>
  );
});

export default MindmapNode;
