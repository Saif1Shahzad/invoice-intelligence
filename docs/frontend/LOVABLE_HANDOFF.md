# Interactive frontend build

Lovable project: https://lovable.dev/projects/ad1cacdf-a9e6-447d-b732-770b7d3d2853

Requested: React/TypeScript review workspace with Anime.js v4, accessible reduced-motion support, responsive document queue, source evidence, human verification, matching and audit history. Existing Python backend remains authoritative.

GitHub then Vercel publication is authorized by the user. Account connections were initiated; do not publish until active connections are verified. Keep .env, web_data, data, reports, .secrets and backups out of uploaded source. Never expose GROQ_API_KEY to frontend code or Vercel public environment variables.

## API corrections and contract

- List: GET /v1/documents?limit=50&offset=0 returns {documents:[...]} (no total count). Paginate before showing whole-system totals; otherwise label counts as loaded records.
- Upload: POST /v1/documents, multipart `file`; optional Idempotency-Key header. 202 new, 200 reused.
- Review: GET /v1/documents/{id}/review.
- Save: **PATCH**, not PUT, /v1/documents/{id}/review.
- Save body: {expected_revision, actor, reason, fields: {headerName: string|null}, verified_fields: ["supplier_name", "line_items[0].amount"], line_items?: [{source_index:number|null,description,sku,quantity,unit_price,amount,discount_amount,tax_rate}], taxes?:[{source_index:number|null,rate,amount}]}.
- Decision: POST /v1/documents/{id}/review/decision with {expected_revision,actor,reason,decision:"approved"|"rejected",acknowledge_warnings:false,matching_token,acknowledge_po_exception:false}.
- Review response: {document_id,revision,current_revision,status,source_run_id,newer_candidate_available,fields,validation,confirmation:{allowed,blockers,warning_count},matching,pages:[{page,method,image_url}],actor,reason,created_at,...}.
- fields is an InvoiceExtraction object. Individual field: {value,status,reason,evidence:[{page,bbox:[x0,y0,x1,y1],text,method,span_ids}]}; boxes normalized to upright image. `proposed` always requires explicit source verification. Editing and saving alone must not mark unchanged proposals verified.
- Matching is live. Use backend confirmation and matching blockers; never infer approval eligibility from a frontend confidence score.
- Review history: GET /v1/documents/{id}/review/history returns {revisions:[...]}.
- 409 revision conflicts: preserve draft, ask user to reload/reconcile, never blindly retry.
- 401/403: show sign-in/role problem. No API keys in browser. Same-origin authenticated requests through a restricted backend rewrite.

## Hosting

Vercel hosts the frontend only. This backend requires native OCR, a durable worker and persistent SQLite/files on a separate HTTPS host. No backend host exists yet. Demo mode must be clearly labeled; live mutations remain disabled until connected. No fake live processing or accuracy statistics.

The initial Lovable prompt accidentally listed PUT for review; the correct contract above supersedes it and must be supplied before accepting the integration.
