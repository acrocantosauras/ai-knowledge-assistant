import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { isLoggedIn, logout as apiLogout } from "./api";

interface AuthCtx {
  loggedIn: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthCtx>({
  loggedIn: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn);

  const login = () => setLoggedIn(true);
  const logout = () => {
    apiLogout();
    setLoggedIn(false);
  };

  return (
    <AuthContext.Provider value={{ loggedIn, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
