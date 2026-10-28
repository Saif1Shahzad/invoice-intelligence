import hashlib
import os
from pathlib import Path
import re
import tempfile

from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.ingestion.isolated import run_isolated


EXTENSIONS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def signature(header):
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise DocumentError("unsupported_file", "File bytes must identify a PDF, PNG or JPEG.", 415)


def ingest(upload, key, settings, store):
    if key is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise DocumentError("invalid_idempotency_key", "Use 1–128 letters, digits, periods, underscores, colons or hyphens for Idempotency-Key.", 400)
    filename = (upload.filename or "").replace("\\", "/").split("/")[-1]
    if not filename or len(filename) > 240 or any(ord(c) < 32 for c in filename):
        raise DocumentError("invalid_filename", "Provide a valid filename of at most 240 characters.", 400)
    expected = EXTENSIONS.get(Path(filename).suffix.lower())
    if expected is None:
        raise DocumentError("unsupported_extension", "Use a .pdf, .png, .jpg or .jpeg filename.", 415)
    incoming = settings.data_dir / "incoming"
    incoming.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = None
    try:
        hasher = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(dir=incoming, delete=False) as temp:
            path = Path(temp.name)
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise DocumentError("file_too_large", "File exceeds the upload byte limit.", 413)
                hasher.update(chunk)
                temp.write(chunk)
            temp.flush()
            os.fsync(temp.fileno())
        if size == 0:
            raise DocumentError("empty_file", "The uploaded file is empty.", 400)
        with path.open("rb") as file:
            actual = signature(file.read(16))
        if expected != actual:
            raise DocumentError("file_type_mismatch", "Filename extension does not match file contents.", 415)
        if upload.content_type not in [None, "application/octet-stream", actual]:
            raise DocumentError("file_type_mismatch", "Declared Content-Type does not match file contents.", 415)
        digest = hasher.hexdigest()
        existing_id = store.existing(digest, key)
        if existing_id:
            existing = store.document(existing_id)
            return store.register(digest=digest, filename=filename, media_type=actual, size_bytes=size,
                page_count=existing["page_count"], original_key=existing["original_key"], key=key)
        metadata = run_isolated(path, settings)
        suffix = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}[actual]
        original_key = f"objects/{digest}{suffix}"
        destination = settings.data_dir / original_key
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.link(path, destination)
            destination.chmod(0o600)
        except FileExistsError:
            if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise DocumentError("storage_integrity_error", "The stored original failed its integrity check.", 500)
        return store.register(digest=digest, filename=filename, media_type=actual,
            size_bytes=size, page_count=metadata["page_count"], original_key=original_key, key=key)
    finally:
        if path:
            path.unlink(missing_ok=True)


class UploadLimitMiddleware:
    """Bound bodies before multipart parsing; at most file limit + 64 KiB RAM.

    A public deployment also needs reverse-proxy limits and authentication.
    """
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != "/v1/documents":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        chunks, total = [], 0
        limit = self.max_bytes + 64 * 1024
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                return await JSONResponse({"error": {"code": "file_too_large", "message": "Upload body exceeds the byte limit."}}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
