import clsx from "clsx";
import { ChevronDown, FileText, Search, Sparkles } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useApp } from "@/context/App";
import type { Source } from "@/lib/api";

import { pageLabel } from "./ui";

/** Turn [1] / [1, 3] markers into links react-markdown hands to our chip renderer. */
function linkCitations(text: string): string {
  return text.replace(/\[(\d+(?:\s*,\s*\d+)*)\](?!\()/g, (_, nums: string) =>
    nums.split(",").map((n) => `[${n.trim()}](#cite-${n.trim()})`).join(""),
  );
}

export function Answer({ content, sources, streaming }: { content: string; sources: Source[]; streaming?: boolean }) {
  const { openViewer } = useApp();
  const byNumber = new Map(sources.map((s) => [s.n, s]));

  return (
    <div className="answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href === "#caret") return <span className="caret" aria-hidden />;
            const match = href?.match(/^#cite-(\d+)$/);
            if (!match) return <a href={href} target="_blank" rel="noreferrer" className="text-accent underline">{children}</a>;
            const source = byNumber.get(Number(match[1]));
            if (!source) return null;
            return (
              <button
                type="button"
                onClick={() => openViewer({ documentId: source.document_id, documentTitle: source.document_title, page: source.page_start, text: source.text })}
                className="mx-0.5 inline-flex -translate-y-px items-center rounded-md bg-accent-soft px-1.5 align-baseline text-[11px] font-semibold leading-[18px] text-accent-ink transition hover:bg-accent hover:text-white"
                title={`${source.document_title}, ${pageLabel(source.page_start, source.page_end)}`}
              >
                {source.n}
                <span className="ml-1 font-normal opacity-80">{pageLabel(source.page_start, source.page_end)}</span>
              </button>
            );
          },
        }}
      >
        {linkCitations(content) + (streaming ? " [](#caret)" : "")}
      </ReactMarkdown>
    </div>
  );
}

function SourceCard({ source, cited }: { source: Source; cited: boolean }) {
  const { openViewer } = useApp();
  const how = [source.vector_rank && `meaning #${source.vector_rank}`, source.keyword_rank && `keywords #${source.keyword_rank}`].filter(Boolean).join(" · ");
  return (
    <button
      onClick={() => openViewer({ documentId: source.document_id, documentTitle: source.document_title, page: source.page_start, text: source.text })}
      className={clsx(
        "group flex w-full gap-3 rounded-xl border p-3 text-left transition hover:border-accent/50 hover:bg-surface",
        cited ? "border-line bg-surface" : "border-transparent bg-surface-2/60",
      )}
    >
      <span className={clsx("mt-0.5 grid size-6 shrink-0 place-items-center rounded-md text-xs font-semibold", cited ? "bg-accent text-white dark:text-[#1a0e05]" : "bg-line text-ink-2")}>{source.n}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-[13px] font-medium text-ink">
          <FileText className="size-3.5 shrink-0 text-muted" />
          <span className="truncate">{source.document_title}</span>
          <span className="shrink-0 text-muted">· {pageLabel(source.page_start, source.page_end)}</span>
        </span>
        <span className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-ink-2">{source.text}</span>
        {how && <span className="mt-1 block text-[11px] text-muted">Matched by {how}</span>}
      </span>
    </button>
  );
}

export function Sources({ sources, cited }: { sources: Source[]; cited: number[] }) {
  const [showAll, setShowAll] = useState(false);
  if (!sources.length) return null;
  const citedSet = new Set(cited);
  const primary = cited.length ? sources.filter((s) => citedSet.has(s.n)).sort((a, b) => cited.indexOf(a.n) - cited.indexOf(b.n)) : sources.slice(0, 3);
  const rest = sources.filter((s) => !primary.includes(s));

  return (
    <div className="mt-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
        <Sparkles className="size-3.5" /> {cited.length ? "Sources cited" : "Most relevant passages"}
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {primary.map((s) => <SourceCard key={s.n} source={s} cited={citedSet.has(s.n)} />)}
      </div>
      {rest.length > 0 && (
        <>
          <button onClick={() => setShowAll((v) => !v)} className="mt-2 flex items-center gap-1 text-xs font-medium text-muted hover:text-ink">
            <Search className="size-3.5" /> {showAll ? "Hide" : "Show"} {rest.length} other retrieved passage{rest.length === 1 ? "" : "s"}
            <ChevronDown className={clsx("size-3.5 transition", showAll && "rotate-180")} />
          </button>
          {showAll && <div className="mt-2 grid gap-2 sm:grid-cols-2">{rest.map((s) => <SourceCard key={s.n} source={s} cited={false} />)}</div>}
        </>
      )}
    </div>
  );
}
