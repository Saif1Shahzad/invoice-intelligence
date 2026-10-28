"""Isolated structured-extraction stage, with immutable inputs and local output."""
import json
from pathlib import Path
import sys
import time

from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.domain.invoice_validation import validate_extraction
from invoice_intelligence.extraction.local import extract, VERSION, PROVIDER


def process(request):
    started = time.monotonic()
    source = json.loads(Path(request["path"]).read_text())
    if sum(len(page["text"]) for page in source["pages"]) > request["options"]["max_text_chars"]:
        raise DocumentError("extraction_text_limit", "Text exceeds the configured extraction limit.")
    provider=request['options'].get('extraction_provider','local')
    provider_version=VERSION
    usage={"external_requests":0,"input_tokens":None,"output_tokens":None,"provider_cost_usd":"0.00","cost_scope":"Local compute and human labor are not priced."}
    if provider=='groq':
        from invoice_intelligence.extraction.groq import extract as groq_extract
        from invoice_intelligence.extraction.providers import identity
        from invoice_intelligence.config import Settings
        provider_version=identity(Settings(**{k:v for k,v in request['options'].items() if k in Settings.__dataclass_fields__}))[1]
        record,usage=groq_extract(request['document_id'],source,Path(request['path']),request['options'],Path(request['output_dir']))
    else:
        record = extract(request["document_id"], source)
    validation = validate_extraction(record)
    payload = {"extraction": record.model_dump(mode="json"), "validation": validation,
        "provenance": {"provider": provider, "extractor_version": provider_version,
            "source_text_sha256": request["source_digest"], "elapsed_seconds": round(time.monotonic() - started, 4),
            "confidence": "No calibrated probabilities. Source evidence and deterministic checks; human confirmation always required."},
        "usage": usage}
    output = Path(request["output_dir"])
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output / "extraction.json"
    path.write_text(json.dumps(payload, ensure_ascii=False))
    path.chmod(0o600)
    return {"routing": validation["routing"]}


def main():
    try:
        response = {"ok": True, "result": process(json.load(sys.stdin))}
    except DocumentError as error:
        response = {"ok": False, "error": {"code": error.code, "message": error.message, "status_code": error.status_code,"retry_after":error.retry_after}}
    except Exception:
        response = {"ok": False, "error": {"code": "extraction_failed", "message": "Local extraction failed validation; no partial extraction was published.", "status_code": 422}}
    print(json.dumps(response))


if __name__ == "__main__":
    main()
