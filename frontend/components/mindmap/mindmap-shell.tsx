"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw, AlertTriangle, Map } from "lucide-react";
import { useMindmap } from "@/hooks/use-mindmap";
import { useMindmapChat } from "@/hooks/use-mindmap-chat";
import MindmapCanvas, { type MindmapCanvasHandle } from "./mindmap-canvas";
import MindmapChatPanel from "./mindmap-chat-panel";

interface MindmapShellProps {
  fileId: number;
  classroomId: number;
  fileName: string;
  /** True when the Mindmap tab is the active tab — triggers re-fit after display:none. */
  isActive?: boolean;
}

const MIN_CANVAS_PCT = 25;
const MAX_CANVAS_PCT = 75;

export default function MindmapShell({
  fileId,
  classroomId,
  fileName,
  isActive,
}: MindmapShellProps) {
  const { mindmap, status, isLoading, error, generate } = useMindmap({
    fileId,
    autoGenerate: false,
  });

  const chat = useMindmapChat({
    mindmapId: mindmap?.id ?? null,
    fileId,
    classroomId,
  });

  const [chatInput, setChatInput] = useState("");
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [splitPct, setSplitPct] = useState(50);
  const [isDragging, setIsDragging] = useState(false);

  // Animated re-fit counter for non-drag events (tab visibility, chat toggle)
  const [fitCounter, setFitCounter] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<MindmapCanvasHandle>(null);
  const fitRafRef = useRef<number>(0);         // RAF id for real-time drag fit
  const isFirstChatEffect = useRef(true);

  // ── Re-fit when the tab becomes visible (fixes display:none init issue) ──────
  useEffect(() => {
    if (!isActive) return;
    const timer = setTimeout(() => setFitCounter((c) => c + 1), 200);
    return () => clearTimeout(timer);
  }, [isActive]);

  // ── Animated re-fit when chat panel opens or closes (skip mount) ─────────────
  useEffect(() => {
    if (isFirstChatEffect.current) {
      isFirstChatEffect.current = false;
      return;
    }
    const timer = setTimeout(() => setFitCounter((c) => c + 1), 100);
    return () => clearTimeout(timer);
  }, [chatOpen]);

  // ── Drag-to-resize ───────────────────────────────────────────────────────────
  const startDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    if (!isDragging) return;

    const onMove = (e: MouseEvent) => {
      if (!containerRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setSplitPct(Math.max(MIN_CANVAS_PCT, Math.min(MAX_CANVAS_PCT, pct)));

      // Call fitView on the next animation frame — after React has committed the
      // new width to the DOM — so the canvas is always visible during drag.
      cancelAnimationFrame(fitRafRef.current);
      fitRafRef.current = requestAnimationFrame(() => {
        canvasRef.current?.fitView();
      });
    };

    const onUp = () => {
      setIsDragging(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      cancelAnimationFrame(fitRafRef.current);
      // One final animated re-fit to cleanly settle after drag ends
      setFitCounter((c) => c + 1);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      cancelAnimationFrame(fitRafRef.current);
    };
  }, [isDragging]);

  const handleNodeClick = async (nodeId: string, label: string) => {
    if (!mindmap) return;
    setActiveTopic(label);
    setChatOpen(true);
    await chat.exploreNode(nodeId);
  };

  const handleAsk = async (content: string) => {
    await chat.ask(content);
  };

  // ── Status overlays ──────────────────────────────────────────────────────────

  if (status === "idle" && !isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center px-6 h-full">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl border border-border/40 bg-card/40 backdrop-blur-sm">
          <Map className="h-8 w-8 text-chart-1" />
        </div>
        <div className="space-y-2">
          <p className="text-base font-semibold text-foreground">Mind Map</p>
          <p className="text-xs text-muted-foreground/70 max-w-xs">
            SAMpai will build an interactive mind map for{" "}
            <span className="text-foreground/80 font-medium">{fileName}</span> using
            the knowledge graph.
          </p>
        </div>
        <button
          onClick={() => generate()}
          className="px-6 py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer"
        >
          Generate Mind Map
        </button>
      </div>
    );
  }

  if (status === "pending" || status === "generating" || isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center h-full">
        <Loader2 className="h-8 w-8 text-chart-1 animate-spin" />
        <p className="text-sm font-medium text-muted-foreground">
          {status === "generating" ? "Building mind map…" : "Starting generation…"}
        </p>
        <p className="text-xs text-muted-foreground/50">
          This usually takes 20–60 seconds.
        </p>
      </div>
    );
  }

  if (status === "failed" || error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6 h-full">
        <AlertTriangle className="h-8 w-8 text-destructive/70" />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-foreground">Generation failed</p>
          <p className="text-xs text-muted-foreground/70 max-w-xs">
            {mindmap?.error_message ?? error ?? "An unknown error occurred."}
          </p>
        </div>
        <button
          onClick={() => generate(true)}
          className="flex items-center gap-2 px-5 py-2 rounded-xl border border-border/50 bg-card/50 hover:bg-card/70 text-sm text-foreground transition-colors cursor-pointer"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    );
  }

  // ── Ready ────────────────────────────────────────────────────────────────────

  const root = mindmap?.tree_data?.root;
  if (!root) return null;

  return (
    <div ref={containerRef} className="flex flex-1 min-h-0 overflow-hidden h-full w-full">
      {/* Canvas */}
      <div
        className="h-full min-w-0"
        style={{ width: chatOpen ? `${splitPct}%` : "100%" }}
      >
        <MindmapCanvas
          ref={canvasRef}
          root={root}
          activeNodeId={chat.activeNodeId}
          onNodeClick={handleNodeClick}
          fitTrigger={fitCounter}
        />
      </div>

      {/* Drag handle */}
      {chatOpen && (
        <div
          onMouseDown={startDrag}
          className="w-[5px] h-full flex-none cursor-col-resize relative group select-none z-10"
        >
          <div className="absolute inset-0 bg-border/30 group-hover:bg-chart-1/40 transition-colors duration-150" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-[3px] pointer-events-none">
            {[0, 1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="w-[3px] h-[3px] rounded-full bg-muted-foreground/30 group-hover:bg-chart-1/70 transition-colors"
              />
            ))}
          </div>
        </div>
      )}

      {/* Chat panel */}
      {chatOpen && (
        <div
          className="h-full min-w-0 flex-none border-l border-border/30"
          style={{ width: `${100 - splitPct}%` }}
        >
          <MindmapChatPanel
            messages={chat.messages}
            isSending={chat.isSending}
            activeNodeLabel={activeTopic}
            onAsk={handleAsk}
            onClear={chat.clearChat}
            onClose={() => setChatOpen(false)}
            inputValue={chatInput}
            setInputValue={setChatInput}
          />
        </div>
      )}
    </div>
  );
}
