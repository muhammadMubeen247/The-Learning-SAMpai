/**
 * MindmapShell — the full-page mindmap experience.
 *
 * Layout:
 *   [canvas (flex-1)] | [chat panel (w-80)]
 *
 * States:
 *   idle / pending / generating → status overlay with spinner
 *   failed                      → error overlay with retry button
 *   ready                       → split canvas + chat
 */
"use client";

import { useState } from "react";
import { Loader2, RefreshCw, AlertTriangle, Map } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMindmap } from "@/hooks/use-mindmap";
import { useMindmapChat } from "@/hooks/use-mindmap-chat";
import MindmapCanvas from "./mindmap-canvas";
import MindmapChatPanel from "./mindmap-chat-panel";

interface MindmapShellProps {
  fileId: number;
  classroomId: number;
  fileName: string;
}

export default function MindmapShell({
  fileId,
  classroomId,
  fileName,
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

  const handleNodeClick = async (nodeId: string, label: string) => {
    if (!mindmap) return;
    setActiveTopic(label);
    await chat.exploreNode(nodeId);
  };

  const handleAsk = async (content: string) => {
    await chat.ask(content);
  };

  // ── Status overlays ─────────────────────────────────────────────────────

  if (status === "idle" && !isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-4">
        <Map className="h-12 w-12 text-violet-500 opacity-70" />
        <div>
          <p className="text-lg font-semibold">Generate Mindmap</p>
          <p className="text-sm text-muted-foreground mt-1 max-w-xs">
            SAMpai will build an interactive mindmap for <strong>{fileName}</strong> using the
            knowledge graph.
          </p>
        </div>
        <Button onClick={() => generate()} className="mt-2">
          Generate Mindmap
        </Button>
      </div>
    );
  }

  if (status === "pending" || status === "generating" || isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
        <Loader2 className="h-10 w-10 text-violet-500 animate-spin" />
        <p className="text-sm font-medium text-muted-foreground">
          {status === "generating"
            ? "Building mindmap…"
            : "Starting generation…"}
        </p>
        <p className="text-xs text-muted-foreground">
          This usually takes 15–30 seconds.
        </p>
      </div>
    );
  }

  if (status === "failed" || error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-4">
        <AlertTriangle className="h-10 w-10 text-destructive opacity-70" />
        <p className="text-sm font-semibold">Mindmap generation failed</p>
        <p className="text-xs text-muted-foreground max-w-xs">
          {mindmap?.error_message ?? error ?? "An unknown error occurred."}
        </p>
        <Button variant="outline" onClick={() => generate(true)} className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      </div>
    );
  }

  // ── Ready: render canvas + chat ─────────────────────────────────────────

  const root = mindmap?.tree_data?.root;
  if (!root) return null;

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Canvas */}
      <div className="flex-1 min-w-0 h-full">
        <MindmapCanvas
          root={root}
          activeNodeId={chat.activeNodeId}
          onNodeClick={handleNodeClick}
        />
      </div>

      {/* Chat panel */}
      <div className="w-80 shrink-0 h-full">
        <MindmapChatPanel
          messages={chat.messages}
          isSending={chat.isSending}
          activeNodeLabel={activeTopic}
          onAsk={handleAsk}
          onClear={chat.clearChat}
          inputValue={chatInput}
          setInputValue={setChatInput}
        />
      </div>
    </div>
  );
}
