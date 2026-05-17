/**
 * useMinddmap — manages mindmap generation polling and tree state.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { mindmapApi, type Mindmap, type MindmapStatus } from "@/api/mindmap";

const POLL_INTERVAL_MS = 2000;

interface UseMindmapOptions {
  fileId: number;
  /** Auto-trigger generation on first mount if no mindmap exists. */
  autoGenerate?: boolean;
}

interface UseMindmapReturn {
  mindmap: Mindmap | null;
  status: MindmapStatus | "idle";
  isLoading: boolean;
  error: string | null;
  generate: (force?: boolean) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useMindmap({
  fileId,
  autoGenerate = false,
}: UseMindmapOptions): UseMindmapReturn {
  const [mindmap, setMindmap] = useState<Mindmap | null>(null);
  const [status, setStatus] = useState<MindmapStatus | "idle">("idle");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMounted = useRef(true);
  const didAutoRegen = useRef(false);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const data = await mindmapApi.get(fileId);
        if (!isMounted.current) return;
        setMindmap(data);
        setStatus(data.status);
        if (data.status === "ready" || data.status === "failed") {
          stopPolling();
          setIsLoading(false);
          if (data.status === "failed") {
            setError(data.error_message ?? "Mindmap generation failed.");
          }
          // Auto-regen if tree is from the old schema (version < 2)
          if (
            data.status === "ready" &&
            !didAutoRegen.current &&
            ((data.tree_data?.version ?? 0) < 2)
          ) {
            didAutoRegen.current = true;
            generate(true);
          }
        }
      } catch {
        // transient network error — keep polling
      }
    }, POLL_INTERVAL_MS);
  }, [fileId, stopPolling]);

  const generate = useCallback(
    async (force = false) => {
      setIsLoading(true);
      setError(null);
      try {
        const resp = await mindmapApi.generate(fileId, force);
        if (!isMounted.current) return;
        setMindmap(resp.mindmap);
        setStatus(resp.mindmap.status);
        if (
          resp.mindmap.status === "pending" ||
          resp.mindmap.status === "generating"
        ) {
          startPolling();
        } else {
          setIsLoading(false);
        }
      } catch (err: unknown) {
        if (!isMounted.current) return;
        const msg =
          err instanceof Error ? err.message : "Failed to start generation.";
        setError(msg);
        setIsLoading(false);
      }
    },
    [fileId, startPolling]
  );

  const refresh = useCallback(async () => {
    try {
      const data = await mindmapApi.get(fileId);
      if (!isMounted.current) return;
      setMindmap(data);
      setStatus(data.status);
    } catch {
      // ignore
    }
  }, [fileId]);

  // Initial fetch
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await mindmapApi.get(fileId);
        if (cancelled) return;
        setMindmap(data);
        setStatus(data.status);
        if (data.status === "pending" || data.status === "generating") {
          setIsLoading(true);
          startPolling();
        } else if (
          data.status === "ready" &&
          !didAutoRegen.current &&
          ((data.tree_data?.version ?? 0) < 2)
        ) {
          // Stale tree from old schema — regenerate once
          didAutoRegen.current = true;
          generate(true);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        // 404 = no mindmap yet
        const code = (err as { response?: { status?: number } })?.response
          ?.status;
        if (code === 404) {
          if (autoGenerate) {
            generate();
          }
        }
      }
    })();
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [fileId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { mindmap, status, isLoading, error, generate, refresh };
}
