import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Cpu, Library, LogOut, Menu, MessageSquare, Moon, Plus, Sparkles, Sun, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useMatch, useNavigate } from "react-router-dom";

import { useApp } from "@/context/App";
import { api, type Conversation } from "@/lib/api";

import { PdfPanel } from "./PdfPanel";
import { Logo } from "./ui";

function group(conversations: Conversation[]) {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const weekAgo = startOfToday.getTime() - 6 * 86400_000;
  const buckets: Record<string, Conversation[]> = { Today: [], "Previous 7 days": [], Older: [] };
  for (const c of conversations) {
    const t = new Date(c.updated_at).getTime();
    buckets[t >= startOfToday.getTime() ? "Today" : t >= weekAgo ? "Previous 7 days" : "Older"].push(c);
  }
  return Object.entries(buckets).filter(([, list]) => list.length);
}

const ENGINE_LABEL = {
  anthropic: "Claude answers",
  gemini: "Gemini answers",
  ollama: "Local model answers",
  extractive: "Extractive mode",
} as const;

function EngineCard() {
  const { status } = useApp();
  if (!status) return null;
  const hint =
    status.provider === "anthropic" || status.provider === "gemini" ? `Model: ${status.model}.`
    : status.provider === "ollama" ? `Running ${status.ollama_model} on this computer via Ollama. Free and private.`
    : status.ollama === "no-model" ? `Ollama is running. Download the model with: ollama pull ${status.ollama_model}`
    : "No LLM connected: answers quote the best passages. Add a free Gemini key or start Ollama.";
  return (
    <div className="rounded-xl border border-line bg-surface/60 p-3 text-xs">
      <p className="flex items-center gap-1.5 font-semibold text-ink">
        {status.llm ? <Sparkles className="size-3.5 text-accent" /> : <Cpu className="size-3.5 text-muted" />}
        {ENGINE_LABEL[status.provider]}
      </p>
      <p className="mt-1 leading-relaxed text-muted">
        {hint} Embeddings: {status.embeddings_local_model ? status.embeddings.replace("BAAI/", "") : "hashing (offline)"}
      </p>
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout, theme, toggleTheme } = useApp();
  const id = useMatch("/c/:id")?.params.id; // layout routes can't read child params via useParams
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: conversations } = useQuery({ queryKey: ["conversations"], queryFn: api.conversations.list });
  const { data: docs } = useQuery({ queryKey: ["documents"], queryFn: api.documents.list });
  const remove = useMutation({
    mutationFn: api.conversations.remove,
    onSuccess: (_d, removed) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (String(removed) === id) navigate("/c");
    },
  });

  return (
    <div className="flex h-full flex-col gap-4 p-3">
      <div className="flex items-center justify-between px-2 pt-2"><Link to="/c" onClick={onNavigate}><Logo /></Link></div>
      <button
        onClick={() => { navigate("/c"); onNavigate?.(); }}
        className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2.5 text-sm font-medium text-ink shadow-[var(--shadow)] transition hover:border-accent/40"
      >
        <Plus className="size-4 text-accent" /> New chat
      </button>
      <NavLink
        to="/library"
        onClick={onNavigate}
        className={({ isActive }) => clsx("flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition", isActive ? "bg-surface text-ink" : "text-ink-2 hover:bg-surface/70")}
      >
        <Library className="size-4" /> Library
        <span className="ml-auto rounded-full bg-line px-2 text-[11px] tabular-nums text-ink-2">{docs?.length ?? 0}</span>
      </NavLink>

      <div className="-mx-1 flex-1 overflow-y-auto px-1">
        {group(conversations ?? []).map(([label, list]) => (
          <div key={label} className="mb-3">
            <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</p>
            {list.map((c) => (
              <div key={c.id} className="group relative">
                <NavLink
                  to={`/c/${c.id}`}
                  onClick={onNavigate}
                  className={({ isActive }) => clsx("flex items-center gap-2 rounded-lg py-2 pl-3 pr-8 text-[13px] transition", isActive ? "bg-surface font-medium text-ink shadow-[var(--shadow)]" : "text-ink-2 hover:bg-surface/70")}
                >
                  <MessageSquare className="size-3.5 shrink-0 text-muted" />
                  <span className="truncate">{c.title}</span>
                </NavLink>
                <button
                  onClick={() => confirm("Delete this conversation?") && remove.mutate(c.id)}
                  className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded-md p-1 text-muted hover:text-bad group-hover:block"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        ))}
      </div>

      <EngineCard />
      <div className="flex items-center gap-2 rounded-xl px-2 py-1">
        <span className="grid size-8 place-items-center rounded-full bg-ink text-sm font-semibold text-bg">{user?.username[0]?.toUpperCase()}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{user?.username}</span>
        <button onClick={toggleTheme} className="rounded-lg p-2 text-muted hover:bg-surface hover:text-ink" aria-label="Toggle theme">
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
        <button onClick={logout} className="rounded-lg p-2 text-muted hover:bg-surface hover:text-bad" aria-label="Log out"><LogOut className="size-4" /></button>
      </div>
    </div>
  );
}

export function Layout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-full">
      <aside className="hidden w-72 shrink-0 border-r border-line bg-panel lg:block"><Sidebar /></aside>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
          <aside className="animate-slide-in absolute inset-y-0 left-0 w-72 bg-panel shadow-[var(--shadow-pop)]">
            <button onClick={() => setOpen(false)} className="absolute right-3 top-4 rounded-lg p-1.5 text-muted" aria-label="Close menu"><X className="size-4" /></button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line px-4 py-3 lg:hidden">
          <button onClick={() => setOpen(true)} className="rounded-lg p-1.5 text-ink-2" aria-label="Open menu"><Menu className="size-5" /></button>
          <Logo />
        </header>
        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 overflow-y-auto"><Outlet /></main>
          <PdfPanel />
        </div>
      </div>
    </div>
  );
}
