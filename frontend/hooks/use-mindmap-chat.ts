/**
 * useMindmapChat — manages per-user mindmap chat state.
 *
 * - Fetches full history on mount.
 * - Polls for pending messages every 1.5 s.
 * - Exposes exploreNode and ask functions.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  mindmapApi,
  type ChatMessage,
  type ExploreNodeResponse,
} from "@/api/mindmap";

const PENDING_POLL_MS = 1500;

interface UseMindmapChatOptions {
  mindmapId: number | null;
  fileId: number;
  classroomId: number;
}

interface UseMindmapChatReturn {
  messages: ChatMessage[];
  isSending: boolean;
  error: string | null;
  activeNodeId: string | null;
  setActiveNodeId: (id: string | null) => void;
  exploreNode: (nodeId: string) => Promise<ExploreNodeResponse | null>;
  ask: (content: string) => Promise<void>;
  clearChat: () => Promise<void>;
}

export function useMindmapChat({
  mindmapId,
  fileId,
  classroomId,
}: UseMindmapChatOptions): UseMindmapChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  // ── Helper: does any message have { pending: true } in metadata? ────────
  const hasPending = useCallback((msgs: ChatMessage[]) => {
    return msgs.some(
      (m) =>
        m.role === "assistant" && m.message_metadata?.pending === true
    );
  }, []);

  // ── Polling: refresh history until no pending messages ─────────────────
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const maybeStartPolling = useCallback(
    (msgs: ChatMessage[]) => {
      if (!mindmapId) return;
      if (!hasPending(msgs)) return;
      if (pollRef.current) return; // already polling
      pollRef.current = setInterval(async () => {
        if (!isMounted.current || !mindmapId) return;
        try {
          const resp = await mindmapApi.getChatHistory(mindmapId);
          if (!isMounted.current) return;
          setMessages(resp.messages);
          if (!hasPending(resp.messages)) stopPolling();
        } catch {
          // transient network error — keep going
        }
      }, PENDING_POLL_MS);
    },
    [mindmapId, hasPending, stopPolling]
  );

  // ── Initial history fetch ───────────────────────────────────────────────
  useEffect(() => {
    if (!mindmapId) return;
    let cancelled = false;
    (async () => {
      try {
        const resp = await mindmapApi.getChatHistory(mindmapId);
        if (cancelled) return;
        setMessages(resp.messages);
        maybeStartPolling(resp.messages);
      } catch {
        // no chat yet — that's fine
      }
    })();
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [mindmapId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── exploreNode ─────────────────────────────────────────────────────────
  const exploreNode = useCallback(
    async (nodeId: string): Promise<ExploreNodeResponse | null> => {
      if (!mindmapId) return null;
      try {
        const resp = await mindmapApi.exploreNode(mindmapId, nodeId);
        setActiveNodeId(nodeId);

        // Refresh history to include the new MARKER + placeholder
        const histResp = await mindmapApi.getChatHistory(mindmapId);
        if (isMounted.current) {
          setMessages(histResp.messages);
          maybeStartPolling(histResp.messages);
        }
        return resp;
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Failed to explore node.";
        setError(msg);
        return null;
      }
    },
    [mindmapId, maybeStartPolling]
  );

  // ── ask ─────────────────────────────────────────────────────────────────
  const ask = useCallback(
    async (content: string) => {
      if (!mindmapId || !content.trim()) return;
      setIsSending(true);
      setError(null);
      try {
        const resp = await mindmapApi.ask(mindmapId, content, activeNodeId);
        if (!isMounted.current) return;

        // Fetch full history after the response so we have all messages
        const histResp = await mindmapApi.getChatHistory(mindmapId);
        if (isMounted.current) {
          setMessages(histResp.messages);
        }
      } catch (err: unknown) {
        if (!isMounted.current) return;
        const msg =
          err instanceof Error ? err.message : "Failed to send message.";
        setError(msg);
      } finally {
        if (isMounted.current) setIsSending(false);
      }
    },
    [mindmapId, activeNodeId]
  );

  // ── clearChat ───────────────────────────────────────────────────────────
  const clearChat = useCallback(async () => {
    if (!mindmapId) return;
    try {
      await mindmapApi.clearChat(mindmapId);
      if (isMounted.current) {
        setMessages([]);
        setActiveNodeId(null);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to clear chat.";
      setError(msg);
    }
  }, [mindmapId]);

  return {
    messages,
    isSending,
    error,
    activeNodeId,
    setActiveNodeId,
    exploreNode,
    ask,
    clearChat,
  };
}
