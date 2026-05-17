"use client";

import { ChevronsUpDown, Minimize2, Minus, Plus } from "lucide-react";
import { useReactFlow } from "@xyflow/react";

interface MindmapToolbarProps {
  isFullyExpanded: boolean;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}

export default function MindmapToolbar({
  isFullyExpanded,
  onExpandAll,
  onCollapseAll,
}: MindmapToolbarProps) {
  const { zoomIn, zoomOut } = useReactFlow();

  return (
    <div className="flex flex-col gap-1.5">
      <ToolButton
        onClick={isFullyExpanded ? onCollapseAll : onExpandAll}
        title={isFullyExpanded ? "Collapse all" : "Expand all"}
      >
        {isFullyExpanded ? (
          <Minimize2 className="h-3.5 w-3.5" />
        ) : (
          <ChevronsUpDown className="h-3.5 w-3.5" />
        )}
      </ToolButton>
      <ToolButton onClick={() => zoomIn({ duration: 200 })} title="Zoom in">
        <Plus className="h-3.5 w-3.5" />
      </ToolButton>
      <ToolButton onClick={() => zoomOut({ duration: 200 })} title="Zoom out">
        <Minus className="h-3.5 w-3.5" />
      </ToolButton>
    </div>
  );
}

function ToolButton({
  children,
  onClick,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="w-9 h-9 rounded-full flex items-center justify-center bg-card/80 backdrop-blur-md border border-border/50 text-muted-foreground shadow-md hover:bg-card/95 hover:border-chart-1/40 hover:text-chart-1 transition-all cursor-pointer"
    >
      {children}
    </button>
  );
}
