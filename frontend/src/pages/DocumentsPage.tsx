import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  type Document,
  type DocumentListResponse,
} from "../api";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const initialUploadRef = useRef(false);

  const load = useCallback(() => {
    setLoading(true);
    listDocuments()
      .then(setDocs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!initialUploadRef.current && searchParams.get("upload") === "true") {
      initialUploadRef.current = true;
      fileRef.current?.click();
      setSearchParams({});
    }
  }, [searchParams, setSearchParams]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    setSuccess("");
    try {
      await uploadDocument(file);
      setSuccess(`"${file.name}" uploaded successfully`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (id: string, title: string) => {
    if (!window.confirm(`Delete "${title}"?`)) return;
    try {
      await deleteDocument(id);
      setSuccess(`"${title}" deleted`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div style={{ padding: "2rem", maxWidth: "960px", margin: "0 auto" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>
          Documents
        </h1>
        <label
          style={{
            padding: "0.5rem 1rem",
            background: "#2563eb",
            color: "#fff",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "0.875rem",
            fontWeight: 500,
            opacity: uploading ? 0.7 : 1,
          }}
        >
          {uploading ? "Uploading..." : "Upload Document"}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.docx"
            onChange={handleUpload}
            style={{ display: "none" }}
            disabled={uploading}
          />
        </label>
      </div>

      {error && <div style={banner("#fef2f2", "#dc2626")}>{error}</div>}
      {success && <div style={banner("#f0fdf4", "#16a34a")}>{success}</div>}

      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading...</p>
      ) : !docs || docs.documents.length === 0 ? (
        <div style={emptyBox}>
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>📂</div>
          <p style={{ color: "#6b7280", margin: 0 }}>No documents yet</p>
          <p style={{ color: "#9ca3af", fontSize: "0.875rem", margin: "0.25rem 0 0" }}>
            Upload a PDF, TXT, or DOCX file to get started
          </p>
        </div>
      ) : (
        <div>
          <div style={{ color: "#6b7280", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            {docs.total} document{docs.total !== 1 ? "s" : ""}
          </div>
          {docs.documents.map((doc) => (
            <DocRow
              key={doc.id}
              doc={doc}
              onDelete={() => handleDelete(doc.id, doc.title)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DocRow({ doc, onDelete }: { doc: Document; onDelete: () => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "8px",
        marginBottom: "0.5rem",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "0.75rem 1rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
          background: "#fff",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500 }}>{doc.title}</div>
          <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
            {doc.content_type?.split("/").pop() ?? "unknown"} ·{" "}
            {doc.chunk_count} chunks · {doc.status}
          </div>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <span style={{ color: "#9ca3af", fontSize: "0.75rem" }}>
            {new Date(doc.created_at).toLocaleDateString()}
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            style={{
              padding: "0.25rem 0.5rem",
              background: "#fef2f2",
              color: "#dc2626",
              border: "1px solid #fecaca",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.75rem",
            }}
          >
            Delete
          </button>
        </div>
      </div>
      {expanded && (
        <div
          style={{
            padding: "0.75rem 1rem",
            borderTop: "1px solid #e5e7eb",
            background: "#f9fafb",
            fontSize: "0.8125rem",
            color: "#374151",
          }}
        >
          {doc.content_excerpt && (
            <p style={{ margin: "0 0 0.5rem" }}>
              <strong>Excerpt:</strong> {doc.content_excerpt}
            </p>
          )}
          <p style={{ margin: 0, color: "#6b7280" }}>
            ID: {doc.id}
          </p>
        </div>
      )}
    </div>
  );
}

function banner(bg: string, color: string): React.CSSProperties {
  return {
    background: bg,
    color,
    padding: "0.5rem 0.75rem",
    borderRadius: "8px",
    fontSize: "0.8125rem",
    marginBottom: "1rem",
  };
}

const emptyBox: React.CSSProperties = {
  textAlign: "center",
  padding: "3rem 1rem",
  border: "2px dashed #d1d5db",
  borderRadius: "12px",
  background: "#f9fafb",
};
