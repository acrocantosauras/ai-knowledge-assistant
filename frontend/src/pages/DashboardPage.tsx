import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listDocuments, type DocumentListResponse } from "../api";

export default function DashboardPage() {
  const [docs, setDocs] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    listDocuments(5)
      .then(setDocs)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load documents");
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: "2rem", maxWidth: "960px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1rem" }}>
        Dashboard
      </h1>

      {error && (
        <div
          style={{
            background: "#fef2f2",
            color: "#dc2626",
            padding: "0.5rem 0.75rem",
            borderRadius: "8px",
            fontSize: "0.8125rem",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      <div style={grid}>
        <div
          style={card}
          onClick={() => navigate("/documents")}
          role="button"
          tabIndex={0}
        >
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>📄</div>
          <div style={{ fontSize: "1.25rem", fontWeight: 600 }}>
            {loading ? "—" : docs?.total ?? 0}
          </div>
          <div style={{ color: "#6b7280", fontSize: "0.875rem" }}>
            Documents
          </div>
        </div>

        <div
          style={card}
          onClick={() => navigate("/chat")}
          role="button"
          tabIndex={0}
        >
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>💬</div>
          <div style={{ fontSize: "1.25rem", fontWeight: 600 }}>Chat</div>
          <div style={{ color: "#6b7280", fontSize: "0.875rem" }}>
            Ask questions with RAG
          </div>
        </div>

        <div
          style={card}
          onClick={() => navigate("/documents?upload=true")}
          role="button"
          tabIndex={0}
        >
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>⬆️</div>
          <div style={{ fontSize: "1.25rem", fontWeight: 600 }}>Upload</div>
          <div style={{ color: "#6b7280", fontSize: "0.875rem" }}>
            Add new documents
          </div>
        </div>
      </div>

      {docs && docs.documents.length > 0 && (
        <div style={{ marginTop: "2rem" }}>
          <h2
            style={{ fontSize: "1.125rem", fontWeight: 600, marginBottom: "1rem" }}
          >
            Recent Documents
          </h2>
          {docs.documents.slice(0, 5).map((d) => (
            <div
              key={d.id}
              style={{
                padding: "0.75rem 1rem",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                marginBottom: "0.5rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <div style={{ fontWeight: 500 }}>{d.title}</div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                  {d.chunk_count} chunks · {d.status}
                </div>
              </div>
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "#9ca3af",
                }}
              >
                {new Date(d.created_at).toLocaleDateString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "1rem",
};

const card: React.CSSProperties = {
  padding: "1.5rem",
  border: "1px solid #e5e7eb",
  borderRadius: "12px",
  textAlign: "center",
  cursor: "pointer",
  transition: "box-shadow 0.15s",
  background: "#fff",
};
