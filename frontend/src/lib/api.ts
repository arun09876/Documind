import axios from "axios";

export interface User {
  id: number;
  username: string;
  email: string;
}

export interface DocumentItem {
  id: number;
  title: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  chunk_count: number;
  status: "processing" | "ready" | "failed";
  error: string;
  embedding_model: string;
  created_at: string;
  processed_at: string | null;
}

export interface ChunkItem {
  id: number;
  index: number;
  text: string;
  page_start: number;
  page_end: number;
}

export interface Source {
  n: number;
  chunk_id: number;
  document_id: number;
  document_title: string;
  page_start: number;
  page_end: number;
  text: string;
  score: number;
  vector_rank: number | null;
  keyword_rank: number | null;
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  cited: number[];
  mode: string;
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  document_ids: number[];
  messages?: Message[];
  created_at: string;
  updated_at: string;
}

export interface Status {
  llm: boolean;
  provider: "anthropic" | "gemini" | "ollama" | "extractive";
  model: string | null;
  ollama: "ready" | "no-model" | "offline";
  ollama_model: string;
  embeddings: string;
  embeddings_local_model: boolean;
  max_upload_mb: number;
}

const ACCESS = "documind-access";
const REFRESH = "documind-refresh";

function read(key: string) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export const tokens = {
  get access() {
    return read(ACCESS);
  },
  get refresh() {
    return read(REFRESH);
  },
  set(access: string, refresh?: string) {
    try {
      localStorage.setItem(ACCESS, access);
      if (refresh) localStorage.setItem(REFRESH, refresh);
    } catch {
      /* storage blocked */
    }
  },
  clear() {
    try {
      localStorage.removeItem(ACCESS);
      localStorage.removeItem(REFRESH);
    } catch {
      /* ignore */
    }
  },
};

export const http = axios.create({ baseURL: "/api" });
http.interceptors.request.use((config) => {
  if (tokens.access) config.headers.Authorization = `Bearer ${tokens.access}`;
  return config;
});

let refreshing: Promise<string> | null = null;
async function refreshAccess(): Promise<string> {
  refreshing ??= axios
    .post<{ access: string; refresh?: string }>("/api/auth/refresh/", { refresh: tokens.refresh })
    .then(({ data }) => {
      tokens.set(data.access, data.refresh);
      return data.access;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

http.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && tokens.refresh && !original._retry && !original.url?.startsWith("/auth/")) {
      original._retry = true;
      try {
        original.headers.Authorization = `Bearer ${await refreshAccess()}`;
        return http(original);
      } catch {
        tokens.clear();
        window.dispatchEvent(new Event("documind:logout"));
      }
    }
    throw error;
  },
);

export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback;
  if (!error.response) return "Can't reach the server. Is the backend running?";
  const data = error.response.data as Record<string, unknown> | undefined;
  if (typeof data?.error === "string") return data.error;
  if (typeof data?.detail === "string") return data.detail;
  const first = data && Object.values(data)[0];
  if (Array.isArray(first) && typeof first[0] === "string") return first[0];
  return fallback;
}

type AuthResponse = { access: string; refresh: string; user: User };

export type StreamEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "delta"; text: string }
  | { type: "done"; message_id: number; cited: number[]; mode: string; content: string }
  | { type: "error"; error: string };

/** POST a question and invoke `onEvent` for each Server-Sent Event as it arrives. */
async function ask(conversationId: number, question: string, onEvent: (e: StreamEvent) => void, signal?: AbortSignal) {
  const send = () =>
    fetch(`/api/conversations/${conversationId}/ask/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokens.access}` },
      body: JSON.stringify({ question }),
      signal,
    });
  let response = await send();
  if (response.status === 401 && tokens.refresh) {
    await refreshAccess();
    response = await send();
  }
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error ?? data.detail ?? `Request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) onEvent({ type: event, ...JSON.parse(data) } as StreamEvent);
    }
  }
}

export const api = {
  status: () => http.get<Status>("/status/").then((r) => r.data),
  auth: {
    login: (username: string, password: string) => http.post<AuthResponse>("/auth/login/", { username, password }).then((r) => r.data),
    register: (username: string, email: string, password: string) =>
      http.post<AuthResponse>("/auth/register/", { username, email, password }).then((r) => r.data),
    me: () => http.get<User>("/auth/me/").then((r) => r.data),
  },
  documents: {
    list: () => http.get<DocumentItem[]>("/documents/").then((r) => r.data),
    upload: (file: File, onProgress?: (pct: number) => void) => {
      const form = new FormData();
      form.append("file", file);
      return http
        .post<DocumentItem>("/documents/", form, { onUploadProgress: (e) => e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)) })
        .then((r) => r.data);
    },
    remove: (id: number) => http.delete(`/documents/${id}/`),
    chunks: (id: number) => http.get<ChunkItem[]>(`/documents/${id}/chunks/`).then((r) => r.data),
    file: (id: number) => http.get<ArrayBuffer>(`/documents/${id}/file/`, { responseType: "arraybuffer" }).then((r) => r.data),
  },
  conversations: {
    list: () => http.get<Conversation[]>("/conversations/").then((r) => r.data),
    get: (id: number) => http.get<Conversation>(`/conversations/${id}/`).then((r) => r.data),
    create: (document_ids: number[]) => http.post<Conversation>("/conversations/", { document_ids }).then((r) => r.data),
    remove: (id: number) => http.delete(`/conversations/${id}/`),
    ask,
  },
};
