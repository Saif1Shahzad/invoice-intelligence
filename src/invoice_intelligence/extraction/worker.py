import hashlib
import time

from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.ingestion.isolated import run_isolated
from invoice_intelligence.persistence.extractions import ExtractionStore


def run_extraction_once(settings, store, document_id=None):
    extraction_store = ExtractionStore(store)
    extraction_store.discover()
    job = extraction_store.claim(document_id)
    if job is None:
        return None
    started = time.monotonic()
    key = f"extractions/{job['document_id']}/{job['lease_token']}"
    try:
        source = store.hydrate_source(job["source_key"])
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != job["source_digest"]:
            raise DocumentError("text_integrity_error", "Text input is missing or changed since extraction was queued.")
        result = run_isolated(source,settings,mode="extract",module="invoice_intelligence.extraction.pipeline",
            output_dir=settings.data_dir/key,document_id=job["document_id"],source_digest=job["source_digest"])
        committed = extraction_store.finish(job,result_key=f"{key}/extraction.json",elapsed=time.monotonic()-started)
        status = result["routing"] if committed else "superseded"
    except DocumentError as error:
        committed = extraction_store.finish(job,error=error,elapsed=time.monotonic()-started)
        status = ("queued" if error.code=="groq_rate_limit" and job["attempts"]<settings.max_attempts else "failed") if committed else "superseded"
    except Exception:
        extraction_store.finish(job,error=DocumentError("extraction_failed","Local extraction failed; saved page text is unchanged."),elapsed=time.monotonic()-started)
        status = "failed"
    return {"document_id":job["document_id"],"stage":"extraction","attempt":job["attempts"],"status":status}
