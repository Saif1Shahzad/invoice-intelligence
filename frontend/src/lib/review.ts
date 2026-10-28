export type BBox = [number, number, number, number]; // x, y, w, h in % of page

export interface Field {
  key: string;
  label: string;
  value: string;
  extracted: string; // original proposed value
  verified: boolean;
  page: number;
  bbox: BBox;
}

export interface LineItem {
  id: string;
  description: string;
  qty: number;
  unitPrice: number;
  verified: boolean;
  bbox: BBox;
}

export interface Revision {
  revision: number;
  at: string;
  actor: string;
  summary: string;
}

export interface SampleDoc {
  id: string;
  filename: string;
  media_type: string;
  status: "queued" | "processing" | "needs_review" | "confirmed" | "rejected" | "failed";
  page_count: number;
  created_at: string;
  job: { status: string; error: string | null };
  review: { status: string; revision: number };
  fields: Field[];
  lineItems: LineItem[];
  taxRate: number; // percent
  taxBBox: BBox;
  holds: { duplicateOf?: string; poIssue?: string };
  matching: { po: string | null; poTotal: number | null; receipt: string | null };
  history: Revision[];
}

export const money = (n: number, cur = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: cur }).format(isFinite(n) ? n : 0);

export const num = (s: string) => {
  const n = parseFloat(s.replace(/[^0-9.-]/g, ""));
  return isFinite(n) ? n : NaN;
};

export const getField = (d: SampleDoc, key: string) => d.fields.find((f) => f.key === key);

export function totals(d: SampleDoc) {
  const lineSum = round(d.lineItems.reduce((s, l) => s + l.qty * l.unitPrice, 0));
  const subtotal = num(getField(d, "subtotal")?.value ?? "");
  const tax = num(getField(d, "tax")?.value ?? "");
  const total = num(getField(d, "total")?.value ?? "");
  const expectedTax = round((subtotal * d.taxRate) / 100);
  return {
    lineSum,
    subtotal,
    tax,
    total,
    expectedTax,
    lineMatches: Math.abs(lineSum - subtotal) < 0.01,
    taxMatches: Math.abs(expectedTax - tax) < 0.01,
    totalMatches: Math.abs(round(subtotal + tax) - total) < 0.01,
  };
}

const round = (n: number) => Math.round(n * 100) / 100;

export function blockers(d: SampleDoc): string[] {
  const out: string[] = [];
  const unverified = d.fields.filter((f) => !f.verified).length + d.lineItems.filter((l) => !l.verified).length;
  if (unverified) out.push(`${unverified} field${unverified > 1 ? "s" : ""} not yet verified against source`);
  const t = totals(d);
  if (!t.lineMatches) out.push(`Line items (${money(t.lineSum)}) don't add up to subtotal (${money(t.subtotal)})`);
  if (!t.taxMatches) out.push(`Tax ${money(t.tax)} differs from ${d.taxRate}% of subtotal (${money(t.expectedTax)})`);
  if (!t.totalMatches) out.push(`Subtotal + tax doesn't equal total`);
  if (d.holds.duplicateOf) out.push(`Duplicate hold: possible duplicate of ${d.holds.duplicateOf}`);
  if (d.holds.poIssue) out.push(`PO hold: ${d.holds.poIssue}`);
  return out;
}

/** Confirm requires zero blockers. Reject is always allowed but needs a reason. */
export const canConfirm = (d: SampleDoc) => d.status === "needs_review" && blockers(d).length === 0;
export const canReject = (d: SampleDoc, reason: string) => d.status === "needs_review" && reason.trim().length > 0;

export function summarize(docs: { status: string }[]) {
  const c = { total: docs.length, needs_review: 0, confirmed: 0, rejected: 0, processing: 0, failed: 0 };
  for (const d of docs) {
    if (d.status === "needs_review") c.needs_review++;
    else if (d.status === "confirmed") c.confirmed++;
    else if (d.status === "rejected") c.rejected++;
    else if (d.status === "failed") c.failed++;
    else c.processing++;
  }
  return c;
}

