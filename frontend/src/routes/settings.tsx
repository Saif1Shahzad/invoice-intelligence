import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel } from "@/components/bits";
import { useApp } from "@/lib/app-state";
import { validateBase } from "@/lib/api/client";
import { useStaggerIn } from "@/lib/motion";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — Invoice Intelligence" },
      { name: "description", content: "Backend connection and sample data settings." },
      { property: "og:title", content: "Settings — Invoice Intelligence" },
      { property: "og:description", content: "Backend connection and sample data settings." },
    ],
  }),
  component: Settings,
});

function Settings() {
  const ref = useRef<HTMLDivElement>(null);
  const { apiBase, setApiBase, conn, connError, recheck, resetSample } = useApp();
  const [draft, setDraft] = useState(apiBase);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setDraft(apiBase), [apiBase]);
  useStaggerIn(ref, []);

  const save = () => {
    const e = validateBase(draft, window.location.hostname);
    setErr(e);
    if (!e) setApiBase(draft.trim());
  };

  return (
    <div ref={ref} className="mx-auto max-w-3xl space-y-4">
      <PageHeader title="Settings" />
      <Panel className="space-y-4 p-5">
        <div>
          <h2 className="text-lg">Backend connection</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Enter <code className="rounded bg-muted px-1 font-mono">/</code> to use same-origin <code className="font-mono">/v1</code> routes
            to use this application’s secure processing server. No API keys are entered or stored here.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="/" aria-label="API base" className="font-mono" />
          <Button onClick={save}>Save</Button>
          <Button variant="outline" onClick={() => { setDraft(""); setApiBase(""); setErr(null); }}>Clear</Button>
        </div>
        {err && <p className="text-sm text-destructive">{err}</p>}
        <div className="flex items-center gap-3 rounded-md bg-muted p-3 text-sm">
          <span>Status: <strong>{conn === "unconfigured" ? "Not configured" : conn === "checking" ? "Checking /health…" : conn === "reachable" ? "Reachable" : "Unreachable"}</strong></span>
          {connError && <span className="text-xs text-destructive">{connError}</span>}
          {apiBase && <Button size="sm" variant="ghost" className="ml-auto" onClick={recheck}>Re-check</Button>}
        </div>
        <p className="text-xs text-muted-foreground">Live uploads and reviews require a reachable backend and an authorized reviewer account. Sample mode remains separate.</p>
      </Panel>
      <Panel className="p-5"><h2 className="text-lg">Advanced review</h2><p className="mb-2 text-sm text-muted-foreground">Resolve duplicate pairs, import purchase orders, or reopen a previous decision.</p><a className="text-sm text-primary underline" href="/legacy-review">Open advanced review controls</a></Panel>
      <Panel className="flex items-center justify-between gap-4 p-5">
        <div><h2 className="text-lg">Sample data</h2><p className="text-sm text-muted-foreground">Restore sample records to their original state.</p></div>
        <Button variant="outline" onClick={resetSample}>Reset sample data</Button>
      </Panel>
    </div>
  );
}

