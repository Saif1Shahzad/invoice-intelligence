# Vercel review entry point

The current backend uses native Tesseract, an always-running worker, SQLite and page files. Vercel Functions do not provide the persistent filesystem and worker lifecycle that this implementation needs. Do not put its database in Vercel `/tmp` or attempt to run its worker after returning an HTTP response.

This project supports Vercel as the user-facing HTTPS entry point using **external rewrites**, with an HTTPS backend running the supplied container deployment. It creates no Vercel Functions, keeps browser URLs on the Vercel domain and lets the backend enforce authentication and serve the review assets/API. Groq keys remain exclusively on the backend.

1. Deploy the backend using `deploy/README.md` on a host with a persistent volume and an always-running worker. Give it an HTTPS origin, for example `https://invoice-api.example.com`.
2. Run from the project root:

   ```sh
   python scripts/prepare_vercel.py --api-origin https://invoice-api.example.com
   ```

3. Commit the generated routing configuration (no credentials). In Vercel, import the repository, set **Root Directory** to `deploy/vercel`, **Framework** to Other, no build command, and **Output Directory** to `public`. Deploy.
4. Set the backend `INVOICE_PUBLIC_ORIGIN` to your actual Vercel production URL, and keep `INVOICE_ALLOWED_HOSTS` restricted to the backend hostname plus localhost/127.0.0.1. Restart API and worker.
5. Visit Vercel, sign in with the backend account and test upload → worker → source page → review → confirmed export. Test the maximum upload you intend to support on your Vercel plan; external rewrite and request limits are distinct from the backend's 20 MiB limit.

Use one stable production frontend origin. Vercel preview deployments must not automatically gain access to live invoice writes. No wildcard cross-origin policy is enabled. Check backend availability and Groq quota separately; a healthy Vercel URL does not prove the worker is processing.

If all backend execution must also be on Vercel, a further architecture change is required: managed database, durable object storage and a durable external queue/task executor, with OCR delivered as a service. That architecture is not supplied by this routing project. The present backend is intended for a small, reviewed pilot on one persistent host.

References: [Vercel external rewrites](https://vercel.com/docs/routing/rewrites), [function filesystem](https://vercel.com/docs/functions/runtimes), [function limits](https://vercel.com/docs/functions/limitations).
