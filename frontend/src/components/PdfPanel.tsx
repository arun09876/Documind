import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, Minus, Plus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";

import { useApp } from "@/context/App";
import { api } from "@/lib/api";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const normalize = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/** Side panel that shows the cited PDF page with the retrieved passage highlighted. */
export function PdfPanel() {
  const { viewer, closeViewer } = useApp();
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [scale, setScale] = useState(1);
  const [width, setWidth] = useState(520);
  const box = useRef<HTMLDivElement>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["pdf", viewer?.documentId],
    queryFn: () => api.documents.file(viewer!.documentId),
    enabled: !!viewer,
    staleTime: Infinity,
  });
  // react-pdf transfers the buffer to its worker, so hand it a copy each time.
  const file = useMemo(() => (data ? { data: new Uint8Array(data.slice(0)) } : null), [data]);

  useEffect(() => {
    if (viewer) setPage(viewer.page);
  }, [viewer]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.min(760, entry.contentRect.width - 32)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [viewer]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeViewer();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeViewer]);

  // Highlight text-layer items that are part of the cited passage (only on the cited page).
  const passage = useMemo(() => normalize(viewer?.text ?? ""), [viewer]);
  const textRenderer = useCallback(
    ({ str }: { str: string }) => {
      const n = normalize(str);
      const hit = viewer && page === viewer.page && n.length > 3 && passage.includes(n);
      return hit ? `<mark>${escapeHtml(str)}</mark>` : escapeHtml(str);
    },
    [passage, page, viewer],
  );

  if (!viewer) return null;

  return (
    <aside className="animate-slide-in fixed inset-0 z-40 flex flex-col border-l border-line bg-panel lg:static lg:inset-auto lg:z-auto lg:w-[46%] lg:max-w-[720px] lg:shrink-0">
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink">{viewer.documentTitle}</p>
          <p className="text-xs text-muted">Highlighted: the passage used for this answer</p>
        </div>
        <div className="flex items-center rounded-lg border border-line bg-surface">
          <button className="p-1.5 text-muted hover:text-ink" onClick={() => setScale((s) => Math.max(0.6, s - 0.15))} aria-label="Zoom out"><Minus className="size-4" /></button>
          <span className="w-11 text-center text-xs tabular-nums text-ink-2">{Math.round(scale * 100)}%</span>
          <button className="p-1.5 text-muted hover:text-ink" onClick={() => setScale((s) => Math.min(2, s + 0.15))} aria-label="Zoom in"><Plus className="size-4" /></button>
        </div>
        <button onClick={closeViewer} className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-ink" aria-label="Close viewer"><X className="size-4" /></button>
      </header>

      <div ref={box} className="flex-1 overflow-auto p-4">
        {isLoading && <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-accent" /></div>}
        {isError && <p className="p-6 text-center text-sm text-bad">Couldn't load this PDF.</p>}
        {file && (
          <Document file={file} onLoadSuccess={({ numPages }) => setPages(numPages)} loading={<Loader2 className="mx-auto mt-10 size-6 animate-spin text-accent" />}>
            <div className="pdf-page mx-auto w-fit overflow-hidden rounded-lg shadow-[var(--shadow-pop)]">
              <Page pageNumber={page} width={width * scale} renderAnnotationLayer={false} customTextRenderer={textRenderer} />
            </div>
          </Document>
        )}
      </div>

      <footer className="flex items-center justify-center gap-3 border-t border-line px-4 py-2.5 text-sm">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-30" aria-label="Previous page"><ChevronLeft className="size-4" /></button>
        <span className="tabular-nums text-ink-2">
          Page <b className="text-ink">{page}</b> of {pages || "…"}
          {page !== viewer.page && (
            <button onClick={() => setPage(viewer.page)} className="ml-2 text-xs font-medium text-accent hover:underline">back to cited page {viewer.page}</button>
          )}
        </span>
        <button disabled={!pages || page >= pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-30" aria-label="Next page"><ChevronRight className="size-4" /></button>
      </footer>
    </aside>
  );
}
