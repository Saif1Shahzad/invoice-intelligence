"""Durable single-worker entry point. Restart-safe claims with bounded attempts."""
import argparse
import hashlib
import json
import time

from invoice_intelligence.config import Settings
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.ingestion.isolated import run_isolated
from invoice_intelligence.persistence.store import Store


def run_once(settings, store=None):
    if store is None:
        store = Store(settings)
        store.initialize()
    if settings.extraction_provider in {"local", "groq"}:
        from invoice_intelligence.extraction.worker import run_extraction_once
        extraction = run_extraction_once(settings, store)
        if extraction:
            return extraction
    job = store.claim()
    if job is None:
        return None
    started = time.monotonic()
    document = store.document(job["document_id"])
    output_key = f"artifacts/{document['id']}/{job['lease_token']}"
    try:
        original = settings.data_dir / document["original_key"]
        if not original.exists() or hashlib.sha256(original.read_bytes()).hexdigest() != document["sha256"]:
            raise DocumentError("original_integrity_error", "Original file is missing or differs from its stored digest.")
        result = run_isolated(original, settings, mode="process", output_dir=settings.data_dir / output_key)
        committed = store.finish(job, result_key=f"{output_key}/result.json", status=result["status"], elapsed=time.monotonic() - started)
        status = result["status"] if committed else "superseded"
    except DocumentError as error:
        store.finish(job, error=error, elapsed=time.monotonic() - started)
        status = "failed"
    except Exception:
        store.finish(job, error=DocumentError("worker_failed", "Processing failed; retry after checking local configuration."), elapsed=time.monotonic() - started)
        status = "failed"
    if status in {"text_ready", "needs_review"} and settings.extraction_provider in {"local", "groq"}:
        from invoice_intelligence.persistence.extractions import ExtractionStore
        ExtractionStore(store).enqueue(document["id"])
    return {"document_id": document["id"], "stage": "text", "attempt": job["attempts"], "status": status}


def main():
    parser = argparse.ArgumentParser(description="Process queued text and structured-extraction jobs")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    args = parser.parse_args()
    settings = Settings.from_env()
    store = Store(settings)
    store.initialize()
    if args.once:
        print(json.dumps(run_once(settings, store) or {"status": "idle"}))
        return
    print("Invoice text/extraction worker running. Ctrl+C to stop.", flush=True)
    try:
        from invoice_intelligence.workers.heartbeat import heartbeat
        with heartbeat(store):
            while True:
                result = run_once(settings, store)
                if result:
                    print(json.dumps(result), flush=True)
                else:
                    time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
