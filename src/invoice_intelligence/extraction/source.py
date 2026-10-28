"""Reconstruct geometric lines and attach evidence using actual stored spans."""
from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from invoice_intelligence.schemas.extraction import Evidence, ExtractedField


@dataclass(frozen=True)
class Word:
    page: int
    line: int
    span_id: str
    text: str
    bbox: tuple
    method: str


@dataclass
class Line:
    words: list[Word]

    @property
    def text(self):
        return " ".join(word.text for word in self.words)

    def slice(self, start=0, end=None):
        end = len(self.text) if end is None else end
        selected, offset = [], 0
        for word in self.words:
            if offset < end and offset + len(word.text) > start:
                selected.append(word)
            offset += len(word.text) + 1
        return selected


def geometric_lines(result):
    lines = []
    for page in result["pages"]:
        raw = [word for word in page["words"] if word["text"].strip()]
        heights = [word["bbox"][3] - word["bbox"][1] for word in raw]
        tolerance = median(heights) * .6 if heights else .003
        groups = []
        for word in sorted(raw, key=lambda w: ((w["bbox"][1] + w["bbox"][3]) / 2, w["bbox"][0])):
            center = (word["bbox"][1] + word["bbox"][3]) / 2
            if not groups or abs(center - groups[-1][0]) > tolerance:
                groups.append((center, [word]))
            else:
                groups[-1][1].append(word)
        for number, (_, words) in enumerate(groups):
            lines.append(Line([Word(page["page"], number, word["span_id"], word["text"],
                tuple(word["bbox"]), page["method"]) for word in sorted(words, key=lambda w: w["bbox"][0])]))
    return lines


def evidence(words):
    groups = defaultdict(list)
    for word in dict.fromkeys(words):
        groups[(word.page, word.line)].append(word)
    spans = []
    for (page, _), group in sorted(groups.items()):
        group.sort(key=lambda word: word.bbox[0])
        spans.append(Evidence(page=page, bbox=(min(w.bbox[0] for w in group), min(w.bbox[1] for w in group),
            max(w.bbox[2] for w in group), max(w.bbox[3] for w in group)),
            text=" ".join(w.text for w in group), method=group[0].method,
            span_ids=[w.span_id for w in group]))
    return spans


def observed(value, words):
    if not words:
        return missing("no_source_span")
    return {"value": value, "status": "observed", "reason": None,
            "evidence": [item.model_dump(mode="json") for item in evidence(words)]}


def missing(reason="not_found", words=(), *, ambiguous=False):
    return {"value": None, "status": "ambiguous" if ambiguous else "missing", "reason": reason,
            "evidence": [item.model_dump(mode="json") for item in evidence(words)]}


def choose(candidates):
    if not candidates:
        return missing()
    values = {str(value) for value, _ in candidates}
    words = [word for _, refs in candidates for word in refs]
    if len(values) != 1:
        return missing("conflicting_values", words, ambiguous=True)
    return observed(candidates[0][0], words)


def verify_evidence(extraction, source):
    """Reject invented IDs/text/coordinates before publishing any provider result."""
    index = {(page["page"], word["span_id"]): (page["method"], word) for page in source["pages"] for word in page["words"]}

    def walk(value):
        if isinstance(value, dict):
            if value.get("status") == "corrected":
                raise ValueError("Only the review workflow may create human corrections")
            if value.get("status") in {"observed", "proposed"}:
                for span in value["evidence"]:
                    if not span.get("span_ids"):
                        raise ValueError("Observed field lacks resolvable span IDs")
                    words = [index[(span["page"], identifier)] for identifier in span["span_ids"]]
                    expected_box = [min(w["bbox"][0] for _, w in words), min(w["bbox"][1] for _, w in words),
                                    max(w["bbox"][2] for _, w in words), max(w["bbox"][3] for _, w in words)]
                    if " ".join(w["text"] for _, w in words) != span["text"] or any(abs(a-b) > 1e-6 for a,b in zip(expected_box,span["bbox"])):
                        raise ValueError("Evidence does not match source words")
                    if any(method != span["method"] for method, _ in words):
                        raise ValueError("Evidence method does not match source")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(extraction.model_dump(mode="json"))
