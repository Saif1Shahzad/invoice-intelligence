# Reviewed pilot deployment (version 1.1)

The app remains a human-reviewed accounting aid. It does not post entries or pay invoices. The backend must run on persistent storage; Vercel can provide the user-facing routing project described in `vercel/README.md`.

## Local start

Copy `.env.example` to `.env` only if you do not already have a local `.env`. Configure the key locally. The one-command launcher reads it automatically; existing shell variables take precedence.

```sh
source .venv/bin/activate
python -m invoice_intelligence serve --port 8000
```

New uploads use the selected provider. Groq sends the processed page images and OCR text to Groq. Existing historical documents are not automatically sent to Groq; request a new extraction explicitly. Original candidates and review revisions remain immutable.

## Accounts

```sh
python -m invoice_intelligence.accounts saif --role admin
python -m invoice_intelligence.accounts reviewer1 --role reviewer
python -m invoice_intelligence.accounts viewer1 --role viewer
```

Passwords are entered using a hidden prompt. Only salted scrypt hashes are stored in `.secrets/accounts.json`, excluded from Git. Viewer accounts cannot write; reviewers may review/upload; only admins import POs. All accounts share this team's document collection: this is not tenant isolation. Authenticated account names override user-supplied audit actor names. Restart API after account changes. Use HTTPS outside localhost. Browser Basic authentication caches credentials; use a separate browser profile for separate roles and close its sessions when signing out.

Set `INVOICE_AUTH_FILE=./.secrets/accounts.json` in local `.env` to enable authentication locally.

## Persistent container host

Prerequisites: Linux host with Docker Compose, a domain pointing at the host, ports 80/443 available, persistent encrypted disk, and outbound access to Groq. Choose a small single-team pilot; SQLite is not a multi-host database.

1. Copy `deploy/production.env.example` to the root `.env.production`. Configure the actual backend domain, canonical review origin, and Groq key there. Set mode 600. Do not copy local or downloaded invoice folders into the image.
2. Create accounts as above. On Linux, the container runs UID 10001; arrange for `.secrets/accounts.json` to be readable by UID 10001 only (for example, server administrator sets its ownership to 10001 and mode 600). Keep the account directory owned by UID 10001 and mode 700 as well, so the container can traverse it. On the deployment server an administrator can set `chown -R 10001:10001 .secrets`, `chmod 700 .secrets` and `chmod 600 .secrets/accounts.json`; do not run these ownership changes on your development Mac. Never commit it.
3. Run:

   ```sh
   docker compose --env-file .env.production -f deploy/compose.yml up -d --build
   ```

Only Caddy exposes network ports. API and worker share a persistent volume. Containers run without root/capabilities, with read-only root filesystems and private temporary storage. Caddy terminates HTTPS. Groq credentials are runtime settings, not image layers. Restrict access to Docker and the host because administrators can inspect container environment settings.

4. Check Caddy's certificate, sign in, check the worker indicator, upload a public sample, verify source evidence, correct/confirm it and inspect the export. Confirm unauthenticated users cannot access document/file/export routes. Do not expose the API's internal port directly.

For Vercel: `INVOICE_DOMAIN` is the backend domain; `INVOICE_PUBLIC_ORIGIN` is the stable Vercel frontend URL. Use the Vercel routing generator only after the backend is reachable over HTTPS.

## Operations

- `/livez` is minimal unauthenticated liveness when accounts are enabled.
- Authenticated `/health` reports DB availability, provider/model, job counts and worker heartbeat. Treat worker inactive >20 seconds or sustained queued/failed jobs as an alert requiring investigation.
- Groq requests are paced by `GROQ_MIN_INTERVAL` (default 65 seconds). HTTP 429 creates a delayed durable retry, up to the attempt limit; malformed/truncated responses and ambiguous network failures are never approved or silently replaced by local extraction.
- `GROQ_DOCUMENT_BUDGET_USD` bounds estimated request costs per attempt. Timeouts, provider billing differences and explicit retries can incur additional charges; configure an account-level Groq spend limit too. These estimates are not a billing guarantee.
- Production startup fails without accounts and an HTTPS public origin. Allowed hosts and write origins are explicit. Keep the host, Python dependencies and image updated. Authentication rate limiting is per process; add perimeter controls if exposed to many users.
- No backups, invoices, extracted values, keys or API response logs belong in the public repository. `web_data`, data, reports, `.env.*`, backups and `.secrets` are ignored. Backup storage and disks must be encrypted by the hosting platform; the app does not implement disk encryption.

## Verified offline backup/restore

Stop **both API and worker** first. For the local runtime:

```sh
python -m invoice_intelligence.backup backup data/runtime backups/2026-10-28 --offline
python -m invoice_intelligence.backup restore backups/2026-10-28 data/restored-runtime --offline
```

Backups include the SQLite snapshot plus all originals/page/extraction artifacts and a SHA-256 manifest. Restore refuses existing destinations and modified contents. Keep `.env.production` and account hashes in a separate protected secret backup. For containers, stop app/worker and run the backup command with the data and backup volumes mounted; restart both after backup. Test a restore before relying on backups.

## Deployment status

Container configuration and local checks are supplied. A live deployment still requires your backend host, domain and account setup. Docker was unavailable in the development environment, so a successful container build is not claimed. Vercel and backend smoke tests must be completed on the chosen host. Full multi-tenant service, automatic accounting posting, PostgreSQL migration and serverless OCR/task storage remain outside this pilot.
