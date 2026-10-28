> Schedule update: follow [the one-week delivery plan](ONE_WEEK_PLAN.md) for the October 28 portfolio target. The original sprint below is retained for reference.

# First sprint: first 10 working days

1. Day 1: agree on canonical nullable fields, currency precision, evidence coordinates and state transitions. Review the starter contracts before extending them.
2. Days 2–3: create three development-only supplier templates and ten verified PDFs; reserve held-out families in a manifest. Add labels and deterministic corruptions.
3. Days 3–4: add PostgreSQL migrations for documents, jobs and extraction runs; implement file storage and upload limits. Test concurrent exact uploads and idempotency-key conflicts.
4. Days 5–6: implement PDF rendering/orientation and one OCR adapter; persist word boxes and transforms. Verify highlighted boxes on a rotated page.
5. Days 7–8: connect one structured extraction adapter; preserve nulls, raw outputs and field evidence. Record request usage and latency.
6. Days 9–10: wire the worker and result endpoint; exercise a clean invoice, unreadable page and worker crash/retry. Manually inspect extracted line items and source locations.

Sprint exit: upload one invoice and retrieve stored structured output, evidence, validation reasons and stage costs. Reupload/retry it without creating a second document. No auto-readiness policy until calibration is implemented. The health endpoint alone does not satisfy this milestone.
