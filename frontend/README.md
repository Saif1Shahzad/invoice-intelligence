# Invoice Intelligence frontend

Interactive React / TypeScript frontend designed in Lovable and completed locally. Anime.js 4 provides scoped entrance animations, an upload drawer transition and source-field feedback. Reduced-motion preferences are respected.

## Run

Use Node.js 22.12+ or 24 LTS. From `frontend`, run `npm ci`, then `npm run dev`. The development server proxies `/v1` and `/health` to the local Python backend at port 8000. Sample mode works without a backend. Build with `npm run build`, and run policy/adapter tests with `npm test`.

The frontend uses Vite and TanStack Router as a static SPA. The initial Lovable TanStack Start scaffold was adapted for static hosting; no frontend server or database is required.

## What works

- Responsive overview, searchable and filterable documents, review queue, matching, audit and settings.
- Clearly labeled sample mode. Sample actions are in-memory only and never written to the backend; source pages are illustrative renderings, not real scans.
- Live API adapter: upload, document list, original source pages, normalized evidence highlights, editable headers/items/taxes, explicit proposal verification, save/revalidate, confirm/reject, revision history and confirmed exports.
- Server validation is authoritative. Confirmation is disabled for dirty drafts, stale candidates, conflicts, unauthorized accounts, unresolved blockers or missing acknowledgements.
- Duplicate pair decisions, PO imports, rebase/reopen and review timers remain in the existing backend review UI. The new frontend displays those findings but does not yet replace every administrative control.
- Live counts represent the 50 loaded records; they are not whole-database totals. Live matching is currently read-only and audit history is available within each invoice.

## Deploy after GitHub

In Vercel import `Saif1Shahzad/invoice-intelligence`, select `frontend` as Root Directory, Vite framework, `npm ci` install, `npm run build`, and `dist` output. No Groq key belongs in this frontend or its public environment.

Initially the deployed site is a sample-mode frontend. Real processing needs the Python API, Tesseract, worker and persistent storage on a separate HTTPS host. Deploy that backend using `../deploy/README.md`. Add explicit Vercel external rewrites for `/v1/:path*` and `/health` before the SPA fallback. Set the backend's `INVOICE_PUBLIC_ORIGIN` to the Vercel production origin and configure allowed hosts/accounts. Then select Backend and save `/` in connection settings. Authentication uses the existing same-origin backend session; arbitrary browser-entered backend URLs are rejected.

The generated `vercel.json` deliberately excludes `/v1` and `/health` from the SPA fallback so an absent backend cannot look healthy. Do not deploy the Python SQLite database to Vercel temporary storage. See `../deploy/vercel/README.md` for the backend's original proxy entry point; for this new frontend use Root Directory `frontend` instead.

Lovable design source: https://lovable.dev/projects/ad1cacdf-a9e6-447d-b732-770b7d3d2853 . The GitHub copy includes local build and contract fixes; automatic synchronization with Lovable is not configured.
