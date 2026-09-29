import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, tokens, type Status, type User } from "@/lib/api";

type Theme = "light" | "dark";

export interface Citation {
  documentId: number;
  documentTitle: string;
  page: number;
  text: string;
}

interface AppState {
  user: User | null;
  loadingUser: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  theme: Theme;
  toggleTheme: () => void;
  status: Status | undefined;
  /** The PDF viewer panel: open a document at a page, highlighting a passage. */
  viewer: Citation | null;
  openViewer: (c: Citation) => void;
  closeViewer: () => void;
}

const Ctx = createContext<AppState | null>(null);

export const DEMO = { username: "demo", password: "demo12345" };

export function AppProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loadingUser, setLoadingUser] = useState(Boolean(tokens.access));
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || "light");
  const [viewer, setViewer] = useState<Citation | null>(null);
  const { data: status } = useQuery({ queryKey: ["status"], queryFn: api.status, staleTime: Infinity });

  useEffect(() => {
    if (!tokens.access) return;
    api.auth.me().then(setUser).catch(() => tokens.clear()).finally(() => setLoadingUser(false));
  }, []);

  const logout = useCallback(() => {
    tokens.clear();
    setUser(null);
    setViewer(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    window.addEventListener("documind:logout", logout);
    return () => window.removeEventListener("documind:logout", logout);
  }, [logout]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("documind-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  const value = useMemo<AppState>(() => {
    const accept = (r: { access: string; refresh: string; user: User }) => {
      tokens.set(r.access, r.refresh);
      setUser(r.user);
    };
    return {
      user,
      loadingUser,
      logout,
      login: async (u, p) => accept(await api.auth.login(u, p)),
      register: async (u, e, p) => accept(await api.auth.register(u, e, p)),
      theme,
      toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
      status,
      viewer,
      openViewer: setViewer,
      closeViewer: () => setViewer(null),
    };
  }, [user, loadingUser, logout, theme, status, viewer]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
