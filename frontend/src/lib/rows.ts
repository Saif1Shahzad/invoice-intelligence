import { useApp } from "./app-state";
import { getField } from "./review";

export interface Row {
  id: string;
  filename: string;
  media_type: string;
  status: string;
  page_count: number | null;
  created_at: string;
  error: string | null;
  vendor?: string | undefined;
  total?: string | undefined;
  revision: number | null;
}

export function useRows(): { rows: Row[]; live: boolean; available: boolean; error: string | null } {
  const { mode, sampleDocs, liveDocs, conn, liveError } = useApp();
  if (mode === "sample") {
    return {
      live: false, available: true, error: null,
      rows: sampleDocs.map((d) => ({
        id: d.id, filename: d.filename, media_type: d.media_type, status: d.status, page_count: d.page_count,
        created_at: d.created_at, error: d.job.error, vendor: getField(d, "vendor")?.value, total: getField(d, "total")?.value,
        revision: d.review.revision,
      })),
    };
  }
  return {
    live: true, available: conn === "reachable", error: liveError,
    rows: liveDocs.map((d) => ({
      id: d.id, filename: d.filename, media_type: d.media_type, status: d.review?.status === "approved" ? "confirmed" : d.review?.status === "rejected" ? "rejected" : d.extraction?.run_id ? "needs_review" : d.job?.status === "failed" ? "failed" : "processing", page_count: d.page_count,
      created_at: d.created_at, error: d.extraction?.job?.error ?? d.job?.error ?? null, revision: d.review?.revision ?? null,
    })),
  };
}

export const fmtDate = (s: string) => {
  const d = new Date(s);
  return isNaN(+d) ? s : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
};

