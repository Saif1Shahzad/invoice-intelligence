"""Local Tesseract adapter. OCR scores are not calibrated field probabilities."""
import csv
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from invoice_intelligence.domain.errors import DocumentError


def _run(command, timeout):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              env=os.environ | {"OMP_THREAD_LIMIT": "1"})
    except FileNotFoundError:
        raise DocumentError("ocr_unavailable", "Tesseract is not installed or TESSERACT_CMD is incorrect.") from None
    except subprocess.TimeoutExpired:
        raise DocumentError("ocr_timeout", "OCR exceeded the page time limit.") from None


def _words(tsv, width, height):
    words = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        x, y, w, h = (int(row[k]) for k in ["left", "top", "width", "height"])
        if w <= 0 or h <= 0:
            continue
        box = [max(0.0, x / width), max(0.0, y / height),
               min(1.0, (x + w) / width), min(1.0, (y + h) / height)]
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        words.append({"text": row["text"].strip(), "bbox": box,
                      "recognition_score": float(row["conf"]),
                      "line": [int(row[k]) for k in ["block_num", "par_num", "line_num"]]})
    return words


def _recognize(image, path, options, psm="3"):
    image.save(path, format="PNG")
    result = _run([options["tesseract_cmd"], str(path), "stdout", "-l", options.get("ocr_languages", "eng"),
                   "--psm", psm, "tsv"], options["ocr_timeout"])
    if result.returncode:
        raise DocumentError("ocr_failed", "Tesseract could not read this page. Check English language data.")
    return _words(result.stdout, image.width, image.height)


def recognize(image, options, rotation_hint_cw=None):
    if not shutil.which(options["tesseract_cmd"]):
        raise DocumentError("ocr_unavailable", "Install Tesseract and its English/OSD data, then retry this document.")
    preprocessing=[]
    if options.get("ocr_enhanced",False):
        from PIL import Image,ImageChops
        # Trim only completely black letterboxing, never estimated paper/content boundaries.
        rgb=image.convert('RGB');box=ImageChops.difference(rgb,Image.new('RGB',rgb.size,'black')).getbbox()
        if box and box!=(0,0,*rgb.size):
            image=rgb.crop(box);preprocessing.append('black_letterbox_removed')
        if max(image.size)<1600:
            scale=1600/max(image.size);image=image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
            preprocessing.append('small_page_upscaled')
    with tempfile.TemporaryDirectory(prefix="invoice-ocr-") as temp:
        path = Path(temp) / "page.png"
        image.save(path, format="PNG")
        if rotation_hint_cw is not None:
            # A native PDF text matrix provides a deterministic baseline direction.
            upright = image.rotate(-rotation_hint_cw, expand=True, fillcolor="white")
            words = _recognize(upright, path, options)
            scores = [word["recognition_score"] for word in words if word["recognition_score"] >= 0]
            mean_score = sum(scores) / len(scores) if scores else 0
            lines, previous = [], None
            for word in words:
                if word["line"] != previous:
                    lines.append([])
                    previous = word["line"]
                lines[-1].append(word["text"])
                del word["line"]
            return upright, words, "\n".join(" ".join(line) for line in lines), {
                "rotation_cw": rotation_hint_cw, "orientation_method": "pdf_text_matrix",
                "mean_ocr_score": round(mean_score, 2),
                "warnings": ["low_ocr_score_requires_review"] if mean_score < 60 else []}
        osd = _run([options["tesseract_cmd"], str(path), "stdout", "--psm", "0"], options["ocr_timeout"])
        rotation = re.search(r"Rotate:\s*(0|90|180|270)\b", osd.stdout)
        confidence = re.search(r"Orientation confidence:\s*([\d.]+)", osd.stdout)
        reliable_orientation = osd.returncode == 0 and rotation is not None and confidence is not None and float(confidence[1]) >= 5
        warnings = ["image_preprocessed_verify_source"] if preprocessing else []
        if reliable_orientation:
            angle = int(rotation[1])
            upright = image.rotate(-angle, expand=True, fillcolor="white")
            words = _recognize(upright, path, options)
            orientation_method = "tesseract_osd"
        else:
            # OSD often fails on small receipts. Compare four right-angle readings.
            candidates = []
            for angle in [0, 90, 180, 270]:
                candidate = image.rotate(-angle, expand=True, fillcolor="white")
                words = _recognize(candidate, path, options)
                score = sum(max(0, word["recognition_score"]) * min(len(word["text"]), 12) for word in words)
                candidates.append((score, angle, words))
                candidate.close()
            _, angle, words = max(candidates, key=lambda c: c[0])
            upright = image.rotate(-angle, expand=True, fillcolor="white")
            orientation_method = "four_rotation_heuristic"
            warnings.append("orientation_estimated_requires_review")
        if options.get("ocr_enhanced",False):
            # Sparse receipt layouts often lose entire amount columns under auto segmentation.
            from PIL import ImageOps
            enhanced=ImageOps.autocontrast(upright.convert('L')).convert('RGB')
            alternatives=[(words,upright)]
            for segmentation in ['6','11']:
                alternatives.append((_recognize(enhanced,path,options,segmentation),enhanced))
            def quality(candidate):
                return sum(max(0,w['recognition_score']-30)*min(len(w['text']),12) for w in candidate[0])
            words,chosen=max(alternatives,key=quality)
            if chosen is enhanced:
                upright=enhanced
                warnings.append('ocr_layout_alternative_selected_requires_review')
        valid_scores = [word["recognition_score"] for word in words if word["recognition_score"] >= 0]
        mean_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        if mean_score < 60:
            warnings.append("low_ocr_score_requires_review")
        lines = []
        previous = None
        for word in words:
            if word["line"] != previous:
                lines.append([])
                previous = word["line"]
            lines[-1].append(word["text"])
            del word["line"]
        text = "\n".join(" ".join(line) for line in lines)
        return upright, words, text, {"rotation_cw": angle, "orientation_method": orientation_method,
            "mean_ocr_score": round(mean_score, 2), "preprocessing":preprocessing, "warnings": warnings}
