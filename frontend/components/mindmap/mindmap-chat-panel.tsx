/**
 * MindmapChatPanel — the right-hand chat sidebar for the mindmap page.
 *
 * Features:
 * - Shows per-node summary when a node is clicked (via MARKER + ASSISTANT rows)
 * - Shows conversational follow-up messages
 * - Polls until all pending messages are resolved
 * - "Ask a question..." input at the bottom
 */
"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2, Send, Trash2 } from "lucide-react";

import type { ChatMessage } from "@/api/mindmap";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface MindmapChatPanelProps {
  messages: ChatMessage[];
  isSending: boolean;
  activeNodeLabel: string | null;
  onAsk: (content: string) => void;
  onClear: () => void;
  inputValue: string;
  setInputValue: (v: string) => void;
}

function isPending(msg: ChatMessage): boolean {
  return msg.role === "assistant" && msg.message_metadata?.pending === true;
}

function isMarker(msg: ChatMessage): boolean {
  return msg.role === "marker";
}

export default function MindmapChatPanel({
  messages,
  isSending,
  activeNodeLabel,
  onAsk,
  onClear,
  inputValue,
  setInputValue,
}: MindmapChatPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (inputValue.trim()) onAsk(inputValue.trim());
      setInputValue("");
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
    <div className="flex flex-col h-full border-l border-border bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">
            {activeNodeLabel ? `Exploring: ${activeNodeLabel}` : "Chat"}
          </p>
          <p className="text-xs text-muted-foreground">
            Click a node to explore it
          </p>
        </div>
        {visibleMessages.length > 0 && (
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 text-muted-foreground hover:text-destructive"
            onClick={onClear}
            title="Clear chat"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col gap-3 p-4">
          {visibleMessages.length === 0 && (
            <p className="text-xs text-muted-foreground text-center mt-8">
              Click a node on the map to get an AI-generated summary, then ask
              follow-up questions here.
            </p>
          )}
          {visibleMessages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="shrink-0 border-t border-border p-3">
        <div className="flex gap-2 items-end">
          <Textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a follow-up question…"
            className="resize-none text-sm min-h-[40px] max-h-[120px]"
            rows={1}
            disabled={isSending}
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={isSending || !inputValue.trim()}
            className="shrink-0"
          >
            {isSending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Individual message bubble ─────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const pending = isPending(message);

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="bg-violet-600 text-white rounded-2xl rounded-tr-sm px-3 py-2 max-w-[85%] text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className={cn(
          "rounded-2xl rounded-tl-sm px-3 py-2 max-w-[92%] text-sm",
          "bg-muted text-foreground",
          pending && "opacity-60"
        )}
      >
        {pending ? (
          <span className="flex items-center gap-2 text-muted-foreground text-xs">
            <Loader2 className="h-3 w-3 animate-spin" />
            Generating summary…
          </span>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => (
                <p className="mb-1 last:mb-0 leading-relaxed">{children}</p>
              ),
              ul: ({ children }) => (
                <ul className="list-disc pl-4 mb-1">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal pl-4 mb-1">{children}</ol>
              ),
              code: ({ children }) => (
                <code className="bg-muted-foreground/20 px-1 rounded text-xs font-mono">
                  {children}
                </code>
              ),
              strong: ({ children }) => (
                <strong className="font-semibold">{children}</strong>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}
