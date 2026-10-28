# Live backend verification

Deployment: https://invoice-intelligence-theta.vercel.app

The Vercel Container framework is selected, command overrides are disabled, and the configured HTTP port is 8000. PostgreSQL and private Blob storage hold durable records and artifacts. Secrets remain outside GitHub.

## Verified

- 172 backend tests and 14 frontend tests passed before deployment.
- 15 integration checks passed using real Neon PostgreSQL and private Blob storage, including confirmation, audit history and recovery from a fresh cache.
- 11 live HTTP checks passed: authenticated session, built frontend, cloud health, synthetic PDF upload, safe retry, processing, review retrieval, source-page retrieval, original-file recovery, audit history and saved invoices.
- The live extraction job used Groq and succeeded. The invoice remains pending human review.

## Limits

Uploads are limited to 3 pages and 3.5 MB. Keep the workspace open while processing; durable work resumes on return. There is no unattended background worker. Groq account quotas may delay requests.

This verifies deployment functionality with one synthetic invoice. It does not establish general extraction accuracy or replace the previous dataset evaluation. Human confirmation remains required.

Login details are saved locally in `.secrets/LIVE_APP_LOGIN.txt` and are not committed. Standard browsers support the HTTP Basic sign-in prompt; the in-app automated browser could not complete that prompt, so final visual browser verification is outstanding.
