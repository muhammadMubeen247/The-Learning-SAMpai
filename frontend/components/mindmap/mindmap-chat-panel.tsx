"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2, Send, Trash2, X } from "lucide-react";
import type { ChatMessage } from "@/api/mindmap";

interface MindmapChatPanelProps {
  messages: ChatMessage[];
  isSending: boolean;
  activeNodeLabel: string | null;
  onAsk: (content: string) => void;
  onClear: () => void;
  onClose: () => void;
  inputValue: string;
  setInputValue: (v: string) => void;
}

function isPending(msg: ChatMessage): boolean {
  return msg.role === "assistant" && msg.message_metadata?.pending === true;
}

function isMarker(msg: ChatMessage): boolean {
  return msg.role === "marker";
}

const mdComponents = {
  p: ({ children }: { children: React.ReactNode }) => (
    <p className="mb-1 last:mb-0 leading-relaxed">{children}</p>
  ),
  ul: ({ children }: { children: React.ReactNode }) => (
    <ul className="list-disc pl-4 mb-1 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }: { children: React.ReactNode }) => (
    <ol className="list-decimal pl-4 mb-1 space-y-0.5">{children}</ol>
  ),
  li: ({ children }: { children: React.ReactNode }) => <li>{children}</li>,
  code: ({ children }: { children: React.ReactNode }) => (
    <code className="bg-black/10 dark:bg-white/10 px-1 py-0.5 rounded text-xs font-mono">
      {children}
    </code>
  ),
  strong: ({ children }: { children: React.ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
};

export default function MindmapChatPanel({
  messages,
  isSending,
  activeNodeLabel,
  onAsk,
  onClear,
  onClose,
  inputValue,
  setInputValue,
}: MindmapChatPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (inputValue.trim()) {
        onAsk(inputValue.trim());
        setInputValue("");
      }
    }
  };

  const handleSend = () => {
    if (inputValue.trim()) {
      onAsk(inputValue.trim());
      setInputValue("");
    }
  };

  const visibleMessages = messages.filter((m) => !isMarker(m));

  return (
    <div className="flex flex-col h-full bg-card/20 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/30 shrink-0">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground truncate">
            {activeNodeLabel ? activeNodeLabel : "Mind Map Chat"}
          </p>
          <p className="text-[11px] text-muted-foreground/60">
            {activeNodeLabel ? "Click a node to explore another" : "Click any node to explore it"}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {visibleMessages.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              title="Clear chat"
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            title="Close chat"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground/60 hover:text-foreground hover:bg-card/50 transition-colors cursor-pointer"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="flex flex-col gap-3 p-4">
          {visibleMessages.length === 0 && (
            <p className="text-xs text-muted-foreground/50 text-center mt-10 leading-relaxed">
              Click a node on the map to get an AI-generated summary, then ask
              follow-up questions here.
            </p>
          )}
          {visibleMessages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-border/30 p-3">
        <div className="flex items-end gap-2 bg-card/40 backdrop-blur-md border border-border/40 rounded-2xl p-2">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a follow-up question…"
            rows={1}
            disabled={isSending}
            className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed overflow-y-auto"
            style={{ maxHeight: 100, fieldSizing: "content" } as React.CSSProperties}
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={isSending || !inputValue.trim()}
            className="shrink-0 flex items-center justify-center w-8 h-8 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
          >
            {isSending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground/40 px-2">
          Enter · send · Shift+Enter · new line
        </p>
      </div>
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const pending = isPending(message);

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-chart-1/25 backdrop-blur-md border border-chart-1/20 px-3 py-2 text-sm text-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[92%] rounded-2xl rounded-bl-sm px-3 py-2 text-sm bg-card/60 backdrop-blur-sm border border-border/40 text-foreground ${
          pending ? "opacity-60" : ""
        }`}
      >
        {pending ? (
          <span className="flex items-center gap-2 text-muted-foreground text-xs">
            <Loader2 className="h-3 w-3 animate-spin" />
            Generating summary…
          </span>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as never}>
            {message.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}
