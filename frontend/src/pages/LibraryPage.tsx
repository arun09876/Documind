import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertCircle, Eye, FileText, Layers, Loader2, MessageSquarePlus, Trash2, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button, Empty, formatBytes, pageLabel } from "@/components/ui";
import { useApp } from "@/context/App";
import { api, errorMessage, type DocumentItem } from "@/lib/api";

function ChunksDialog({ doc, onClose }: { doc: DocumentItem; onClose: () => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["chunks", doc.id], queryFn: () => api.documents.chunks(doc.id) });
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="animate-fade-up relative flex max-h-[85vh] w-full flex-col rounded-t-3xl border border-line bg-surface sm:max-w-2xl sm:rounded-3xl">
        <div className="flex items-start justify-between gap-4 border-b border-line p-5">
          <div>
            <h2 className="font-serif text-xl font-semibold text-ink">How this document was split</h2>
            <p className="mt-1 text-sm text-muted">{doc.chunk_count} chunks from {doc.page_count} pages · embedded with {doc.embedding_model}. Chunks follow sentence boundaries, overlap slightly, and never cross a page, so every citation names one page.</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-surface-2" aria-label="Close"><X className="size-5" /></button>
        </div>
        <div className="space-y-3 overflow-y-auto p-5">
          {isLoading && <Loader2 className="mx-auto size-5 animate-spin text-accent" />}
          {data?.map((c) => (
            <div key={c.id} className="rounded-xl border border-line bg-surface-2/50 p-3.5">
              <p className="mb-1.5 flex items-center gap-2 text-xs font-semibold text-muted">
                <span className="rounded bg-line px-1.5 py-0.5 text-ink-2">#{c.index + 1}</span> {pageLabel(c.page_start, c.page_end)} · {c.text.length} chars
              </p>
              <p className="text-[13px] leading-relaxed text-ink-2">{c.text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LibraryPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { openViewer, status } = useApp();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<{ name: string; pct: number }[]>([]);
  const [inspect, setInspect] = useState<DocumentItem | null>(null);

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: api.documents.list,
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === "processing") ? 1500 : false),
  });

  const remove = useMutation({
    mutationFn: api.documents.remove,
    onSuccess: () => {
      toast.success("Document deleted");
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files).filter((f) => {
      if (!f.name.toLowerCase().endsWith(".pdf")) {
        toast.error(`${f.name}: only PDF files are supported`);
        return false;
      }
      if (status && f.size > status.max_upload_mb * 1024 * 1024) {
        toast.error(`${f.name}: larger than ${status.max_upload_mb} MB`);
        return false;
      }
      return true;
    });
    for (const file of list) {
      setUploads((u) => [...u, { name: file.name, pct: 0 }]);
      try {
        await api.documents.upload(file, (pct) => setUploads((u) => u.map((x) => (x.name === file.name ? { ...x, pct } : x))));
        toast.success(`${file.name} uploaded. Indexing…`);
      } catch (e) {
        toast.error(`${file.name}: ${errorMessage(e)}`);
      } finally {
        setUploads((u) => u.filter((x) => x.name !== file.name));
        qc.invalidateQueries({ queryKey: ["documents"] });
      }
    }
  }

  async function chatAbout(doc: DocumentItem) {
    const conv = await api.conversations.create([doc.id]);
    qc.invalidateQueries({ queryKey: ["conversations"] });
    navigate(`/c/${conv.id}`);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-8">
      <h1 className="font-serif text-4xl font-medium tracking-tight text-ink">Library</h1>
      <p className="mt-2 text-muted">Your documents are private to your account. Each PDF is split into passages and indexed for semantic and keyword search.</p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void uploadFiles(e.dataTransfer.files); }}
        onClick={() => input.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
        className={clsx(
          "mt-8 flex cursor-pointer flex-col items-center rounded-3xl border-2 border-dashed px-6 py-12 text-center transition",
          dragging ? "border-accent bg-accent-soft" : "border-line bg-surface/50 hover:border-accent/50 hover:bg-surface",
        )}
      >
        <div className="grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent"><UploadCloud className="size-6" /></div>
        <p className="mt-4 font-medium text-ink">Drop PDFs here, or click to browse</p>
        <p className="mt-1 text-sm text-muted">Text-based PDFs up to {status?.max_upload_mb ?? 25} MB · scanned documents need OCR first</p>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => e.target.files && void uploadFiles(e.target.files)} />
      </div>

      {uploads.map((u) => (
        <div key={u.name} className="card mt-3 flex items-center gap-3 p-4">
          <Loader2 className="size-4 animate-spin text-accent" />
          <span className="flex-1 truncate text-sm text-ink">{u.name}</span>
          <div className="h-1.5 w-40 overflow-hidden rounded-full bg-surface-2"><div className="h-full bg-accent transition-all" style={{ width: `${u.pct}%` }} /></div>
        </div>
      ))}

      <div className="mt-8">
        {!isLoading && docs.length === 0 && uploads.length === 0 ? (
          <Empty icon={<FileText className="size-5" />} title="No documents yet" text="Upload your first PDF above. Handbooks, papers, contracts and manuals all work well." />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {docs.map((d) => (
              <div key={d.id} className="card group flex flex-col p-5">
                <div className="flex items-start gap-3">
                  <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><FileText className="size-5" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 font-medium leading-snug text-ink">{d.title}</p>
                    <p className="mt-1 truncate text-xs text-muted">{d.filename} · {formatBytes(d.size_bytes)}</p>
                  </div>
                  <button onClick={() => confirm(`Delete "${d.title}"? Chats that cited it keep their text.`) && remove.mutate(d.id)} className="rounded-lg p-1.5 text-muted opacity-0 transition hover:bg-bad/10 hover:text-bad group-hover:opacity-100 focus:opacity-100" aria-label="Delete document">
                    <Trash2 className="size-4" />
                  </button>
                </div>
                <div className="mt-4 flex items-center gap-3 text-xs text-muted">
                  {d.status === "processing" && <span className="flex items-center gap-1.5 font-medium text-accent"><Loader2 className="size-3.5 animate-spin" /> Reading and indexing…</span>}
                  {d.status === "failed" && <span className="flex items-center gap-1.5 font-medium text-bad"><AlertCircle className="size-3.5" /> {d.error}</span>}
                  {d.status === "ready" && (
                    <>
                      <span>{d.page_count} pages</span>
                      <span className="flex items-center gap-1"><Layers className="size-3.5" /> {d.chunk_count} passages</span>
                      <span className="ml-auto rounded-full bg-good/10 px-2 py-0.5 font-medium text-good">Ready</span>
                    </>
                  )}
                </div>
                {d.status === "ready" && (
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
                    <Button size="sm" icon={<MessageSquarePlus className="size-3.5" />} onClick={() => void chatAbout(d)}>Chat</Button>
                    <Button size="sm" variant="secondary" icon={<Eye className="size-3.5" />} onClick={() => openViewer({ documentId: d.id, documentTitle: d.title, page: 1, text: "" })}>View</Button>
                    <Button size="sm" variant="ghost" icon={<Layers className="size-3.5" />} onClick={() => setInspect(d)}>Passages</Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {inspect && <ChunksDialog doc={inspect} onClose={() => setInspect(null)} />}
    </div>
  );
}
