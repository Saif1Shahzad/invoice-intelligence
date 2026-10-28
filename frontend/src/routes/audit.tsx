import { createFileRoute, Link } from "@tanstack/react-router";
import { useRef } from "react";
import { PageHeader, Panel, BackendNotConnected } from "@/components/bits";
import { useApp } from "@/lib/app-state";
import { useStaggerIn } from "@/lib/motion";
import { fmtDate } from "@/lib/rows";

export const Route = createFileRoute("/audit")({
  head: () => ({
    meta: [
      { title: "Audit — Invoice Intelligence" },
      { name: "description", content: "Revision history across all reviewed documents." },
      { property: "og:title", content: "Audit — Invoice Intelligence" },
      { property: "og:description", content: "Revision history across all reviewed documents." },
    ],
  }),
  component: Audit,
});

function Audit() {
  const ref = useRef<HTMLDivElement>(null);
  const { mode, sampleDocs, conn } = useApp();
  useStaggerIn(ref, [mode]);
  if (mode === "live") {
    return (
      <div ref={ref} className="mx-auto max-w-4xl">
        <PageHeader title="Audit" />
        {conn !== "reachable" ? <BackendNotConnected what="Audit history" /> : (
          <Panel className="p-6 text-sm text-muted-foreground">The backend exposes history per document (GET /v1/documents/{"{id}"}/review/history). Open a document from Documents to view its history.</Panel>
        )}
      </div>
    );
  }
  const events = sampleDocs.flatMap((d) => d.history.map((h) => ({ ...h, doc: d }))).sort((a, b) => b.at.localeCompare(a.at));
  return (
    <div ref={ref} className="mx-auto max-w-4xl">
      <PageHeader title="Audit" sub={`${events.length} revisions across ${sampleDocs.length} documents`} />
      <Panel>
        <ul className="divide-y divide-border">
          {events.map((e) => (
            <li key={`${e.doc.id}-${e.revision}`} className="flex flex-col gap-1 px-4 py-3 text-sm md:flex-row md:items-center md:gap-4">
              <span className="w-40 shrink-0 text-xs text-muted-foreground">{fmtDate(e.at)}</span>
              <Link to="/review/$id" params={{ id: e.doc.id }} className="w-52 shrink-0 truncate font-medium hover:text-primary">{e.doc.filename}</Link>
              <span className="flex-1 text-muted-foreground">{e.summary}</span>
              <span className="text-xs">rev {e.revision} · {e.actor}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

