import type { SampleDoc, Field, LineItem } from "./review";

const f = (key: string, label: string, value: string, bbox: Field["bbox"], verified = false): Field => ({
  key, label, value, extracted: value, verified, page: 1, bbox,
});
const li = (id: string, description: string, qty: number, unitPrice: number, y: number, verified = false): LineItem => ({
  id, description, qty, unitPrice, verified, bbox: [8, y, 84, 4.5],
});

function header(vendor: string, inv: string, date: string, due: string, po: string, sub: string, tax: string, total: string): Field[] {
  return [
    f("vendor", "Vendor", vendor, [8, 6, 45, 6]),
    f("invoice_number", "Invoice no.", inv, [62, 8, 30, 4]),
    f("invoice_date", "Invoice date", date, [62, 13, 30, 4]),
    f("due_date", "Due date", due, [62, 18, 30, 4]),
    f("po_number", "PO number", po, [62, 23, 30, 4]),
    f("currency", "Currency", "USD", [8, 23, 20, 4]),
    f("subtotal", "Subtotal", sub, [60, 68, 32, 4]),
    f("tax", "Tax", tax, [60, 73, 32, 4]),
    f("total", "Total", total, [60, 79, 32, 5]),
  ];
}

export function makeSampleDocs(): SampleDoc[] {
  return [
    {
      id: "smp-1042", filename: "northwind-INV-20931.pdf", media_type: "application/pdf", status: "needs_review",
      page_count: 1, created_at: "2026-10-27T09:12:00Z", job: { status: "succeeded", error: null },
      review: { status: "pending", revision: 2 },
      fields: header("Northwind Office Supply", "INV-20931", "2026-10-20", "2026-11-19", "PO-7781", "1,240.00", "102.30", "1,342.30"),
      lineItems: [li("a", "Ergonomic chair, mesh", 4, 210, 38), li("b", "Monitor arm, dual", 4, 85, 44), li("c", "Desk mat, felt", 8, 12.5, 50)],
      taxRate: 8.25, taxBBox: [60, 73, 32, 4], holds: {},
      matching: { po: "PO-7781", poTotal: 1342.3, receipt: "GRN-3310" },
      history: [
        { revision: 1, at: "2026-10-27T09:13:00Z", actor: "extraction", summary: "Initial extraction proposed 9 headers, 3 line items" },
        { revision: 2, at: "2026-10-27T10:02:00Z", actor: "m.chen", summary: "Edited Due date 2026-11-09 → 2026-11-19" },
      ],
    },
    {
      id: "smp-1043", filename: "acme-freight-0098.png", media_type: "image/png", status: "needs_review",
      page_count: 1, created_at: "2026-10-27T11:40:00Z", job: { status: "succeeded", error: null },
      review: { status: "pending", revision: 1 },
      fields: header("Acme Freight Co.", "AF-0098", "2026-10-22", "2026-11-05", "PO-7790", "860.00", "70.95", "940.95"),
      lineItems: [li("a", "LTL freight, Zone 4", 1, 720, 38), li("b", "Liftgate fee", 1, 90, 44), li("c", "Fuel surcharge", 1, 40, 50)],
      taxRate: 8.25, taxBBox: [60, 73, 32, 4], holds: { duplicateOf: "smp-0987 (AF-0098, same vendor & total)" },
      matching: { po: "PO-7790", poTotal: 850, receipt: null },
      history: [{ revision: 1, at: "2026-10-27T11:41:00Z", actor: "extraction", summary: "Initial extraction" }],
    },
    {
      id: "smp-1044", filename: "receipt-cafe-lumen.jpeg", media_type: "image/jpeg", status: "needs_review",
      page_count: 1, created_at: "2026-10-28T08:05:00Z", job: { status: "succeeded", error: null },
      review: { status: "pending", revision: 1 },
      fields: header("Café Lumen", "R-55120", "2026-10-26", "2026-10-26", "", "64.00", "5.28", "69.28"),
      lineItems: [li("a", "Team breakfast platter", 2, 28, 38), li("b", "Coffee carafe", 1, 8, 44)],
      taxRate: 8.25, taxBBox: [60, 73, 32, 4], holds: { poIssue: "No PO number on receipt; expense policy requires one over $50" },
      matching: { po: null, poTotal: null, receipt: null },
      history: [{ revision: 1, at: "2026-10-28T08:06:00Z", actor: "extraction", summary: "Initial extraction" }],
    },
    {
      id: "smp-1039", filename: "globex-INV-7765.pdf", media_type: "application/pdf", status: "confirmed",
      page_count: 2, created_at: "2026-10-25T14:22:00Z", job: { status: "succeeded", error: null },
      review: { status: "confirmed", revision: 3 },
      fields: header("Globex Industrial", "INV-7765", "2026-10-18", "2026-11-17", "PO-7712", "3,200.00", "264.00", "3,464.00").map((x) => ({ ...x, verified: true })),
      lineItems: [li("a", "Hydraulic fittings kit", 10, 320, 38, true)],
      taxRate: 8.25, taxBBox: [60, 73, 32, 4], holds: {},
      matching: { po: "PO-7712", poTotal: 3464, receipt: "GRN-3290" },
      history: [
        { revision: 1, at: "2026-10-25T14:23:00Z", actor: "extraction", summary: "Initial extraction" },
        { revision: 2, at: "2026-10-25T15:00:00Z", actor: "a.ruiz", summary: "Verified all fields" },
        { revision: 3, at: "2026-10-25T15:01:00Z", actor: "a.ruiz", summary: "Confirmed" },
      ],
    },
    {
      id: "smp-1040", filename: "initech-scan-blurry.jpeg", media_type: "image/jpeg", status: "failed",
      page_count: 1, created_at: "2026-10-26T16:30:00Z",
      job: { status: "failed", error: "OCR produced no readable text (image too low-resolution). Re-scan at 300 DPI and upload again." },
      review: { status: "none", revision: 0 }, fields: [], lineItems: [], taxRate: 0, taxBBox: [0, 0, 0, 0], holds: {},
      matching: { po: null, poTotal: null, receipt: null }, history: [],
    },
    {
      id: "smp-1041", filename: "umbrella-INV-311.pdf", media_type: "application/pdf", status: "rejected",
      page_count: 1, created_at: "2026-10-26T17:10:00Z", job: { status: "succeeded", error: null },
      review: { status: "rejected", revision: 2 },
      fields: header("Umbrella Services", "INV-311", "2026-10-01", "2026-10-31", "PO-7600", "500.00", "41.25", "541.25"),
      lineItems: [li("a", "Consulting retainer", 1, 500, 38)],
      taxRate: 8.25, taxBBox: [60, 73, 32, 4], holds: {},
      matching: { po: "PO-7600", poTotal: 541.25, receipt: null },
      history: [
        { revision: 1, at: "2026-10-26T17:11:00Z", actor: "extraction", summary: "Initial extraction" },
        { revision: 2, at: "2026-10-26T17:40:00Z", actor: "m.chen", summary: "Rejected: services not rendered this period" },
      ],
    },
    {
      id: "smp-1045", filename: "contoso-INV-4410.pdf", media_type: "application/pdf", status: "processing",
      page_count: 3, created_at: "2026-10-28T10:58:00Z", job: { status: "running", error: null },
      review: { status: "none", revision: 0 }, fields: [], lineItems: [], taxRate: 0, taxBBox: [0, 0, 0, 0], holds: {},
      matching: { po: null, poTotal: null, receipt: null }, history: [],
    },
  ];
}

