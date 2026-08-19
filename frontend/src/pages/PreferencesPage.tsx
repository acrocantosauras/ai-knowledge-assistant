import { useEffect, useState } from "react";
import {
  getPreferences,
  updatePreferences,
  type UserPreferences,
} from "../api";

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<UserPreferences>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getPreferences()
      .then(setPrefs)
      .catch((err) => {
        console.error("Failed to load preferences:", err);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const updated = await updatePreferences(prefs);
      setPrefs(updated);
      setSuccess("Preferences saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const update = <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K],
  ) => {
    setPrefs((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div style={{ padding: "2rem", maxWidth: "640px", margin: "0 auto" }}>
        <p style={{ color: "#6b7280" }}>Loading...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: "2rem", maxWidth: "640px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>
        Preferences
      </h1>

      {error && <div style={banner("#fef2f2", "#dc2626")}>{error}</div>}
      {success && <div style={banner("#f0fdf4", "#16a34a")}>{success}</div>}

      {/* LLM Settings */}
      <section style={sectionStyle}>
        <h2 style={sectionTitle}>LLM Settings</h2>

        <label style={labelStyle}>
          Default Model
          <input
            type="text"
            value={prefs.default_model ?? ""}
            onChange={(e) => update("default_model", e.target.value || null)}
            placeholder="gpt-4o-mini"
            style={inputStyle}
          />
        </label>

        <label style={labelStyle}>
          Default Temperature (0.0 – 2.0)
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={prefs.default_temperature ?? ""}
            onChange={(e) =>
              update(
                "default_temperature",
                e.target.value ? parseFloat(e.target.value) : null,
              )
            }
            placeholder="0.7"
            style={inputStyle}
          />
        </label>

        <label style={labelStyle}>
          Default Max Tokens (1 – 4096)
          <input
            type="number"
            min={1}
            max={4096}
            value={prefs.default_max_tokens ?? ""}
            onChange={(e) =>
              update(
                "default_max_tokens",
                e.target.value ? parseInt(e.target.value, 10) : null,
              )
            }
            placeholder="1024"
            style={inputStyle}
          />
        </label>
      </section>

      {/* RAG Settings */}
      <section style={sectionStyle}>
        <h2 style={sectionTitle}>RAG Settings</h2>

        <label style={labelStyle}>
          Default Document Limit (1 – 50)
          <input
            type="number"
            min={1}
            max={50}
            value={prefs.default_rag_limit ?? ""}
            onChange={(e) =>
              update(
                "default_rag_limit",
                e.target.value ? parseInt(e.target.value, 10) : null,
              )
            }
            placeholder="5"
            style={inputStyle}
          />
        </label>

        <label style={labelStyle}>
          Default Similarity Threshold (0.0 – 1.0)
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={prefs.default_rag_threshold ?? ""}
            onChange={(e) =>
              update(
                "default_rag_threshold",
                e.target.value ? parseFloat(e.target.value) : null,
              )
            }
            placeholder="0.7"
            style={inputStyle}
          />
        </label>
      </section>

      {/* UI Settings */}
      <section style={sectionStyle}>
        <h2 style={sectionTitle}>UI Settings</h2>

        <label style={labelStyle}>
          Theme
          <select
            value={prefs.theme ?? ""}
            onChange={(e) => update("theme", e.target.value || null)}
            style={inputStyle}
          >
            <option value="">System default</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>

        <label style={labelStyle}>
          Language
          <select
            value={prefs.language ?? ""}
            onChange={(e) => update("language", e.target.value || null)}
            style={inputStyle}
          >
            <option value="">System default</option>
            <option value="en">English</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
            <option value="ja">日本語</option>
            <option value="zh">中文</option>
          </select>
        </label>
      </section>

      <div style={{ marginTop: "1.5rem", display: "flex", gap: "0.75rem" }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: "0.5rem 1.25rem",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "0.875rem",
            fontWeight: 600,
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? "Saving..." : "Save Preferences"}
        </button>
        <button
          onClick={() => {
            setPrefs({});
            setSuccess("");
            setError("");
          }}
          style={{
            padding: "0.5rem 1.25rem",
            background: "#f3f4f6",
            color: "#374151",
            border: "1px solid #d1d5db",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "0.875rem",
          }}
        >
          Reset to Defaults
        </button>
      </div>
    </div>
  );
}

const sectionStyle: React.CSSProperties = {
  marginBottom: "1.5rem",
  padding: "1.25rem",
  border: "1px solid #e5e7eb",
  borderRadius: "12px",
  background: "#fff",
};

const sectionTitle: React.CSSProperties = {
  fontSize: "1rem",
  fontWeight: 600,
  marginBottom: "1rem",
  marginTop: 0,
};

const labelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: "0.75rem",
  fontSize: "0.8125rem",
  fontWeight: 500,
  color: "#374151",
};

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: "0.25rem",
  padding: "0.5rem 0.75rem",
  border: "1px solid #d1d5db",
  borderRadius: "8px",
  fontSize: "0.875rem",
  outline: "none",
};

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
