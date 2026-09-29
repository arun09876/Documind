import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowUp, Check, ChevronDown, Copy, Cpu, FileText, Files, Sparkles, Square, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Answer, Sources } from "@/components/Answer";
import { Button, Empty } from "@/components/ui";
import { api, type DocumentItem, type Source } from "@/lib/api";

interface ChatMessage {
  key: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  cited: number[];
  mode?: string;
  streaming?: boolean;
  error?: string;
}

const DEMO_QUESTIONS = [
  "How many weeks of parental leave do primary caregivers get?",
  "What's the daily meal allowance when travelling?",
  "How does HNSW compare to IVF?",
  "Why combine BM25 with vector search?",
];

function suggestions(docs: DocumentItem[]): string[] {
  const titles = docs.map((d) => d.title);
  if (titles.some((t) => t.includes("Northwind")) && titles.some((t) => t.includes("Vector Search"))) return DEMO_QUESTIONS;
  return docs.slice(0, 2).flatMap((d) => [`Summarize "${d.title}"`, `What are the key points in "${d.title}"?`]).slice(0, 4);
}

function ScopePicker({ docs, scope, setScope, locked }: { docs: DocumentItem[]; scope: number[]; setScope: (ids: number[]) => void; locked: boolean }) {
  const [open, setOpen] = useState(false);
  const label = scope.length === 0 ? `All documents (${docs.length})` : scope.length === 1 ? docs.find((d) => d.id === scope[0])?.title ?? "1 document" : `${scope.length} documents`;
  return (
    <div className="relative">
      <button
        disabled={locked}
        onClick={() => setOpen((v) => !v)}
        className="flex max-w-72 items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 transition hover:border-accent/40 disabled:cursor-default disabled:hover:border-line"
        title={locked ? "A conversation's documents are fixed once it starts" : "Choose which documents to search"}
      >
        <Files className="size-3.5 text-accent" />
        <span className="truncate">Searching: {label}</span>
        {!locked && <ChevronDown className="size-3.5" />}
      </button>
      {open && !locked && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="animate-fade-up absolute left-0 z-20 mt-2 w-80 rounded-xl border border-line bg-surface p-1.5 shadow-[var(--shadow-pop)]">
            <button onClick={() => setScope([])} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-2">
              <span className={clsx("grid size-4 place-items-center rounded border", scope.length === 0 ? "border-accent bg-accent text-white" : "border-line")}>{scope.length === 0 && <Check className="size-3" />}</span>
              All documents
            </button>
            <div className="my-1 h-px bg-line" />
            {docs.map((d) => {
              const on = scope.includes(d.id);
              return (
                <button key={d.id} onClick={() => setScope(on ? scope.filter((x) => x !== d.id) : [...scope, d.id])} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-2">
                  <span className={clsx("grid size-4 shrink-0 place-items-center rounded border", on ? "border-accent bg-accent text-white" : "border-line")}>{on && <Check className="size-3" />}</span>
                  <span className="truncate">{d.title}</span>
                  <span className="ml-auto shrink-0 text-xs text-muted">{d.page_count}p</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text.replace(/\[(\d+(?:,\s*\d+)*)\]/g, ""));
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
      className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted hover:bg-surface-2 hover:text-ink"
    >
      {done ? <Check className="size-3.5 text-good" /> : <Copy className="size-3.5" />} {done ? "Copied" : "Copy"}
    </button>
  );
}

export default function ChatPage() {
  const { id } = useParams();
  const conversationId = id ? Number(id) : null;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [scope, setScope] = useState<number[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const createdHere = useRef<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  const { data: docs = [] } = useQuery({ queryKey: ["documents"], queryFn: api.documents.list });
  const readyDocs = docs.filter((d) => d.status === "ready");

  // Load the conversation when the URL changes (but not the one we just created mid-stream).
  useEffect(() => {
    if (conversationId === null) {
      setMessages([]);
      setScope([]);
      return;
    }
    if (createdHere.current === conversationId) return;
    abort.current?.abort();
    api.conversations
      .get(conversationId)
      .then((c) => {
        setScope(c.document_ids);
        setMessages((c.messages ?? []).map((m) => ({ key: String(m.id), role: m.role, content: m.content, sources: m.sources, cited: m.cited, mode: m.mode })));
      })
      .catch(() => {
        toast.error("That conversation doesn't exist.");
        navigate("/c", { replace: true });
      });
  }, [conversationId, navigate]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const updateLast = (patch: (m: ChatMessage) => ChatMessage) => setMessages((list) => [...list.slice(0, -1), patch(list[list.length - 1])]);

  const send = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || busy) return;
      if (!readyDocs.length) {
        toast("Upload a PDF first", { action: { label: "Open library", onClick: () => navigate("/library") } });
        return;
      }
      setBusy(true);
      setInput("");
      let cid = conversationId;
      try {
        if (cid === null) {
          const conv = await api.conversations.create(scope);
          cid = conv.id;
          createdHere.current = cid;
          navigate(`/c/${cid}`);
        }
        setMessages((list) => [
          ...list,
          { key: `u${Date.now()}`, role: "user", content: question, sources: [], cited: [] },
          { key: `a${Date.now()}`, role: "assistant", content: "", sources: [], cited: [], streaming: true },
        ]);
        abort.current = new AbortController();
        await api.conversations.ask(
          cid,
          question,
          (event) => {
            if (event.type === "sources") updateLast((m) => ({ ...m, sources: event.sources }));
            else if (event.type === "delta") updateLast((m) => ({ ...m, content: m.content + event.text }));
            else if (event.type === "done") updateLast((m) => ({ ...m, content: event.content, cited: event.cited, mode: event.mode, streaming: false }));
            else if (event.type === "error") updateLast((m) => ({ ...m, streaming: false, error: event.error }));
          },
          abort.current.signal,
        );
      } catch (e) {
        const aborted = e instanceof DOMException && e.name === "AbortError";
        updateLast((m) => (m?.role === "assistant" ? { ...m, streaming: false, error: aborted ? "Stopped." : e instanceof Error ? e.message : "Request failed." } : m));
      } finally {
        updateLast((m) => (m?.streaming ? { ...m, streaming: false } : m));
        setBusy(false);
        abort.current = null;
        qc.invalidateQueries({ queryKey: ["conversations"] });
        textarea.current?.focus();
      }
    },
    [busy, conversationId, navigate, qc, readyDocs.length, scope],
  );

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 pb-8 pt-6 sm:px-6">
          {empty ? (
            docs.length === 0 ? (
              <div className="pt-16">
                <Empty
                  icon={<Upload className="size-5" />}
                  title="Start by adding a PDF"
                  text="Upload documents to your library, then ask questions in plain English. Every answer cites the page it came from."
                  action={<Link to="/library"><Button icon={<Upload className="size-4" />}>Go to library</Button></Link>}
                />
              </div>
            ) : (
              <div className="animate-fade-up pt-[8vh] text-center">
                <h1 className="font-serif text-4xl font-medium tracking-tight text-ink sm:text-5xl">What would you like to know?</h1>
                <p className="mx-auto mt-3 max-w-md text-[15px] text-muted">Ask about your documents in plain English. Answers come only from your files, with page citations you can check.</p>
                <div className="mt-6 flex justify-center"><ScopePicker docs={readyDocs} scope={scope} setScope={setScope} locked={false} /></div>
                <div className="mx-auto mt-8 grid max-w-2xl gap-2.5 sm:grid-cols-2">
                  {suggestions(readyDocs).map((q) => (
                    <button key={q} onClick={() => void send(q)} className="card flex items-start gap-2.5 p-4 text-left text-sm text-ink-2 transition hover:-translate-y-0.5 hover:border-accent/40 hover:text-ink">
                      <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" /> {q}
                    </button>
                  ))}
                </div>
              </div>
            )
          ) : (
            <div className="space-y-8">
              <div className="flex justify-center"><ScopePicker docs={readyDocs} scope={scope} setScope={setScope} locked /></div>
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.key} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[15px] leading-relaxed text-bg">{m.content}</div>
                  </div>
                ) : (
                  <div key={m.key} className="animate-fade-up">
                    {m.streaming && !m.content && (
                      <p className="mb-2 flex items-center gap-2 text-sm text-muted">
                        <FileText className="size-4 animate-pulse text-accent" />
                        {m.sources.length ? `Reading ${m.sources.length} passages…` : "Searching your documents…"}
                      </p>
                    )}
                    {(m.content || m.streaming) && <Answer content={m.content} sources={m.sources} streaming={m.streaming} />}
                    {m.error && <p className="mt-2 rounded-xl bg-bad/10 px-3 py-2 text-sm text-bad">{m.error}</p>}
                    {!m.streaming && <Sources sources={m.sources} cited={m.cited} />}
                    {!m.streaming && m.content && (
                      <div className="mt-3 flex items-center gap-2">
                        <span className="flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-muted">
                          {m.mode === "extractive" ? <Cpu className="size-3" /> : <Sparkles className="size-3 text-accent" />}
                          {m.mode === "extractive" ? "Extractive (no LLM)" : m.mode}
                        </span>
                        <CopyButton text={m.content} />
                      </div>
                    )}
                  </div>
                ),
              )}
              <div ref={bottom} />
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="border-t border-line bg-bg/80 px-4 py-4 backdrop-blur sm:px-6">
        <form
          className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-[var(--shadow)] focus-within:border-accent/60"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <textarea
            ref={textarea}
            rows={1}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            placeholder={readyDocs.length ? "Ask a question about your documents…" : "Upload a PDF to start asking questions"}
            className="max-h-[200px] flex-1 resize-none bg-transparent px-2.5 py-2 text-[15px] text-ink outline-none placeholder:text-muted"
            aria-label="Question"
          />
          {busy ? (
            <button type="button" onClick={() => abort.current?.abort()} className="grid size-10 place-items-center rounded-xl bg-ink text-bg" aria-label="Stop generating">
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button type="submit" disabled={!input.trim()} className="grid size-10 place-items-center rounded-xl bg-accent text-white transition disabled:opacity-40 dark:text-[#1a0e05]" aria-label="Send">
              <ArrowUp className="size-4" />
            </button>
          )}
        </form>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted">Answers are generated from your documents only. Check the cited pages for anything important.</p>
      </div>
    </div>
  );
}
