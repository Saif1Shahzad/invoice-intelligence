import { useEffect, useRef, useState } from "react";
import { UploadCloud, X, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApp } from "@/lib/app-state";
import { slideIn } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { SampleDoc } from "@/lib/review";

const ACCEPT = ["application/pdf", "image/jpeg", "image/png"];
const STAGES = ["Validate", "Upload", "Accepted (202)", "Queued for extraction"] as const;

interface Item { file: File; stage: number; error: string | null; done: boolean }

export function UploadDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { mode, conn, client, addSample, refreshLive } = useApp();
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const liveBlocked = mode === "live" && conn !== "reachable";

  useEffect(() => { const animation = open ? slideIn(panel.current) : undefined; return () => { animation?.revert(); }; }, [open]);
  useEffect(() => { if (!open) setItems([]); }, [open]);

  const add = (files: FileList | null) => {
    if (!files) return;
    setItems((cur) => [
      ...cur,
      ...Array.from(files).map((file) => ({
        file, stage: 0, done: false,
        error: ACCEPT.includes(file.type) ? null : `Unsupported type "${file.type || "unknown"}". Upload a PDF, JPEG or PNG.`,
      })),
    ]);
  };

  const set = (i: number, p: Partial<Item>) => setItems((cur) => cur.map((x, j) => (j === i ? { ...x, ...p } : x)));

  const run = async () => {
    setBusy(true);
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (!it || it.error || it.done) continue;
      set(i, { stage: 1 });
      if (mode === "sample") {
        await new Promise((r) => setTimeout(r, 450));
        set(i, { stage: 2 });
        await new Promise((r) => setTimeout(r, 350));
        set(i, { stage: 3, done: true });
        const d: SampleDoc = {
          id: `smp-new-${Date.now()}-${i}`, filename: it.file.name, media_type: it.file.type, status: "processing", page_count: 1,
          created_at: new Date().toISOString(), job: { status: "queued", error: null }, review: { status: "none", revision: 0 },
          fields: [], lineItems: [], taxRate: 0, taxBBox: [0, 0, 0, 0], holds: {}, matching: { po: null, poTotal: null, receipt: null }, history: [],
        };
        addSample(d);
      } else if (client) {
        try {
          await client.uploadDocument(it.file);
          set(i, { stage: 3, done: true });
        } catch (e) {
          set(i, { error: `Upload failed: ${e instanceof Error ? e.message : String(e)}. Check the connection and retry.`, stage: 1 });
        }
      }
    }
    setBusy(false);
    if (mode === "live") refreshLive();
  };

  if (!open) return null;
  const ready = items.filter((x) => !x.error && !x.done).length;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-foreground/30" onClick={() => { if (!busy) onClose(); }} />
      <div ref={panel} role="dialog" aria-label="Upload documents" className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-card shadow-paper">
        <div className="flex items-center justify-between border-b border-border p-4">
          <div>
            <h2 className="text-lg">Upload documents</h2>
            <p className="text-xs text-muted-foreground">{mode === "sample" ? "Sample mode — files stay in this browser and are not sent anywhere." : "Sends each file to POST /v1/documents."}</p>
          </div>
          <button aria-label="Close" onClick={() => { if (!busy) onClose(); }}><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {liveBlocked && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">Backend not connected. Live uploads are disabled until /health responds.</div>
          )}
          <button
            disabled={liveBlocked || busy}
            onClick={() => input.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); if (!liveBlocked && !busy) add(e.dataTransfer.files); }}
            className="flex w-full flex-col items-center gap-2 rounded-lg border border-dashed border-input bg-background p-8 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground disabled:opacity-50"
          >
            <UploadCloud className="h-7 w-7 text-primary" />
            Drop files or click to browse
            <span className="text-xs">PDF, JPEG, PNG · multiple files</span>
          </button>
          <input ref={input} type="file" multiple accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          <ul className="space-y-2">
            {items.map((it, i) => (
              <li key={i} className="rounded-md border border-border p-3">
                <div className="flex items-center gap-2 text-sm">
                  {it.error ? <AlertCircle className="h-4 w-4 text-destructive" /> : it.done ? <CheckCircle2 className="h-4 w-4 text-success" /> : busy && it.stage > 0 ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : <span className="h-4 w-4" />}
                  <span className="truncate font-medium">{it.file.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{(it.file.size / 1024).toFixed(0)} KB</span>
                </div>
                <div className="mt-2 grid grid-cols-4 gap-1">
                  {STAGES.map((s, k) => (
                    <div key={s} className="space-y-1">
                      <div className={cn("h-1 rounded-full", it.error && k >= it.stage ? "bg-destructive/30" : k <= it.stage && (it.stage > 0 || k === 0) && !it.error ? "bg-primary" : "bg-muted")} />
                      <div className="text-[10px] text-muted-foreground">{s}</div>
                    </div>
                  ))}
                </div>
                {it.error && (
                  <div className="mt-2 flex items-start justify-between gap-2 text-xs text-destructive">
                    <span>{it.error}</span>
                    <button className="shrink-0 underline" onClick={() => setItems((c) => c.filter((_, j) => j !== i))}>Remove</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex gap-2 border-t border-border p-4">
          <Button variant="outline" className="flex-1" onClick={() => { if (!busy) onClose(); }}>Close</Button>
          <Button className="flex-1" disabled={!ready || busy || liveBlocked} onClick={run}>
            {busy ? "Uploading…" : `Upload ${ready || ""}`}
          </Button>
        </div>
      </div>
    </div>
  );
}

