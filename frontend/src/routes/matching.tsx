import { createFileRoute, Link } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { PageHeader, Panel, BackendNotConnected, StatusBadge } from "@/components/bits";
import { useApp } from "@/lib/app-state";
import { getField, money, totals } from "@/lib/review";
import { useStaggerIn } from "@/lib/motion";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/matching")({
  head: () => ({
    meta: [
      { title: "Matching — Invoice Intelligence" },
      { name: "description", content: "Purchase order and receipt matching for reviewed documents." },
      { property: "og:title", content: "Matching — Invoice Intelligence" },
      { property: "og:description", content: "Purchase order and receipt matching for reviewed documents." },
    ],
  }),
  component: Matching,
});

function Matching() {
  const ref = useRef<HTMLDivElement>(null);
  const { mode, sampleDocs, liveDocs, conn, client } = useApp();
  const [sel, setSel] = useState<string | null>(null);
  const [out, setOut] = useState<string>("");
  useStaggerIn(ref, [mode]);

  if (mode === "live") {
    return (
      <div ref={ref} className="mx-auto max-w-5xl">
        <PageHeader title="Matching" sub="GET /v1/documents/{id}/matching" />
        {conn !== "reachable" ? <BackendNotConnected what="Matching results" /> : (
          <div className="grid gap-4 md:grid-cols-2">
            <Panel><ul className="divide-y divide-border">{liveDocs.map((d) => (
              <li key={d.id}><button className={cn("w-full px-4 py-2.5 text-left text-sm hover:bg-muted/40", sel === d.id && "bg-accent")} onClick={() => {
                setSel(d.id); setOut("Loading…");
                client!.getMatching(d.id).then((r) => setOut(JSON.stringify(r, null, 2))).catch((e) => setOut(String(e)));
              }}>{d.filename}</button></li>
            ))}</ul></Panel>
            <Panel className="p-4"><pre className="overflow-auto font-mono text-xs">{out || "Select a document."}</pre></Panel>
          </div>
        )}
      </div>
    );
  }
  const docs = sampleDocs.filter((d) => d.fields.length);
  return (
    <div ref={ref} className="mx-auto max-w-5xl">
      <PageHeader title="Matching" sub="Invoice vs purchase order vs goods receipt (sample)" />
      <Panel className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground"><tr className="border-b border-border">
            <th className="px-4 py-2 font-medium">Vendor</th><th className="px-4 py-2 font-medium">PO</th><th className="px-4 py-2 text-right font-medium">PO amount</th><th className="px-4 py-2 text-right font-medium">Invoice</th><th className="px-4 py-2 font-medium">Receipt</th><th className="px-4 py-2 font-medium">Status</th>
          </tr></thead>
          <tbody className="divide-y divide-border">
            {docs.map((d) => {
              const t = totals(d);
              const ok = d.matching.poTotal !== null && Math.abs(d.matching.poTotal - t.total) < 0.01;
              return (
                <tr key={d.id} className="hover:bg-muted/40">
                  <td className="px-4 py-3"><Link to="/review/$id" params={{ id: d.id }} className="hover:text-primary">{getField(d, "vendor")?.value}</Link></td>
                  <td className="px-4 py-3 font-mono text-xs">{d.matching.po ?? "—"}</td>
                  <td className="px-4 py-3 text-right font-mono">{d.matching.poTotal === null ? "—" : money(d.matching.poTotal)}</td>
                  <td className={cn("px-4 py-3 text-right font-mono", d.matching.poTotal !== null && !ok && "text-destructive")}>{money(t.total)}</td>
                  <td className="px-4 py-3 font-mono text-xs">{d.matching.receipt ?? "—"}</td>
                  <td className="px-4 py-3"><StatusBadge status={d.matching.po === null ? "no PO" : ok ? "matched" : "variance"} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

