# Backend build package

This wheel contains the Python source from this repository and lets the existing Vercel project build the combined application with Root Directory `frontend`. It contains no invoices, credentials or runtime files.

Rebuild after backend edits with `uv build --wheel --out-dir frontend/vendor` from the repository root. The Python source in `src/invoice_intelligence` remains authoritative. The frontend Dockerfile installs this package and its cloud dependencies, then runs FastAPI alongside the compiled frontend in a single container.
