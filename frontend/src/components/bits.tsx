import type { ReactNode } from "react";
import { PlugZap } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { useApp } from "@/lib/app-state";

const tone: Record<string, string> = {
  needs_review: "bg-warning-soft text-warning-foreground border-warning/40",
  confirmed: "bg-success-soft text-success border-success/40",
  rejected: "bg-muted text-muted-foreground border-border",
  failed: "bg-destructive/10 text-destructive border-destructive/30",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize", tone[status] ?? "bg-accent text-accent-foreground border-primary/20")}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div data-anim className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl text-foreground md:text-3xl">{title}</h1>
        {sub && <p className="mt-1 text-sm text-muted-foreground">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <div data-anim className={cn("rounded-lg border border-border bg-card", className)}>{children}</div>;
}

export function BackendNotConnected({ what }: { what?: string }) {
  const { conn, connError } = useApp();
  return (
    <Panel className="flex flex-col items-start gap-3 p-6">
      <PlugZap className="h-6 w-6 text-muted-foreground" />
      <div>
        <h2 className="text-lg">Backend not connected</h2>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          {conn === "unconfigured"
            ? "No API connection is configured. "
            : `The configured API didn't respond to /health${connError ? ` (${connError})` : ""}. `}
          {what ?? "Live data"} is unavailable until the backend is reachable. Switch to Sample data to explore the workspace.
        </p>
      </div>
      <Link to="/settings" className="text-sm font-medium text-primary underline-offset-4 hover:underline">Open connection settings</Link>
    </Panel>
  );
}

