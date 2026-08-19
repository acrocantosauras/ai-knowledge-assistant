import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { AuthProvider, useAuth } from "../AuthContext";

function TestComponent() {
  const { loggedIn, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="status">{loggedIn ? "in" : "out"}</span>
      <button onClick={login}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("starts logged out when no token", () => {
    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>,
    );
    expect(screen.getByTestId("status")).toHaveTextContent("out");
  });

  it("starts logged in when token exists", () => {
    localStorage.setItem("token", "test-token");
    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>,
    );
    expect(screen.getByTestId("status")).toHaveTextContent("in");
  });

  it("login sets loggedIn to true", () => {
    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>,
    );
    expect(screen.getByTestId("status")).toHaveTextContent("out");
    act(() => {
      screen.getByText("Login").click();
    });
    expect(screen.getByTestId("status")).toHaveTextContent("in");
  });

  it("logout clears token and sets loggedIn to false", () => {
    localStorage.setItem("token", "test-token");
    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>,
    );
    expect(screen.getByTestId("status")).toHaveTextContent("in");
    act(() => {
      screen.getByText("Logout").click();
    });
    expect(screen.getByTestId("status")).toHaveTextContent("out");
    expect(localStorage.getItem("token")).toBeNull();
  });
});
