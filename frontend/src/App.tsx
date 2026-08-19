import { BrowserRouter, Routes, Route, Link, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import DocumentsPage from "./pages/DocumentsPage";
import ChatPage from "./pages/ChatPage";
import PreferencesPage from "./pages/PreferencesPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { loggedIn } = useAuth();
  const navigate = useNavigate();
  if (!loggedIn) {
    navigate("/login", { replace: true });
    return null;
  }
  return <>{children}</>;
}

function NavBar() {
  const { loggedIn, logout } = useAuth();
  const navigate = useNavigate();

  if (!loggedIn) return null;

  return (
    <nav style={navStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
        <Link to="/" style={logoStyle}>
          🧠 AI Knowledge
        </Link>
        <Link to="/" style={navLink}>
          Dashboard
        </Link>
        <Link to="/documents" style={navLink}>
          Documents
        </Link>
        <Link to="/chat" style={navLink}>
          Chat
        </Link>
        <Link to="/preferences" style={navLink}>
          Settings
        </Link>
      </div>
      <button
        onClick={() => {
          logout();
          navigate("/login");
        }}
        style={logoutBtn}
      >
        Sign out
      </button>
    </nav>
  );
}

function AppRoutes() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/documents"
          element={
            <ProtectedRoute>
              <DocumentsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/preferences"
          element={
            <ProtectedRoute>
              <PreferencesPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

const navStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "0.75rem 1.5rem",
  borderBottom: "1px solid #e5e7eb",
  background: "#fff",
};

const logoStyle: React.CSSProperties = {
  fontWeight: 700,
  fontSize: "1rem",
  color: "#111827",
  textDecoration: "none",
};

const navLink: React.CSSProperties = {
  color: "#6b7280",
  textDecoration: "none",
  fontSize: "0.875rem",
  fontWeight: 500,
};

const logoutBtn: React.CSSProperties = {
  padding: "0.375rem 0.75rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: "6px",
  cursor: "pointer",
  fontSize: "0.8125rem",
  color: "#374151",
};
