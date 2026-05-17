/**
 * Mindmap API client.
 */
import api from "./axios";

// ── Types ──────────────────────────────────────────────────────────────────

export type MindmapStatus = "pending" | "generating" | "ready" | "failed";

export interface MindmapNodeData {
  id: string;
  topic: string;
  description: string;
  depth: number;
  has_children?: boolean;
  children: MindmapNodeData[];
}

export interface MindmapTree {
  version: number;
  root: MindmapNodeData;
}

export interface Mindmap {
  id: number;
  file_id: number;
  classroom_id: number;
  status: MindmapStatus;
  root_topic: string | null;
  root_description: string | null;
  tree_data: MindmapTree | null;
  node_count: number;
  generation_meta: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateMindmapResponse {
  detail: string;
  mindmap: Mindmap;
}

export interface ExploreNodeResponse {
  already_explored: boolean;
  last_message_id: number | null;
  marker_id: number | null;
  placeholder_id: number | null;
}

export type ChatMessageRole = "user" | "assistant" | "marker";

export interface ChatMessage {
  id: number;
  mindmap_id: number;
  user_id: number;
  node_id: string | null;
  role: ChatMessageRole;
  content: string;
  message_metadata: Record<string, unknown>;
  created_at: string;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
  has_more: boolean;
}

// ── API calls ──────────────────────────────────────────────────────────────

export const mindmapApi = {
  /** Trigger or resume generation. Returns immediately with current status. */
  generate: (fileId: number, force = false): Promise<GenerateMindmapResponse> =>
    api.post(`/mindmap/files/${fileId}/generate`, { force }).then((r) => r.data),

  /** Poll for current mindmap state (and tree_data once READY). */
  get: (fileId: number): Promise<Mindmap> =>
    api.get(`/mindmap/files/${fileId}`).then((r) => r.data),

  /** Delete the mindmap tree (owner only). */
  delete: (fileId: number): Promise<void> =>
    api.delete(`/mindmap/files/${fileId}`).then(() => undefined),

  /** Start node exploration — returns existing summary or kicks off generation. */
  exploreNode: (mindmapId: number, nodeId: string): Promise<ExploreNodeResponse> =>
    api
      .post(`/mindmap/${mindmapId}/nodes/${nodeId}/explore`)
      .then((r) => r.data),

  /** Fetch chat history. */
  getChatHistory: (mindmapId: number, limit = 50): Promise<ChatHistoryResponse> =>
    api
      .get(`/mindmap/${mindmapId}/chat`, { params: { limit } })
      .then((r) => r.data),

  /** Ask a follow-up question. */
  ask: (
    mindmapId: number,
    content: string,
    activeNodeId: string | null
  ): Promise<{ message: ChatMessage }> =>
    api
      .post(`/mindmap/${mindmapId}/chat/ask`, {
        content,
        active_node_id: activeNodeId,
      })
      .then((r) => r.data),

  /** Clear the user's chat history. */
  clearChat: (mindmapId: number): Promise<void> =>
    api.delete(`/mindmap/${mindmapId}/chat`).then(() => undefined),
};
