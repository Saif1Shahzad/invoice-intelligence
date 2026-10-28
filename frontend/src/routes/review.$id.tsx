import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, ShieldAlert, X, Lock } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge, BackendNotConnected, Panel } from "@/components/bits";
import { SampleSource, ImageSource, ZoomBar } from "@/components/source-view";
import { useApp } from "@/lib/app-state";
import { blockers, canConfirm, canReject, money, totals, type SampleDoc } from "@/lib/review";
import { LiveReview } from "@/components/live-review";
import type { ApiDocument } from "@/lib/api/types";
import { pulse, useStaggerIn } from "@/lib/motion";
import { fmtDate } from "@/lib/rows";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/review/$id")({
  head: () => ({
    meta: [
      { title: "Review document — Invoice Intelligence" },
      { name: "description", content: "Verify extracted fields against the source document." },
      { property: "og:title", content: "Review document — Invoice Intelligence" },
      { property: "og:description", content: "Verify extracted fields against the source document." },
    ],
  }),
  component: ReviewPage,
});

function ReviewPage() {
  const { id } = Route.useParams();
  const { mode, sampleDocs } = useApp();
  if (mode === "live") return <LiveReview id={id} />;
  const doc = sampleDocs.find((d) => d.id === id);
  if (!doc) return <Panel className="p-8">Sample document not found. <Link to="/review" className="text-primary">Back to queue</Link></Panel>;
  return <SampleReview doc={doc} />;
}

const TABS = ["Headers", "Line items", "Tax & totals", "Reconciliation", "History"] as const;
type Tab = (typeof TABS)[number];

function SampleReview({ doc }: { doc: SampleDoc }) {
  const { updateSample } = useApp();
  const nav = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  const [tab, setTab] = useState<Tab>("Headers");
  const [active, setActive] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [reason, setReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  useStaggerIn(ref, [doc.id]);

  const editable = doc.status === "needs_review";
  const t = totals(doc);
  const b = blockers(doc);

  const log = (summary: string) => (d: SampleDoc): SampleDoc => ({
    ...d,
    review: { ...d.review, revision: d.review.revision + 1 },
    history: [...d.history, { revision: d.review.revision + 1, at: new Date().toISOString(), actor: "you (sample)", summary }],
  });

  const pick = (k: string) => {
    setActive(k);
    if (k.startsWith("li:")) setTab("Line items");
    else if (["subtotal", "tax", "total"].includes(k)) setTab("Tax & totals");
    else setTab("Headers");
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-field="${k}"]`);
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      pulse(el);
    });
  };

  const setField = (key: string, value: string) =>
    updateSample(doc.id, (d) => ({ ...d, fields: d.fields.map((f) => (f.key === key ? { ...f, value, verified: false } : f)) }));
  const commitField = (key: string) => {
    const f = doc.fields.find((x) => x.key === key);
    if (f && f.value !== f.extracted) updateSample(doc.id, log(`Edited ${f.label} → ${f.value}`));
  };
  const verifyField = (key: string) => {
    const f = doc.fields.find((x) => x.key === key)!;
    updateSample(doc.id, (d) => log(`Verified ${f.label}`)({ ...d, fields: d.fields.map((x) => (x.key === key ? { ...x, verified: true } : x)) }));
  };
  const setLine = (lid: string, p: Partial<SampleDoc["lineItems"][number]>) =>
    updateSample(doc.id, (d) => ({ ...d, lineItems: d.lineItems.map((l) => (l.id === lid ? { ...l, ...p, verified: p.verified ?? false } : l)) }));

  const confirm = () => {
    updateSample(doc.id, (d) => log("Confirmed")({ ...d, status: "confirmed", review: { ...d.review, status: "confirmed" } }));
    toast("Confirmed in sample session", { description: "Not saved to any backend." });
    nav({ to: "/review" });
  };
  const reject = () => {
    updateSample(doc.id, (d) => log(`Rejected: ${reason.trim()}`)({ ...d, status: "rejected", review: { ...d.review, status: "rejected" } }));
    toast("Rejected in sample session", { description: "Not saved to any backend." });
    nav({ to: "/review" });
  };

  return (
    <div ref={ref} className="mx-auto max-w-[1500px]">
      <div data-anim className="mb-4 flex flex-wrap items-center gap-3">
        <Link to="/review" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Queue</Link>
        <h1 className="text-xl md:text-2xl">{doc.fields.find((f) => f.key === "vendor")?.value ?? doc.filename}</h1>
        <StatusBadge status={doc.status} />
        <span className="text-xs text-muted-foreground">{doc.filename} · revision {doc.review.revision}</span>
      </div>

      {!doc.fields.length ? (
        <Panel className="p-6 text-sm">
          {doc.job.error ? <p className="text-destructive">Extraction failed: {doc.job.error}</p> : <p className="text-muted-foreground">Extraction is still {doc.job.status}. Fields appear once the job finishes.</p>}
        </Panel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel className="flex h-[55vh] flex-col overflow-hidden lg:sticky lg:top-4 lg:h-[calc(100vh-9rem)]">
            <ZoomBar zoom={zoom} setZoom={setZoom} label={`Source · page 1 of ${doc.page_count} · click a region to jump`} />
            <div className="min-h-0 flex-1"><SampleSource doc={doc} active={active} onPick={pick} zoom={zoom} /></div>
          </Panel>

          <div className="space-y-4">
            <Panel>
              <div role="tablist" className="flex overflow-x-auto border-b border-border">
                {TABS.map((x) => (
                  <button key={x} role="tab" aria-selected={tab === x} onClick={() => setTab(x)}
                    className={cn("whitespace-nowrap border-b-2 px-4 py-2.5 text-sm", tab === x ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                    {x}
                  </button>
                ))}
              </div>
              <div className="p-4">
                {tab === "Headers" && (
                  <div className="space-y-2">
                    {doc.fields.filter((f) => !["subtotal", "tax", "total"].includes(f.key)).map((f) => (
                      <FieldRow key={f.key} f={f} active={active === f.key} editable={editable} onFocus={() => pick(f.key)} onChange={(v) => setField(f.key, v)} onBlur={() => commitField(f.key)} onVerify={() => verifyField(f.key)} />
                    ))}
                  </div>
                )}
                {tab === "Line items" && (
                  <div className="space-y-2">
                    {doc.lineItems.map((l) => (
                      <div key={l.id} data-field={`li:${l.id}`} className={cn("grid grid-cols-12 items-center gap-2 rounded-md border p-2", active === `li:${l.id}` ? "border-primary bg-accent/40" : "border-border")}>
                        <Input className="col-span-12 md:col-span-6" value={l.description} disabled={!editable} onFocus={() => pick(`li:${l.id}`)} onChange={(e) => setLine(l.id, { description: e.target.value })} aria-label="Description" />
                        <Input className="col-span-3 md:col-span-2 font-mono" type="number" value={l.qty} disabled={!editable} onFocus={() => pick(`li:${l.id}`)} onChange={(e) => setLine(l.id, { qty: +e.target.value })} aria-label="Quantity" />
                        <Input className="col-span-5 md:col-span-2 font-mono" type="number" step="0.01" value={l.unitPrice} disabled={!editable} onFocus={() => pick(`li:${l.id}`)} onChange={(e) => setLine(l.id, { unitPrice: +e.target.value })} aria-label="Unit price" />
                        <div className="col-span-4 md:col-span-2 flex justify-end">
                          <VerifyBtn verified={l.verified} disabled={!editable} onClick={() => { setLine(l.id, { verified: true }); updateSample(doc.id, log(`Verified line “${l.description}”`)); }} />
                        </div>
                        <div className="col-span-12 text-right font-mono text-xs text-muted-foreground">= {money(l.qty * l.unitPrice)}</div>
                      </div>
                    ))}
                    <div className="flex justify-between border-t border-border pt-2 text-sm"><span>Line sum</span><span className="font-mono">{money(t.lineSum)}</span></div>
                  </div>
                )}
                {tab === "Tax & totals" && (
                  <div className="space-y-2">
                    {doc.fields.filter((f) => ["subtotal", "tax", "total"].includes(f.key)).map((f) => (
                      <FieldRow key={f.key} f={f} active={active === f.key} editable={editable} mono onFocus={() => pick(f.key)} onChange={(v) => setField(f.key, v)} onBlur={() => commitField(f.key)} onVerify={() => verifyField(f.key)} />
                    ))}
                    <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground">Tax rate applied for checks: {doc.taxRate}% → expected {money(t.expectedTax)}</div>
                  </div>
                )}
                {tab === "Reconciliation" && (
                  <div className="space-y-2 text-sm">
                    <Check2 ok={t.lineMatches} label="Line items sum to subtotal" detail={`${money(t.lineSum)} vs ${money(t.subtotal)}`} />
                    <Check2 ok={t.taxMatches} label={`Tax equals ${doc.taxRate}% of subtotal`} detail={`${money(t.tax)} vs ${money(t.expectedTax)}`} />
                    <Check2 ok={t.totalMatches} label="Subtotal + tax equals total" detail={`${money(t.subtotal + t.tax)} vs ${money(t.total)}`} />
                    <Check2 ok={doc.matching.poTotal === null ? null : Math.abs(doc.matching.poTotal - t.total) < 0.01} label={`PO ${doc.matching.po ?? "—"} amount`} detail={doc.matching.poTotal === null ? "No PO on file" : `${money(doc.matching.poTotal)} vs invoice ${money(t.total)}`} />
                    <Check2 ok={doc.matching.receipt ? true : null} label="Goods receipt" detail={doc.matching.receipt ?? "No receipt linked"} />
                    <Check2 ok={!doc.holds.duplicateOf} label="Duplicate check" detail={doc.holds.duplicateOf ?? "No duplicate detected"} />
                  </div>
                )}
                {tab === "History" && (
                  <ol className="space-y-3 border-l border-border pl-4">
                    {[...doc.history].reverse().map((h) => (
                      <li key={h.revision} className="text-sm">
                        <div className="font-medium">Rev {h.revision} · {h.actor}</div>
                        <div className="text-muted-foreground">{h.summary}</div>
                        <div className="text-[11px] text-muted-foreground">{fmtDate(h.at)}</div>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </Panel>

            <Panel className="p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium"><ShieldAlert className="h-4 w-4 text-warning" />{b.length ? `${b.length} blocker${b.length > 1 ? "s" : ""} before confirm` : "No blockers"}</div>
              {!!b.length && <ul className="mb-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{b.map((x) => <li key={x}>{x}</li>)}</ul>}
              {showReject && (
                <Textarea className="mb-2" placeholder="Reason for rejection (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
              )}
              <div className="flex flex-wrap gap-2">
                <Button disabled={!canConfirm(doc)} onClick={confirm}><Check className="mr-1.5 h-4 w-4" />Confirm</Button>
                {!showReject ? (
                  <Button variant="outline" disabled={!editable} onClick={() => setShowReject(true)}><X className="mr-1.5 h-4 w-4" />Reject…</Button>
                ) : (
                  <Button variant="destructive" disabled={!canReject(doc, reason)} onClick={reject}>Reject document</Button>
                )}
                <span className="self-center text-xs text-muted-foreground">Sample session only — not persisted.</span>
              </div>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

function VerifyBtn({ verified, disabled, onClick }: { verified: boolean; disabled: boolean; onClick: () => void }) {
  return verified ? (
    <span className="inline-flex items-center gap-1 text-xs text-success"><Check className="h-3.5 w-3.5" />Verified</span>
  ) : (
    <Button size="sm" variant="outline" disabled={disabled} onClick={onClick}>Verify against source</Button>
  );
}

function FieldRow({ f, active, editable, mono, onFocus, onChange, onBlur, onVerify }: {
  f: SampleDoc["fields"][number]; active: boolean; editable: boolean; mono?: boolean;
  onFocus: () => void; onChange: (v: string) => void; onBlur: () => void; onVerify: () => void;
}) {
  const edited = f.value !== f.extracted;
  return (
    <div data-field={f.key} className={cn("rounded-md border p-2", active ? "border-primary bg-accent/40" : "border-border")}>
      <div className="mb-1 flex items-center gap-2 text-xs">
        <span className="font-medium text-muted-foreground">{f.label}</span>
        {!f.verified && !edited && <span className="rounded border border-primary/30 px-1.5 text-[10px] uppercase tracking-wide text-primary">Proposed</span>}
        {edited && <span className="rounded border border-warning/40 bg-warning-soft px-1.5 text-[10px] uppercase tracking-wide text-warning-foreground" title={`Extracted: ${f.extracted}`}>Edited</span>}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input className={cn("flex-1", mono && "font-mono")} value={f.value} disabled={!editable} onFocus={onFocus} onBlur={onBlur} onChange={(e) => onChange(e.target.value)} aria-label={f.label} />
        <VerifyBtn verified={f.verified} disabled={!editable} onClick={onVerify} />
      </div>
    </div>
  );
}

function Check2({ ok, label, detail }: { ok: boolean | null; label: string; detail: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border p-2">
      <span className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", ok === null ? "bg-muted-foreground" : ok ? "bg-success" : "bg-destructive")} />
      <div><div>{label}</div><div className="font-mono text-xs text-muted-foreground">{detail}</div></div>
    </div>
  );
}

