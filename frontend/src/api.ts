import type {
  TokenResponse,
  User,
  DocumentListResponse,
  Document,
  ConversationListResponse,
  ConversationWithMessages,
  QAResponse,
  RAGSearchResponse,
  Source,
} from "./types";
export type {
  User,
  Document,
  DocumentListResponse,
  Conversation,
  ConversationListResponse,
  ConversationWithMessages,
  Message,
  Source,
  QAResponse,
  RAGSearchResponse,
  RAGSearchResult,
} from "./types";

const BASE = "/api/v1";

function getToken(): string | null {
  return localStorage.getItem("token");
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function request<T>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(opts.headers as Record<string, string>),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export async function register(
  email: string,
  password: string,
  display_name?: string,
): Promise<User> {
  return request<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name }),
  });
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const data = await request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  localStorage.setItem("token", data.access_token);
  return data;
}

export function logout(): void {
  localStorage.removeItem("token");
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

// Documents
export async function listDocuments(
  limit = 50,
  offset = 0,
): Promise<DocumentListResponse> {
  return request<DocumentListResponse>(
    `/documents/?limit=${limit}&offset=${offset}`,
  );
}

export async function getDocument(id: string): Promise<Document> {
  return request<Document>(`/documents/${id}`);
}

export async function uploadDocument(file: File): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/documents/upload`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  await request<void>(`/documents/${id}`, { method: "DELETE" });
}

// Conversations
export async function listConversations(
  limit = 50,
): Promise<ConversationListResponse> {
  return request<ConversationListResponse>(
    `/conversations/?limit=${limit}`,
  );
}

export async function getConversation(
  id: string,
): Promise<ConversationWithMessages> {
  return request<ConversationWithMessages>(`/conversations/${id}`);
}

export async function createConversation(
  title?: string,
): Promise<{ id: string; title: string }> {
  return request<{ id: string; title: string }>("/conversations/", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await request<void>(`/conversations/${id}`, { method: "DELETE" });
}

// QA / Chat
export async function askQuestion(
  question: string,
  conversationId?: string,
  limit = 5,
): Promise<QAResponse> {
  return request<QAResponse>("/qa/ask", {
    method: "POST",
    body: JSON.stringify({ question, conversation_id: conversationId, limit }),
  });
}

// SSE streaming types
export interface StreamEvent {
  type: "sources" | "answer" | "error";
  content?: string;
  is_final?: boolean;
  sources?: Source[];
  provider?: string;
  model?: string;
  error?: string;
}

export interface StreamCallbacks {
  onSources?: (sources: Source[]) => void;
  onAnswerChunk?: (content: string, isFinal: boolean) => void;
  onError?: (error: string) => void;
  onDone?: () => void;
}

export async function askQuestionStream(
  question: string,
  conversationId?: string,
  limit = 5,
  signal?: AbortSignal,
): Promise<{ reader: ReadableStreamDefaultReader<Uint8Array>; controller: AbortController }> {
  const controller = new AbortController();
  const combinedSignal = signal
    ? AbortSignal.any([controller.signal, signal])
    : controller.signal;

  const res = await fetch(`${BASE}/qa/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ question, conversation_id: conversationId, limit }),
    signal: combinedSignal,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Stream failed (${res.status})`);
  }

  if (!res.body) {
    throw new Error("No response body");
  }

  return { reader: res.body.getReader(), controller };
}

export function parseSSEEvents(
  text: string,
): StreamEvent[] {
  const events: StreamEvent[] = [];
  const lines = text.split("\n");
  for (const line of lines) {
    if (line.startsWith("data: ")) {
      try {
        events.push(JSON.parse(line.slice(6)));
      } catch {
        // Skip malformed JSON
      }
    }
  }
  return events;
}

export async function consumeStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  callbacks: StreamCallbacks,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete lines
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const event: StreamEvent = JSON.parse(line.slice(6));

          if (event.type === "sources" && event.sources) {
            callbacks.onSources?.(event.sources);
          } else if (event.type === "answer") {
            callbacks.onAnswerChunk?.(
              event.content || "",
              event.is_final || false,
            );
          } else if (event.type === "error") {
            callbacks.onError?.(event.error || "Unknown error");
          }
        } catch {
          // Skip malformed JSON
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      // Request was cancelled — not an error
      return;
    }
    callbacks.onError?.(
      err instanceof Error ? err.message : "Stream connection failed",
    );
  } finally {
    callbacks.onDone?.();
  }
}

// RAG Search
export async function ragSearch(
  query: string,
  limit = 5,
): Promise<RAGSearchResponse> {
  return request<RAGSearchResponse>("/rag/search", {
    method: "POST",
    body: JSON.stringify({ query, limit }),
  });
}

// User preferences
export interface UserPreferences {
  default_model?: string | null;
  default_temperature?: number | null;
  default_max_tokens?: number | null;
  default_rag_limit?: number | null;
  default_rag_threshold?: number | null;
  theme?: string | null;
  language?: string | null;
  custom?: Record<string, unknown> | null;
}

export async function getPreferences(): Promise<UserPreferences> {
  return request<UserPreferences>("/users/me/preferences");
}

export async function updatePreferences(
  prefs: Partial<UserPreferences>,
): Promise<UserPreferences> {
  return request<UserPreferences>("/users/me/preferences", {
    method: "PATCH",
    body: JSON.stringify(prefs),
  });
}
