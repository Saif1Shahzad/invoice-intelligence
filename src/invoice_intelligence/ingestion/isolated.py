"""Run parsing/rendering/OCR outside API/worker processes with a hard deadline."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from invoice_intelligence.domain.errors import DocumentError


def run_isolated(path, settings, *, mode="inspect", output_dir=None,
                 module="invoice_intelligence.ingestion.pipeline", **extra):
    request = {"path": str(path), "mode": mode, "options": settings.child_options(),
               "output_dir": str(output_dir) if output_dir else None, **extra}
    env = os.environ.copy()
    # Native file parsers/OCR do not need provider or account secrets.
    for name in list(env):
        if name.endswith(('_API_KEY','_TOKEN','_PASSWORD','_SECRET')):
            if not (mode=='extract' and settings.extraction_provider=='groq' and name=='GROQ_API_KEY'):
                env.pop(name,None)
    package_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.Popen([sys.executable, "-m", module],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True, env=env)
    def stop():
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.communicate()

    try:
        stdout, _ = process.communicate(json.dumps(request), timeout=settings.inspect_timeout if mode == "inspect" else settings.process_timeout)
    except subprocess.TimeoutExpired:
        # Also stop OCR grandchildren, not just the PDF parser process.
        stop()
        raise DocumentError("processing_timeout", "The document exceeded the processing time limit.") from None
    except BaseException:
        stop()
        raise
    if process.returncode:
        raise DocumentError("parser_failed", "The isolated document parser failed; no partial result was published.")
    try:
        result = json.loads(stdout)
    except ValueError:
        raise DocumentError("parser_failed", "The document parser returned an invalid result.") from None
    if not result["ok"]:
        raise DocumentError(**result["error"])
    return result["result"]
