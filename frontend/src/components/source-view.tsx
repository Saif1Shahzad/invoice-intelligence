import { useEffect, useRef } from "react";
import { ZoomIn, ZoomOut, Maximize } from "lucide-react";
import { Button } from "@/components/ui/button";
import { pulse } from "@/lib/motion";
import { money, type SampleDoc, type BBox } from "@/lib/review";
import { cn } from "@/lib/utils";
import { makeSampleDocs } from "@/lib/sample-data";

export function ZoomBar({ zoom, setZoom, label }: { zoom: number; setZoom: (z: number) => void; label?: string }) {
  return (
    <div className="flex items-center gap-1 border-b border-border px-3 py-2 text-xs">
      <span className="mr-auto text-muted-foreground">{label}</span>
      <Button size="icon" variant="ghost" aria-label="Zoom out" onClick={() => setZoom(Math.max(0.5, +(zoom - 0.25).toFixed(2)))}><ZoomOut className="h-4 w-4" /></Button>
      <span className="w-12 text-center font-mono">{Math.round(zoom * 100)}%</span>
      <Button size="icon" variant="ghost" aria-label="Zoom in" onClick={() => setZoom(Math.min(2.5, +(zoom + 0.25).toFixed(2)))}><ZoomIn className="h-4 w-4" /></Button>
      <Button size="icon" variant="ghost" aria-label="Reset zoom" onClick={() => setZoom(1)}><Maximize className="h-4 w-4" /></Button>
    </div>
  );
}

const box = (b: BBox) => ({ left: `${b[0]}%`, top: `${b[1]}%`, width: `${b[2]}%`, height: `${b[3]}%` });

/** Renders a sample "source page" (sample docs ship no real images) with clickable field regions. */
export function SampleSource({ doc, active, onPick, zoom }: { doc: SampleDoc; active: string | null; onPick: (k: string) => void; zoom: number }) {
  const hl = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!active) return;
    hl.current?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
    pulse(hl.current);
  }, [active]);
  const sourceDoc = makeSampleDocs().find(original => original.id === doc.id) ?? doc;
  const regions = [
    ...sourceDoc.fields.map((f) => ({ k: f.key, b: f.bbox, text: f.extracted, label: f.label })),
    ...sourceDoc.lineItems.map((l) => ({ k: `li:${l.id}`, b: l.bbox, text: `${l.description}   ${l.qty} × ${money(l.unitPrice)}`, label: "Line" })),
  ];
  const act = regions.find((r) => r.k === active);
  return (
    <div className="h-full overflow-auto bg-muted/60 p-4">
      <div className="mx-auto origin-top transition-[width]" style={{ width: `${560 * zoom}px` }}>
        <div className="relative aspect-[8.5/11] w-full bg-paper shadow-paper" style={{ fontSize: `${11 * zoom}px` }}>
          <div className="absolute left-[8%] top-[30%] w-[84%] border-b border-border pb-1 text-[0.85em] uppercase tracking-wider text-muted-foreground">Description · Qty × Unit</div>
          <div className="absolute left-[8%] top-[88%] w-[84%] text-[0.8em] text-muted-foreground">Sample document rendering — not an actual uploaded file.</div>
          {regions.map((r) => (
            <button
              key={r.k}
              onClick={() => onPick(r.k)}
              style={box(r.b)}
              title={`${r.label}: ${r.text}`}
              className={cn(
                "absolute flex items-center overflow-hidden whitespace-nowrap rounded-sm px-1 text-left text-foreground transition-colors hover:bg-highlight",
                r.k === "vendor" && "font-display text-[1.6em]",
                r.k === "total" && "font-semibold",
                active === r.k && "ring-2 ring-primary",
              )}
            >
              {r.k.startsWith("li:") || r.k === "vendor" ? r.text : <><span className="mr-2 text-muted-foreground">{r.label}</span><span className="ml-auto font-mono">{r.text || "—"}</span></>}
            </button>
          ))}
          {act && <div ref={hl} aria-hidden className="pointer-events-none absolute rounded-sm bg-highlight" style={box(act.b)} />}
        </div>
      </div>
    </div>
  );
}

export function ImageSource({ pages, zoom }: { pages: { page: number; image_url: string }[]; zoom: number }) {
  return (
    <div className="h-full space-y-4 overflow-auto bg-muted/60 p-4">
      {pages.map((p) => (
        <div key={p.page} className="mx-auto" style={{ width: `${560 * zoom}px` }}>
          <img src={p.image_url} alt={`Page ${p.page}`} className="w-full bg-paper shadow-paper" />
          <div className="mt-1 text-center text-xs text-muted-foreground">Page {p.page}</div>
        </div>
      ))}
    </div>
  );
}

