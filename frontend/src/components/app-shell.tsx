import { Link, useRouterState } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { FileCheck2, LayoutDashboard, FileText, ListChecks, GitCompareArrows, History, Settings, Menu, X, FlaskConical, Plug } from "lucide-react";
import { useApp } from "@/lib/app-state";
import { AccountControls } from "./public-access";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/review", label: "Review queue", icon: ListChecks },
  { to: "/matching", label: "Matching", icon: GitCompareArrows },
  { to: "/audit", label: "Audit", icon: History },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

function NavList({ onNav }: { onNav?: () => void }) {
  const path = useRouterState({ select: (r) => r.location.pathname });
  return (
    <nav className="flex flex-col gap-0.5">
      {nav.map((n) => {
        const active = n.to === "/" ? path === "/" : path.startsWith(n.to);
        return (
          <Link
            key={n.to}
            to={n.to}
            onClick={(event) => { onNav?.(); if (n.to === '/') { event.preventDefault(); window.location.assign('/?workspace=1'); } }}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/60",
            )}
          >
            <n.icon className={cn("h-4 w-4", active && "text-sidebar-primary")} />
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

function ModeSwitch() {
  const { mode, setMode, conn } = useApp();
  return (
    <div className="rounded-lg border border-sidebar-border p-3 text-xs text-sidebar-foreground">
      <div className="mb-2 uppercase tracking-wider opacity-70">Data source</div>
      <div className="grid grid-cols-2 gap-1 rounded-md bg-sidebar-accent p-1">
        {(["sample", "live"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn("rounded px-2 py-1.5 capitalize", mode === m ? "bg-sidebar-primary text-sidebar-primary-foreground" : "hover:bg-sidebar-border")}
          >
            {m === "sample" ? "Sample" : "Backend"}
          </button>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span className={cn("h-2 w-2 rounded-full", conn === "reachable" ? "bg-success" : conn === "checking" ? "bg-warning" : "bg-destructive")} />
        {conn === "reachable" ? "Backend reachable" : conn === "checking" ? "Checking…" : "Backend not connected"}
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-2">
      <div className="grid h-8 w-8 place-items-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-sm"><FileCheck2 className="h-5 w-5" strokeWidth={1.7}/></div>
      <div className="leading-tight">
        <div className="font-display text-base text-sidebar-accent-foreground">Invoice Intelligence</div>
        <div className="text-[11px] text-sidebar-foreground/70">Human review workspace</div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { mode } = useApp();
  return (
    <div className="flex min-h-screen w-full bg-background">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 bg-sidebar p-4 lg:flex">
        <Brand />
        <NavList />
        <div className="mt-auto"><ModeSwitch /></div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-foreground/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col gap-6 bg-sidebar p-4">
            <div className="flex items-center justify-between"><Brand /><button aria-label="Close menu" onClick={() => setOpen(false)} className="text-sidebar-foreground"><X className="h-5 w-5" /></button></div>
            <NavList onNav={() => setOpen(false)} />
            <div className="mt-auto"><ModeSwitch /></div>
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col"><AccountControls/>
        <header className="flex items-center gap-3 border-b border-border bg-card/70 px-4 py-2.5 backdrop-blur lg:hidden">
          <button aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button>
          <span className="font-display">Invoice Intelligence</span>
        </header>
        {mode === "sample" ? (
          <div className="flex items-center gap-2 border-b border-warning/40 bg-warning-soft px-4 py-2 text-xs text-warning-foreground lg:px-8">
            <FlaskConical className="h-3.5 w-3.5" />
            <strong>Sample data</strong> — illustrative records. Actions here change only this browser session and are never sent to or saved by the backend.
          </div>
        ) : (
          <div className="flex items-center gap-2 border-b border-border bg-accent px-4 py-2 text-xs text-accent-foreground lg:px-8">
            <Plug className="h-3.5 w-3.5" /> <strong>Backend mode</strong> — your saved invoices and reviews. Keep this workspace open while processing; unfinished jobs resume when you return.
          </div>
        )}
        <main className="flex-1 px-4 py-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}

