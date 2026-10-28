"""Isolated PDF/image reader. Never imports dataset labels or extraction models."""
import json
from collections import Counter
import math
from importlib.metadata import version
from pathlib import Path
import sys
import time
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader

from invoice_intelligence.domain.errors import DocumentError


def file_kind(path):
    with open(path, "rb") as file:
        header = file.read(16)
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise DocumentError("unsupported_file", "Only PDF, PNG and JPEG invoice files are supported.", 415)


def inspect(path, options):
    kind = file_kind(path)
    if kind == "application/pdf":
        try:
            reader = PdfReader(path, strict=True)
            if reader.is_encrypted:
                raise DocumentError("encrypted_pdf", "Password-protected PDFs are not supported; upload an unlocked copy.")
            count = len(reader.pages)
            if count == 0:
                raise DocumentError("empty_pdf", "This PDF has no pages.")
            if count > options["max_pages"]:
                raise DocumentError("too_many_pages", f"Maximum {options['max_pages']} pages per file.", 413)
            for page in reader.pages:
                width, height = float(page.mediabox.width), float(page.mediabox.height)
                user_unit = float(page.get("/UserUnit", 1))
                scale = options["render_dpi"] / 72 * user_unit
                if not all(math.isfinite(v) and v > 0 for v in [width, height, user_unit]):
                    raise DocumentError("invalid_pdf", "Invalid PDF page dimensions.")
                if math.ceil(width * scale) * math.ceil(height * scale) > options["max_pixels"]:
                    raise DocumentError("page_too_large", "PDF page exceeds the rendering pixel limit.", 413)
        except DocumentError:
            raise
        except Exception:
            raise DocumentError("invalid_pdf", "This PDF is malformed or cannot be opened.") from None
        return {"media_type": kind, "page_count": count}
    try:
        Image.MAX_IMAGE_PIXELS = options["max_pixels"]
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.width * image.height > options["max_pixels"]:
                    raise DocumentError("image_too_large", "Image exceeds the pixel limit.", 413)
                if getattr(image, "n_frames", 1) != 1:
                    raise DocumentError("animated_image", "Animated images are not supported.")
                image.verify()
    except DocumentError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise DocumentError("image_too_large", "Image exceeds the pixel limit.", 413) from None
    except Exception:
        raise DocumentError("invalid_image", "This image is malformed or cannot be opened.") from None
    return {"media_type": kind, "page_count": 1}


def pdf_words(page):
    words = []
    for word in page.extract_words():
        x0, y0, x1, y1 = [word["x0"] / page.width, word["top"] / page.height,
                           word["x1"] / page.width, word["bottom"] / page.height]
        box = [max(0, x0), max(0, y0), min(1, x1), min(1, y1)]
        if box[0] < box[2] and box[1] < box[3]:
            words.append({"text": word["text"], "bbox": box, "recognition_score": None})
    return words


def usable_text(text, words):
    return len(words) >= 5 and sum(c.isalnum() for c in text) >= 30 and sum(c.isprintable() or c.isspace() for c in text) / max(1, len(text)) >= .95


def process(path, output_dir, options):
    import pdfplumber
    import pypdfium2 as pdfium
    from invoice_intelligence.ocr.tesseract import recognize

    started = time.monotonic()
    metadata = inspect(path, options)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    pages, document_warnings = [], []
    text_pdf, render_pdf = None, None
    if metadata["media_type"] == "application/pdf":
        text_pdf = pdfplumber.open(path)
        render_pdf = pdfium.PdfDocument(path)
    try:
        total_text = 0
        for index in range(metadata["page_count"]):
            rotation_meta = {"rotation_cw": 0, "orientation_method": "embedded_pdf_text", "mean_ocr_score": None, "warnings": []}
            original_exif = 1
            pdf_rotation = 0
            words, text = [], ""
            rotation_hint = None
            if render_pdf is not None:
                page = text_pdf.pages[index]
                pdf_rotation = int(page.rotation or 0)
                text = page.extract_text() or ""
                words = pdf_words(page)
                chars = [char for char in page.chars if char.get("text", "").strip()]
                baselines = Counter(round(math.degrees(math.atan2(char['matrix'][1], char['matrix'][0])) / 90) * 90 % 360 for char in chars)
                if baselines:
                    angle, count = baselines.most_common(1)[0]
                    if angle and count > len(chars) / 2:
                        rotation_hint = angle
                if rotation_hint is not None or (chars and sum(not char.get("upright", True) for char in chars) > len(chars) / 2):
                    # Embedded text exists but the page is sideways. OCR supplies
                    # upright-page coordinates instead of returning sideways boxes.
                    words, text = [], ""
                render_page = render_pdf[index]
                try:
                    width, height = render_page.get_size()
                    if math.ceil(width * options["render_dpi"] / 72) * math.ceil(height * options["render_dpi"] / 72) > options["max_pixels"]:
                        raise DocumentError("page_too_large", "Rendered PDF exceeds the pixel limit.")
                    bitmap = render_page.render(scale=options["render_dpi"] / 72)
                    try:
                        image = bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                finally:
                    render_page.close()
                # PDF text boxes must share the rendered page's orientation.
                if abs(page.width / page.height - image.width / image.height) > .01:
                    words, text = [], ""
            else:
                with Image.open(path) as original:
                    original_exif = int(original.getexif().get(274, 1))
                    oriented = ImageOps.exif_transpose(original)
                    rgba = oriented.convert("RGBA")
                    image = Image.new("RGB", rgba.size, "white")
                    image.paste(rgba, mask=rgba.getchannel("A"))
                    rgba.close()
                    oriented.close()
            original_size = list(image.size)
            if metadata["media_type"] == "application/pdf" and usable_text(text, words):
                method = "pdf_text"
            else:
                method = "ocr"
                upright, words, text, rotation_meta = recognize(image, options, rotation_hint_cw=rotation_hint)
                image.close()
                image = upright
            try:
                if not words:
                    rotation_meta["warnings"].append("no_readable_text")
                total_text += len(text)
                if total_text > options["max_text_chars"] or len(words) > 50_000:
                    raise DocumentError("text_limit", "Document exceeds the extracted-text limit.")
                for number, word in enumerate(words):
                    word["span_id"] = f"p{index + 1}:w{number + 1}"
                    word["bbox"] = [round(float(v), 6) for v in word["bbox"]]
                name = f"page_{index + 1}.png"
                image.save(output / name)
                (output / name).chmod(0o600)
                pages.append({"page": index + 1, "method": method, "text": text, "words": words,
                    "image_file": name, "width": image.width, "height": image.height,
                    "transform": {"size_before_ocr": original_size, "exif_orientation_applied": original_exif,
                                  "pdf_rotation_applied": pdf_rotation, "ocr_rotation_cw": rotation_meta["rotation_cw"]},
                    "orientation_method": rotation_meta["orientation_method"],
                    "mean_ocr_score": rotation_meta["mean_ocr_score"], "warnings": rotation_meta["warnings"]})
                document_warnings.extend(rotation_meta["warnings"])
            finally:
                image.close()
    finally:
        if text_pdf is not None:
            text_pdf.close()
        if render_pdf is not None:
            render_pdf.close()
    result = {"pipeline_version": "text-v1", "pages": pages, "warnings": sorted(set(document_warnings)),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "engine_versions": {name: version(name) for name in ["pdfplumber", "pypdf", "pypdfium2", "Pillow"]},
        "scope": "Page text only; structured invoice extraction and human confirmation are pending.",
        "ocr_score_notice": "Tesseract recognition scores are heuristics, not calibrated field confidence."}
    if any(page["method"] == "ocr" for page in pages):
        from invoice_intelligence.ocr.tesseract import _run
        result["engine_versions"]["tesseract"] = _run([options["tesseract_cmd"], "--version"], options["ocr_timeout"]).stdout.splitlines()[0]
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False))
    result_path.chmod(0o600)
    return {"status": "needs_review" if document_warnings else "text_ready", "result_file": "result.json"}


def main():
    try:
        request = json.load(sys.stdin)
        result = inspect(request["path"], request["options"]) if request["mode"] == "inspect" else process(request["path"], request["output_dir"], request["options"])
        response = {"ok": True, "result": result}
    except DocumentError as error:
        response = {"ok": False, "error": {"code": error.code, "message": error.message, "status_code": error.status_code}}
    except Exception:
        response = {"ok": False, "error": {"code": "processing_failed", "message": "Document processing failed; no partial result was published.", "status_code": 422}}
    print(json.dumps(response))


if __name__ == "__main__":
    main()
