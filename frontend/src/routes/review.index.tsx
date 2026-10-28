import { createFileRoute, Link } from "@tanstack/react-router";
import { useRef } from "react";
import { AlertTriangle } from "lucide-react";
import { PageHeader, Panel, BackendNotConnected, StatusBadge } from "@/components/bits";
import { useApp } from "@/lib/app-state";
import { blockers, getField } from "@/lib/review";
import { useStaggerIn } from "@/lib/motion";
import { fmtDate } from "@/lib/rows";

export const Route = createFileRoute("/review/")({
  head: () => ({
    meta: [
      { title: "Review queue — Invoice Intelligence" },
      { name: "description", content: "Documents waiting for human verification." },
      { property: "og:title", content: "Review queue — Invoice Intelligence" },
      { property: "og:description", content: "Documents waiting for human verification." },
    ],
  }),
  component: Queue,
});

function Queue() {
  const ref = useRef<HTMLDivElement>(null);
  const { mode, sampleDocs, liveDocs, conn } = useApp();
  useStaggerIn(ref, [mode]);
  if (mode === "live") {
    const q = liveDocs.filter((d) => d.status === "needs_review" || d.review?.status === "pending");
    return (
      <div ref={ref} className="mx-auto max-w-5xl">
        <PageHeader title="Review queue" />
        {conn !== "reachable" ? <BackendNotConnected what="The review queue" /> : (
          <Panel><ul className="divide-y divide-border">
            {q.map((d) => (
              <li key={d.id}><Link to="/review/$id" params={{ id: d.id }} className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-muted/40">
                <span className="flex-1 truncate">{d.filename}</span><StatusBadge status={d.status} /></Link></li>
            ))}
            {!q.length && <li className="px-4 py-8 text-sm text-muted-foreground">No documents in the backend's review queue.</li>}
          </ul></Panel>
        )}
      </div>
    );
  }
  const q = sampleDocs.filter((d) => d.status === "needs_review");
  return (
    <div ref={ref} className="mx-auto max-w-5xl">
      <PageHeader title="Review queue" sub={`${q.length} document${q.length === 1 ? "" : "s"} awaiting a decision`} />
      <div className="space-y-3">
        {q.map((d) => {
          const b = blockers(d);
          return (
            <Panel key={d.id} className="transition-shadow hover:shadow-paper">
              <Link to="/review/$id" params={{ id: d.id }} className="flex flex-col gap-2 p-4 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{getField(d, "vendor")?.value}</div>
                  <div className="text-xs text-muted-foreground">{d.filename} · {fmtDate(d.created_at)} · rev {d.review.revision}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {d.holds.duplicateOf && <span className="rounded-full border border-destructive/30 bg-destructive/5 px-2 py-0.5 text-[11px] text-destructive">Duplicate hold</span>}
                  {d.holds.poIssue && <span className="rounded-full border border-warning/40 bg-warning-soft px-2 py-0.5 text-[11px] text-warning-foreground">PO hold</span>}
                  <span className="flex items-center gap-1 text-xs text-muted-foreground"><AlertTriangle className="h-3.5 w-3.5" />{b.length} blocker{b.length === 1 ? "" : "s"}</span>
                  <span className="font-mono text-sm">{getField(d, "total")?.value}</span>
                </div>
              </Link>
            </Panel>
          );
        })}
        {!q.length && <Panel className="p-8 text-sm text-muted-foreground">Queue is clear.</Panel>}
      </div>
    </div>
  );
}

