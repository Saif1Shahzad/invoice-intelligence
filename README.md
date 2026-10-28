# Invoice Intelligence 1.1

Human-reviewed invoice and receipt extraction: upload PDF/PNG/JPEG → OCR and Groq vision → source evidence and arithmetic checks → duplicate/PO checks → review → confirmed CSV/JSON export.

The original local rules performed poorly on unfamiliar external documents (13.54% header accuracy and 1.74% line-cell accuracy on a small 16-document test). Version 1.1 adds an opt-in Groq vision provider, receipt/payment fields, explicit verification of vision-only proposals, improved OCR preparation, authenticated pilot deployment and verified backup/restore. Every record still requires human confirmation. Current measured improvement results are available at `/improvement` after evaluation; the earlier narrow benchmark is retained at `/evaluation` as historical evidence, not a current performance claim.

## Start locally

```sh
source .venv/bin/activate
python -m invoice_intelligence serve --port 8000
```

Open http://127.0.0.1:8000/. The launcher starts API and worker together and stops its own processes with Control+C. Control+Z only suspends processes. If the port is occupied, stop the older server or choose a free port.

The app now reads a local `.env` automatically. Existing shell variables take precedence. Copy `.env.example` only if you do not already have `.env`; configure `GROQ_API_KEY` locally and never paste it into chat or commit it. Select `EXTRACTION_PROVIDER=groq` for vision extraction or `local` for the original offline rules. Keys are never sent to the browser. Groq receives uploaded page images and OCR text when selected. Existing documents are not automatically submitted to Groq; use **Extract with configured provider** on a selected record to request a new candidate.

Requires Python 3.11+ and Tesseract with English/OSD data:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
brew install tesseract
```

On Linux install Tesseract using the system package manager. `OCR_LANGUAGES` can select installed language packs. `OCR_ENHANCED=true` enables black-letterbox removal, small-page upscaling, contrast preparation and alternative segmentation. Source highlights refer to the resulting saved upright page, not raw-file pixels.

## Review behavior

Observed values have resolvable OCR/PDF span evidence. **Proposed** values are Groq image readings that OCR does not independently corroborate. They remain visible but block confirmation. Check each against the page, select **Verify against page**, then save with a reason; the resulting correction is attributed to the reviewer. Original source context remains visible and can differ from the proposed/corrected text.

Receipt fields include tip, service fee, previous balance, amount paid and amount due. Invoice total stays separate from payment balances. Decimal checks preserve printed contradictions rather than silently repairing them. Unprinted receipt quantities/prices are not invented. A calculated receipt subtotal is labeled as an arithmetic assumption requiring acknowledgment.

The application preserves bounded uploads/jobs, file-signature checks, exact-byte replay reuse, business duplicate holds, versioned CSV POs, revision conflict protection, immutable candidates and audit history, active review timing, confirmed-only exports and CSV formula protection. Provider model/prompt identity is part of extraction-job reuse. Groq quota failures use paced durable retries; invalid/truncated responses never become approved records.

## Testing and evaluation

```sh
python -m unittest discover -s tests -v
```

Tests cover OCR/validation/review, provider schema/evidence handling, proposal verification, authentication/roles/CSRF, idempotency, exports and backup integrity. Mocked provider tests are distinct from real Groq evaluation. Public downloads, labels, raw responses and local comparison reports stay under ignored `web_data/`.

The original Day 7 benchmark used shared template families and correlated PDF/image variants; its high scores did not generalize to external layouts. See `docs/day7/EVALUATION.md` for that historical scope. Current public-sample evaluation is small and assistant-annotated, not a production reliability guarantee or a human time-saving study. All confidence/readiness policies retain human confirmation.

## Deployment

See [pilot deployment and accounts](deploy/README.md). Viewer/reviewer/admin roles protect shared team data; authenticated account names are bound to audit events. This is a single-team deployment, not multi-tenant isolation.

For **Vercel**, see [Vercel routing setup](deploy/vercel/README.md). The supplied generator creates an external-rewrite entry point to an existing HTTPS backend. The current Tesseract worker, SQLite database and page files need a persistent backend host; putting them in Vercel `/tmp` would lose data. No Groq key is put in the Vercel frontend. A serverless-only architecture would additionally require managed storage/database and a durable task service.

Container files are provided for a persistent single-host pilot with HTTPS, non-root app/worker, shared data volume and restricted host/origin settings. Docker was not installed in the development environment, so the container build must be verified on the chosen host before deployment. Hosting and domains are not provisioned automatically.

## Backup

Stop both API and worker, then:

```sh
python -m invoice_intelligence.backup backup data/runtime backups/2026-10-28 --offline
python -m invoice_intelligence.backup restore backups/2026-10-28 data/restored-runtime --offline
```

Backups include database and evidence artifacts plus hashes. Restore refuses modified backups and existing destinations. Protect backups and secrets using the host's encrypted storage. The app does not implement disk encryption, tax-law compliance, automatic accounting posting, payment execution or a verified labor-saving claim.

## Interactive frontend

The new React / TypeScript interface lives in `frontend/`. It uses Anime.js for responsive transitions, source highlighting and the upload drawer. Run `npm ci` and `npm run dev` from that folder; see `frontend/README.md`. The original FastAPI review interface remains available.

Vercel deployment uses Root Directory `frontend`, framework Vite, build `npm run build`, output `dist`. Until a persistent Python backend is hosted and securely connected, the public frontend runs in clearly labeled sample mode. This frontend deployment alone does not provide hosted OCR or extraction.

