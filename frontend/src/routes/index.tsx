import { createFileRoute, Link } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { Upload, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, StatusBadge, BackendNotConnected } from "@/components/bits";
import { UploadDrawer } from "@/components/upload-drawer";
import { useRows, fmtDate } from "@/lib/rows";
import { summarize } from "@/lib/review";
import { useStaggerIn } from "@/lib/motion";
import { useApp } from "@/lib/app-state";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Overview — Invoice Intelligence" },
      { name: "description", content: "Review queue, document counts and recent activity for invoice and receipt review." },
      { property: "og:title", content: "Overview — Invoice Intelligence" },
      { property: "og:description", content: "Human review workspace for invoices and receipts." },
    ],
  }),
  component: Overview,
});

function Overview() {
  const ref = useRef<HTMLDivElement>(null);
  const { rows, live, available } = useRows();
  const { mode } = useApp();
  const [up, setUp] = useState(false);
  const c = summarize(rows);
  useStaggerIn(ref, [mode]);
  const cards = [
    { label: "Documents", value: c.total },
    { label: "Needs review", value: c.needs_review },
    { label: "Processing", value: c.processing },
    { label: "Confirmed", value: c.confirmed },
    { label: "Rejected", value: c.rejected },
    { label: "Failed", value: c.failed },
  ];
  return (
    <div ref={ref} className="mx-auto max-w-6xl">
      <PageHeader
        title="Overview"
        sub="Counts are computed from the records currently loaded."
        actions={<Button onClick={() => setUp(true)}><Upload className="mr-1.5 h-4 w-4" />Upload</Button>}
      />
      {live && !available ? (
        <BackendNotConnected what="Document counts" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {cards.map((k) => (
              <Panel key={k.label} className="p-4">
                <div className="text-xs text-muted-foreground">{k.label}</div>
                <div className="mt-1 font-display text-3xl">{k.value}</div>
              </Panel>
            ))}
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-5">
            <Panel className="lg:col-span-3">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-base">Awaiting review</h2>
                <Link to="/review" className="flex items-center gap-1 text-xs text-primary">Open queue <ArrowRight className="h-3 w-3" /></Link>
              </div>
              <ul className="divide-y divide-border">
                {rows.filter((r) => r.status === "needs_review").map((r) => (
                  <li key={r.id}>
                    <Link to="/review/$id" params={{ id: r.id }} className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-muted/50">
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{r.vendor ?? r.filename}</div>
                        <div className="truncate text-xs text-muted-foreground">{r.filename}</div>
                      </div>
                      {r.total && <span className="font-mono text-sm">{r.total}</span>}
                    </Link>
                  </li>
                ))}
                {!c.needs_review && <li className="px-4 py-6 text-sm text-muted-foreground">Nothing waiting for review.</li>}
              </ul>
            </Panel>
            <Panel className="lg:col-span-2">
              <div className="border-b border-border px-4 py-3"><h2 className="text-base">Recent uploads</h2></div>
              <ul className="divide-y divide-border">
                {[...rows].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 6).map((r) => (
                  <li key={r.id} className="flex items-center gap-2 px-4 py-2.5 text-sm">
                    <span className="min-w-0 flex-1 truncate">{r.filename}</span>
                    <StatusBadge status={r.status} />
                  </li>
                ))}
                {!rows.length && <li className="px-4 py-6 text-sm text-muted-foreground">No documents yet.</li>}
              </ul>
              {rows[0] && <div className="px-4 pb-3 text-[11px] text-muted-foreground">Latest: {fmtDate([...rows].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]!.created_at)}</div>}
            </Panel>
          </div>
        </>
      )}
      <UploadDrawer open={up} onClose={() => setUp(false)} />
    </div>
  );
}

