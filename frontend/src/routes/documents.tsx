import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useRef, useState } from "react";
import { Search, Upload, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, StatusBadge, BackendNotConnected } from "@/components/bits";
import { UploadDrawer } from "@/components/upload-drawer";
import { useRows, fmtDate } from "@/lib/rows";
import { useStaggerIn } from "@/lib/motion";
import { useApp } from "@/lib/app-state";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/documents")({
  head: () => ({
    meta: [
      { title: "Documents — Invoice Intelligence" },
      { name: "description", content: "Search, filter and upload invoices and receipts." },
      { property: "og:title", content: "Documents — Invoice Intelligence" },
      { property: "og:description", content: "Search, filter and upload invoices and receipts." },
    ],
  }),
  component: Documents,
});

const TYPES = [{ v: "all", l: "All types" }, { v: "application/pdf", l: "PDF" }, { v: "image/jpeg", l: "JPEG" }, { v: "image/png", l: "PNG" }];

function Documents() {
  const ref = useRef<HTMLDivElement>(null);
  const { rows, live, available, error } = useRows();
  const { mode, client } = useApp();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [type, setType] = useState("all");
  const [up, setUp] = useState(false);
  useStaggerIn(ref, [mode]);

  const statuses = useMemo(() => ["all", ...Array.from(new Set(rows.map((r) => r.status)))], [rows]);
  const filtered = rows.filter((r) => {
    const t = `${r.filename} ${r.vendor ?? ""} ${r.id}`.toLowerCase();
    return t.includes(q.toLowerCase()) && (status === "all" || r.status === status) && (type === "all" || r.media_type === type);
  });

  return (
    <div ref={ref} className="mx-auto max-w-6xl">
      <PageHeader
        title="Documents"
        sub={`${filtered.length} of ${rows.length} shown`}
        actions={
          <>
            {live && available && client && (
              <>
                <Button variant="outline" asChild><a href={client.exportUrl("xlsx")}><Download className="mr-1.5 h-4 w-4" />Download Excel</a></Button>
                <Button variant="outline" asChild><a href={client.exportUrl("csv")}><Download className="mr-1.5 h-4 w-4" />Confirmed CSV</a></Button>
                <Button variant="outline" asChild><a href={client.exportUrl("json")}>JSON</a></Button>
              </>
            )}
            <Button onClick={() => setUp(true)}><Upload className="mr-1.5 h-4 w-4" />Upload</Button>
          </>
        }
      />
      {live && !available ? <BackendNotConnected what="The document list" /> : (
        <Panel>
          <div className="flex flex-col gap-3 border-b border-border p-3 md:flex-row md:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search filename, vendor or ID" className="pl-8" aria-label="Search documents" />
            </div>
            <div className="flex flex-wrap gap-1">
              {statuses.map((s) => (
                <button key={s} onClick={() => setStatus(s)} className={cn("rounded-full border px-3 py-1 text-xs capitalize", status === s ? "border-primary bg-accent text-accent-foreground" : "border-border text-muted-foreground hover:text-foreground")}>
                  {s.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            <select value={type} onChange={(e) => setType(e.target.value)} aria-label="File type" className="h-9 rounded-md border border-input bg-background px-2 text-sm">
              {TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
            </select>
          </div>
          {error && <div className="border-b border-border bg-destructive/5 px-4 py-2 text-sm text-destructive">Couldn't load documents: {error}</div>}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-4 py-2 font-medium">Document</th>
                  <th className="hidden px-4 py-2 font-medium md:table-cell">Type</th>
                  <th className="hidden px-4 py-2 font-medium md:table-cell">Pages</th>
                  <th className="hidden px-4 py-2 font-medium lg:table-cell">Uploaded</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((r) => (
                  <tr key={r.id} className="hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <Link to="/review/$id" params={{ id: r.id }} className="font-medium hover:text-primary">{r.vendor ?? r.filename}</Link>
                      <div className="text-xs text-muted-foreground">{r.filename}</div>
                      {r.error && <div className="mt-1 max-w-md text-xs text-destructive">{r.error}</div>}
                    </td>
                    <td className="hidden px-4 py-3 text-xs uppercase text-muted-foreground md:table-cell">{r.media_type.split("/")[1]}</td>
                    <td className="hidden px-4 py-3 md:table-cell">{r.page_count ?? "—"}</td>
                    <td className="hidden px-4 py-3 text-xs text-muted-foreground lg:table-cell">{fmtDate(r.created_at)}</td>
                    <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3 text-right font-mono">{r.total ?? "—"}</td>
                  </tr>
                ))}
                {!filtered.length && <tr><td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">No documents match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <UploadDrawer open={up} onClose={() => setUp(false)} />
    </div>
  );
}

