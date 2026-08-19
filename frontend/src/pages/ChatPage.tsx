import { useEffect, useState, useRef, useCallback } from "react";
import {
  listConversations,
  getConversation,
  deleteConversation,
  askQuestionStream,
  consumeStream,
  type Conversation,
  type Message,
  type Source,
} from "../api";

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [answerSources, setAnswerSources] = useState<Source[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [chatError, setChatError] = useState("");
  const messagesEnd = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const loadConversations = useCallback(async () => {
    try {
      const data = await listConversations();
      setConversations(data.conversations);
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Failed to load conversations",
      );
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const selectConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setChatError("");
    try {
      const conv = await getConversation(id);
      setMessages(conv.messages);
      setAnswerSources([]);
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Failed to load conversation",
      );
      setMessages([]);
    }
  }, []);

  const handleNew = useCallback(() => {
    abortControllerRef.current?.abort();
    setActiveId(null);
    setMessages([]);
    setAnswerSources([]);
    setStreamingContent("");
  }, []);

  const handleStop = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setLoading(false);
    setStreamingContent("");
  }, []);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput("");
    setLoading(true);
    setAnswerSources([]);
    setStreamingContent("");
    setChatError("");

    // Cancel any previous stream
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      conversation_id: activeId ?? "",
      user_id: "",
      role: "user",
      content: question,
      token_count: null,
      metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const { reader } = await askQuestionStream(
        question,
        activeId ?? undefined,
        5,
        controller.signal,
      );

      let finalConversationId = activeId;
      let answerContent = "";

      await consumeStream(reader, {
        onSources: (sources) => {
          setAnswerSources(sources);
        },
        onAnswerChunk: (content) => {
          answerContent += content;
          setStreamingContent(answerContent);
        },
        onError: (error) => {
          setStreamingContent("");
          const errorMsg: Message = {
            id: crypto.randomUUID(),
            conversation_id: activeId ?? "",
            user_id: "",
            role: "assistant",
            content: `Error: ${error}`,
            token_count: null,
            metadata: {},
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, errorMsg]);
        },
        onDone: () => {
          // Convert streamed content to a final message
          if (answerContent) {
            const assistantMsg: Message = {
              id: crypto.randomUUID(),
              conversation_id: finalConversationId ?? "",
              user_id: "",
              role: "assistant",
              content: answerContent,
              token_count: null,
              metadata: {},
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, assistantMsg]);
          }
          setStreamingContent("");
          setLoading(false);
          loadConversations();
        },
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // Request was cancelled
        setStreamingContent("");
        return;
      }
      setStreamingContent("");
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        conversation_id: activeId ?? "",
        user_id: "",
        role: "assistant",
        content: `Error: ${err instanceof Error ? err.message : "Failed to get answer"}`,
        token_count: null,
        metadata: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this conversation?")) return;
    try {
      await deleteConversation(id);
      if (activeId === id) handleNew();
      loadConversations();
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Failed to delete conversation",
      );
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  return (
    <div style={layout}>
      {/* Sidebar */}
      <div style={sidebar}>
        <div style={{ padding: "1rem", borderBottom: "1px solid #e5e7eb" }}>
          <button onClick={handleNew} style={newBtn}>
            + New Chat
          </button>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          {chatError && (
            <div
              style={{
                padding: "0.5rem 0.75rem",
                background: "#fef2f2",
                color: "#dc2626",
                fontSize: "0.75rem",
                cursor: "pointer",
              }}
              onClick={() => setChatError("")}
            >
              {chatError}
            </div>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              style={{
                ...convItem,
                background: activeId === c.id ? "#eff6ff" : "transparent",
              }}
              onClick={() => selectConversation(c.id)}
            >
              <div style={{ flex: 1, overflow: "hidden" }}>
                <div
                  style={{
                    fontSize: "0.8125rem",
                    fontWeight: 500,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c.title || "New Chat"}
                </div>
                <div style={{ fontSize: "0.6875rem", color: "#9ca3af" }}>
                  {c.message_count} messages
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(c.id);
                }}
                style={deleteBtn}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div style={main}>
        {messages.length === 0 ? (
          <div style={emptyChat}>
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>💬</div>
            <h2 style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>
              AI Knowledge Assistant
            </h2>
            <p style={{ color: "#6b7280", margin: 0, maxWidth: "400px" }}>
              Ask questions about your uploaded documents. The AI will search
              for relevant context and provide grounded answers with source
              citations.
            </p>
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: "auto", padding: "1rem" }}>
            {messages.map((m) => (
              <div
                key={m.id}
                style={{
                  marginBottom: "1rem",
                  display: "flex",
                  justifyContent:
                    m.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                <div
                  style={{
                    maxWidth: "75%",
                    padding: "0.75rem 1rem",
                    borderRadius: "12px",
                    fontSize: "0.875rem",
                    lineHeight: 1.6,
                    background: m.role === "user" ? "#2563eb" : "#f3f4f6",
                    color: m.role === "user" ? "#fff" : "#111827",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {m.content}
                  {m.role === "assistant" &&
                    m.metadata &&
                    Array.isArray(
                      (m.metadata as Record<string, unknown>).sources,
                    ) && (
                      <div style={{ marginTop: "0.5rem" }}>
                        {(
                          (m.metadata as Record<string, unknown>)
                            .sources as Source[]
                        ).map((s, i) => (
                          <div
                            key={i}
                            style={{
                              fontSize: "0.75rem",
                              color: m.role === "user" ? "#bfdbfe" : "#6b7280",
                              borderTop: "1px solid #e5e7eb",
                              paddingTop: "0.25rem",
                              marginTop: "0.25rem",
                            }}
                          >
                            📎 Source {i + 1}
                            {s.score != null &&
                              ` (score: ${s.score.toFixed(2)})`}
                          </div>
                        ))}
                      </div>
                    )}
                </div>
              </div>
            ))}
            {streamingContent && (
              <div
                style={{
                  marginBottom: "1rem",
                  display: "flex",
                  justifyContent: "flex-start",
                }}
              >
                <div
                  style={{
                    maxWidth: "75%",
                    padding: "0.75rem 1rem",
                    borderRadius: "12px",
                    fontSize: "0.875rem",
                    lineHeight: 1.6,
                    background: "#f3f4f6",
                    color: "#111827",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {streamingContent}
                  <span className="animate-pulse">|</span>
                </div>
              </div>
            )}
            {loading && !streamingContent && (
              <div style={{ color: "#6b7280", fontSize: "0.875rem" }}>
                Thinking...
              </div>
            )}
            <div ref={messagesEnd} />
          </div>
        )}

        {/* Sources panel */}
        {answerSources.length > 0 && (
          <div style={sourcesPanel}>
            <div style={{ fontWeight: 600, fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
              Sources
            </div>
            {answerSources.map((s, i) => (
              <div
                key={i}
                style={{
                  fontSize: "0.75rem",
                  color: "#374151",
                  padding: "0.25rem 0",
                  borderBottom: "1px solid #e5e7eb",
                }}
              >
                <strong>Doc {i + 1}</strong>
                {s.score != null && (
                  <span style={{ color: "#6b7280" }}>
                    {" "}
                    · score: {s.score.toFixed(3)}
                  </span>
                )}
                <div style={{ color: "#6b7280", marginTop: "0.125rem" }}>
                  {s.content_preview}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Input bar */}
        <div style={inputBar}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !loading && handleSend()}
            placeholder="Ask a question..."
            disabled={loading}
            style={inputField}
          />
          {loading ? (
            <button
              onClick={handleStop}
              style={{
                ...sendBtn,
                background: "#dc2626",
              }}
            >
              Stop
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              style={{
                ...sendBtn,
                opacity: !input.trim() ? 0.5 : 1,
              }}
            >
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const layout: React.CSSProperties = {
  display: "flex",
  height: "calc(100vh - 0px)",
};

const sidebar: React.CSSProperties = {
  width: "260px",
  borderRight: "1px solid #e5e7eb",
  display: "flex",
  flexDirection: "column",
  background: "#fff",
};

const newBtn: React.CSSProperties = {
  width: "100%",
  padding: "0.5rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: "8px",
  cursor: "pointer",
  fontSize: "0.8125rem",
  fontWeight: 500,
};

const convItem: React.CSSProperties = {
  padding: "0.5rem 1rem",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  borderBottom: "1px solid #f3f4f6",
};

const deleteBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#9ca3af",
  cursor: "pointer",
  fontSize: "1.125rem",
  padding: "0.25rem",
  lineHeight: 1,
};

const main: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  background: "#fff",
};

const emptyChat: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  color: "#111827",
  textAlign: "center",
};

const inputBar: React.CSSProperties = {
  padding: "1rem",
  borderTop: "1px solid #e5e7eb",
  display: "flex",
  gap: "0.5rem",
};

const inputField: React.CSSProperties = {
  flex: 1,
  padding: "0.625rem 1rem",
  border: "1px solid #d1d5db",
  borderRadius: "8px",
  fontSize: "0.875rem",
  outline: "none",
};

const sendBtn: React.CSSProperties = {
  padding: "0.625rem 1.25rem",
  background: "#2563eb",
  color: "#fff",
  border: "none",
  borderRadius: "8px",
  cursor: "pointer",
  fontSize: "0.875rem",
  fontWeight: 600,
};

const sourcesPanel: React.CSSProperties = {
  padding: "0.75rem 1rem",
  borderTop: "1px solid #e5e7eb",
  background: "#f9fafb",
  maxHeight: "160px",
  overflowY: "auto",
};
