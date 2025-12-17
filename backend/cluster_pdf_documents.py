#!/usr/bin/env python3
"""
Cluster "documents within a huge PDF" using local OCR + Claude (text-only).

Goal:
1) Run PaddleOCR locally page-by-page and write a resumable JSONL cache.
2) Send pagewise OCR (trimmed snippets) to Claude in batches to:
   - cluster pages into contiguous document blocks (start/end)
   - label doc_type/title
   - decide whether the block needs deep extraction

This avoids Claude Vision entirely; Claude only sees OCR text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
from pdf2image import convert_from_path
from paddleocr import PaddleOCR

from bedrock_config import call_bedrock

try:
    from PyPDF2 import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None

# ---- Multiprocessing globals (must be top-level / picklable) ----
_MP_CFG: Optional[Dict[str, Any]] = None
_MP_READER: Optional[Any] = None
_MP_OCR: Optional[PaddleOCR] = None


def _mp_init(cfg: Dict[str, Any]) -> None:
    """
    Pool initializer: store config in process-global memory.
    Each worker process gets its own PdfReader/PaddleOCR instances.
    """
    global _MP_CFG, _MP_READER, _MP_OCR
    _MP_CFG = cfg
    _MP_READER = None
    _MP_OCR = None


def _mp_get_reader() -> Optional[Any]:
    global _MP_CFG, _MP_READER
    if _MP_READER is not None:
        return _MP_READER
    if _MP_CFG is None:
        return None
    if not _MP_CFG.get("prefer_pdf_text") or PdfReader is None:
        _MP_READER = None
        return None
    try:
        _MP_READER = PdfReader(_MP_CFG["pdf_path"])
    except Exception:
        _MP_READER = None
    return _MP_READER


def _mp_get_ocr() -> PaddleOCR:
    global _MP_OCR
    if _MP_OCR is None:
        _MP_OCR = _init_ocr()
    return _MP_OCR


def _mp_process_one_page(page: int) -> Dict[str, Any]:
    """
    Worker: produce per-page txt file + return manifest row.
    Uses PDF text if present; otherwise rasterizes + OCR (cropped).
    """
    global _MP_CFG
    if _MP_CFG is None:
        raise RuntimeError("Worker not initialized (missing _MP_CFG)")

    t_start = time.time()
    pdf_path = _MP_CFG["pdf_path"]
    out_pages_dir = _MP_CFG["out_pages_dir"]
    borrower_name = _MP_CFG["borrower_name"]
    max_chars_cache = int(_MP_CFG["max_chars_cache"])
    prefer_pdf_text = bool(_MP_CFG["prefer_pdf_text"])
    min_pdf_text_chars = int(_MP_CFG["min_pdf_text_chars"])
    dpi = int(_MP_CFG["dpi"])
    crop_top_ratio = float(_MP_CFG["crop_top_ratio"])
    overwrite_existing = bool(_MP_CFG["overwrite_existing"])

    text_path = _page_text_path(out_pages_dir, page)

    # PDF text fast path
    if prefer_pdf_text:
        reader_local = _mp_get_reader()
        pdf_text = _maybe_extract_pdf_text(reader_local, page)
        if pdf_text and len(pdf_text) >= min_pdf_text_chars:
            if overwrite_existing or (not os.path.exists(text_path)):
                _write_text_file(text_path, pdf_text)
            snippet = _clean_for_prompt(pdf_text, max_chars=max_chars_cache)
            header = "\n".join([ln for ln in snippet.splitlines()[:8] if ln.strip()])
            borrower_hit = borrower_name.upper() in pdf_text.upper()
            return {
                "ts": _now_iso(),
                "pdf_path": pdf_path,
                "page": page,
                "dpi": None,
                "source": "pdf_text",
                "ocr_char_count": len(pdf_text),
                "ocr_sha1": _sha1(pdf_text),
                "borrower_name": borrower_name,
                "borrower_name_found": borrower_hit,
                "keywords": _keywords(pdf_text),
                "header": header,
                "ocr_snippet": snippet,
                "page_text_file": text_path,
                "ocr_meta": {"method": "PyPDF2.extract_text"},
                "elapsed_sec": round(time.time() - t_start, 3),
            }

    # OCR path
    img = _extract_images(pdf_path, page, page, dpi=dpi)[0]
    img2 = _crop_top(img, crop_top_ratio)
    ocr_local = _mp_get_ocr()
    ocr_text, meta = _run_ocr_on_image(ocr_local, img2)
    clean = ocr_text.strip()
    if overwrite_existing or (not os.path.exists(text_path)):
        _write_text_file(text_path, clean)
    snippet = _clean_for_prompt(clean, max_chars=max_chars_cache)
    header = "\n".join([ln for ln in snippet.splitlines()[:8] if ln.strip()])
    borrower_hit = borrower_name.upper() in clean.upper()
    return {
        "ts": _now_iso(),
        "pdf_path": pdf_path,
        "page": page,
        "dpi": dpi,
        "source": "paddleocr",
        "crop_top_ratio": crop_top_ratio,
        "ocr_char_count": len(clean),
        "ocr_sha1": _sha1(clean),
        "borrower_name": borrower_name,
        "borrower_name_found": borrower_hit,
        "keywords": _keywords(clean),
        "header": header,
        "ocr_snippet": snippet,
        "page_text_file": text_path,
        "ocr_meta": meta,
        "elapsed_sec": round(time.time() - t_start, 3),
    }


DEFAULT_BORROWER_NAME = "ROBERT M DUGAN"


def _borrower_aliases(borrower_name: str) -> List[str]:
    """
    Generate common borrower-name variations to help clustering relevance checks.
    Keep this conservative (avoid over-matching).
    """
    raw = (borrower_name or "").strip()
    if not raw:
        return []

    # Normalize whitespace and punctuation for alias generation (Claude will do fuzzy matching too).
    parts = [p for p in re.split(r"\s+", raw.upper().replace(".", "").strip()) if p]
    # Example: ["ROBERT","M","DUGAN"]
    aliases: List[str] = []
    aliases.append(" ".join(parts))

    if len(parts) >= 2:
        first = parts[0]
        last = parts[-1]
        middle = parts[1:-1]

        aliases.append(f"{first} {last}")  # ROBERT DUGAN
        aliases.append(f"{last}, {first}")  # DUGAN, ROBERT
        aliases.append(f"{last} {first}")  # DUGAN ROBERT

        if middle:
            # Middle initial sometimes appears as just the first letter
            mi = middle[0][0]
            aliases.append(f"{first} {mi} {last}")  # ROBERT M DUGAN
            aliases.append(f"{first} {mi}. {last}")  # ROBERT M. DUGAN
            aliases.append(f"{last}, {first} {mi}")  # DUGAN, ROBERT M
            aliases.append(f"{first[0]} {mi} {last}")  # R M DUGAN
            aliases.append(f"{first[0]}. {mi}. {last}")  # R. M. DUGAN
            aliases.append(f"{first[0]} {last}")  # R DUGAN
            aliases.append(f"{first[0]}. {last}")  # R. DUGAN

    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for a in aliases:
        a2 = " ".join(a.replace(".", "").split()).strip()
        if not a2:
            continue
        if a2 in seen:
            continue
        seen.add(a2)
        out.append(a2)
    return out


_NAME_STOPWORDS = {
    "COLORADO",
    "DEPARTMENT",
    "REVENUE",
    "TAX",
    "INSTRUCTIONS",
    "SCHEDULE",
    "FORM",
    "INCOME",
    "RETURN",
    "STATEMENT",
    "INFORMATION",
    "INTERNAL",
    "SERVICE",
    "UNITED",
    "STATES",
    "SOCIAL",
    "SECURITY",
    "ADMINISTRATION",
    "PARTNERSHIP",
    "CORPORATION",
    "INC",
    "INCORPORATED",
    "LLC",
}


def _find_aliases_in_text(text: str, aliases: List[str]) -> List[str]:
    """Case/punctuation-insensitive substring match for known borrower aliases."""
    if not text or not aliases:
        return []
    t = " ".join(str(text).upper().replace(".", "").split())
    found: List[str] = []
    for a in aliases:
        a2 = " ".join(str(a).upper().replace(".", "").split())
        if a2 and a2 in t:
            found.append(a)
    # stable dedupe
    out: List[str] = []
    seen = set()
    for a in found:
        if a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out


def _extract_people_from_text(text: str, max_people: int = 6) -> List[str]:
    """
    Heuristic: extract likely person-name candidates from OCR text.
    This is only a hint to help Claude split multi-shareholder packets.
    """
    if not text:
        return []
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]

    people: List[str] = []
    seen = set()

    ssn_re = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    # Typical "JEANNETTE BROPHY" / "ROBERT M DUGAN" style lines
    name_re = re.compile(r"^(?P<n>[A-Z][A-Z]+(?:\s+[A-Z]\b)?(?:\s+[A-Z][A-Z]+)+)$")

    # Prefer lines near SSNs (often the shareholder name).
    ssn_lines = set()
    for i, ln in enumerate(lines):
        if ssn_re.search(ln):
            ssn_lines.add(i)
            ssn_lines.add(i - 1)
            ssn_lines.add(i - 2)

    def _maybe_add(candidate: str) -> None:
        cand = candidate.strip()
        toks = cand.split()
        if not cand:
            return
        if any(t in _NAME_STOPWORDS for t in toks):
            return
        if cand in seen:
            return
        seen.add(cand)
        people.append(cand)

    for i in sorted([x for x in ssn_lines if 0 <= x < len(lines)]):
        ln = lines[i]
        m = name_re.match(ln)
        if not m:
            continue
        _maybe_add(m.group("n"))
        if len(people) >= max_people:
            return people

    # Fallback: scan all lines
    for ln in lines:
        m = name_re.match(ln)
        if not m:
            continue
        _maybe_add(m.group("n"))
        if len(people) >= max_people:
            break

    return people


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _clean_for_prompt(text: str, max_chars: int) -> str:
    """Keep OCR reasonably bounded for prompts."""
    if not text:
        return ""
    # Normalize whitespace
    t = re.sub(r"[ \t]+", " ", text)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 20] + "\n…(truncated)…"


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if "```json" in s:
        return s.split("```json", 1)[1].split("```", 1)[0].strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return s


def _parse_json_lenient(s: str) -> Any:
    """
    Parse JSON with minor salvage attempts (handles truncated Claude responses).
    This is intentionally conservative: we only try a couple of safe fixes.
    """
    s = _strip_code_fences(s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Try trimming to last closing brace
        last = s.rfind("}")
        if last > 0:
            candidate = s[: last + 1]
            return json.loads(candidate)
        raise


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _append_jsonl(path: str, row: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _existing_pages_in_cache(rows: List[Dict[str, Any]]) -> set:
    pages = set()
    for r in rows:
        p = r.get("page")
        if isinstance(p, int):
            pages.add(p)
    return pages


def _last_manifest_rows_by_page(rows: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Manifest is append-only; keep the last row per page as the effective resume state.
    """
    last: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        p = r.get("page")
        if isinstance(p, int):
            last[p] = r
    return last


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _page_text_path(out_dir: str, page: int) -> str:
    return os.path.join(out_dir, f"page_{page:04d}.txt")


def _write_text_file(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")


def _extract_images(pdf_path: str, start_page: int, end_page: int, dpi: int) -> List[Any]:
    images = convert_from_path(pdf_path, first_page=start_page, last_page=end_page, dpi=dpi)
    return [img.convert("RGB") for img in images]


def _init_ocr() -> PaddleOCR:
    # Keep it fast for screening.
    return PaddleOCR(
        lang="en",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _run_ocr_on_image(ocr: PaddleOCR, image) -> Tuple[str, Dict[str, Any]]:
    """Return (plain_text, debug_meta)."""
    arr = np.array(image)
    result = ocr.predict(
        arr,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_det_limit_side_len=960,
        text_det_limit_type="max",
    )

    if not result or not isinstance(result, list):
        return "", {"shape": getattr(arr, "shape", None), "note": "empty_result"}

    item = result[0]

    # PaddleOCR v3 returns OCRResult dict-like object with rec_texts/rec_scores.
    rec_texts = item.get("rec_texts") or []
    rec_scores = item.get("rec_scores") or []

    lines: List[str] = []
    for i, t in enumerate(rec_texts):
        if not t:
            continue
        score = rec_scores[i] if i < len(rec_scores) else None
        if score is not None and float(score) < 0.50:
            continue
        lines.append(str(t))

    return "\n".join(lines).strip(), {
        "shape": getattr(arr, "shape", None),
        "n_texts": len(rec_texts),
        "n_kept": len(lines),
    }


def _maybe_extract_pdf_text(reader: Optional[Any], page: int) -> str:
    """Attempt fast (non-OCR) PDF text extraction. Page is 1-based."""
    if reader is None:
        return ""
    try:
        p = reader.pages[page - 1]
        t = p.extract_text() or ""
        return t.strip()
    except Exception:
        return ""


def _crop_top(image, ratio: Optional[float]):
    """
    Crop the top portion of the page for clustering OCR.
    This is usually enough to catch form titles / borrower names / headers.
    """
    if ratio is None:
        return image
    try:
        r = float(ratio)
    except Exception:
        return image
    if r <= 0 or r >= 1:
        return image
    w, h = image.size
    return image.crop((0, 0, w, max(1, int(h * r))))


def _keywords(ocr_text: str) -> List[str]:
    if not ocr_text:
        return []
    t = ocr_text.upper()
    candidates = [
        ("SCHEDULE K-1", "SCHEDULE_K1"),
        ("FORM 1040", "FORM_1040"),
        ("FORM 500", "GA_FORM_500"),
        ("GEORGIA", "GEORGIA"),
        ("W-2", "W2"),
        ("EARNINGS SUMMARY", "EARNINGS_SUMMARY"),
        ("INSTRUCTIONS", "INSTRUCTIONS"),
        ("CODE", "CODE"),
        ("GLOSSARY", "GLOSSARY"),
        ("DISCLOSURE", "DISCLOSURE"),
        ("UNIFORM RESIDENTIAL LOAN APPLICATION", "URLA"),
        ("FORM 1008", "FORM_1008"),
    ]
    found = [tag for needle, tag in candidates if needle in t]
    return sorted(set(found))


def build_ocr_cache(
    pdf_path: str,
    output_jsonl: str,
    output_pages_dir: str,
    start_page: int,
    end_page: int,
    dpi: int,
    borrower_name: str,
    max_chars_per_page_in_cache: int,
    prefer_pdf_text: bool,
    min_pdf_text_chars: int,
    crop_top_ratio: float,
    render_chunk_size: int,
    overwrite_existing: bool,
    resume: bool,
    workers: int,
) -> None:
    os.makedirs(os.path.dirname(output_jsonl) or ".", exist_ok=True)
    _ensure_dir(output_pages_dir)
    existing_rows = _read_jsonl(output_jsonl) if resume else []
    last_by_page = _last_manifest_rows_by_page(existing_rows) if resume else {}
    done_pages = set(last_by_page.keys())

    # If the last run OCR'd a page with a different crop ratio (and wasn't pdf_text),
    # reprocess it to keep outputs consistent with the current crop setting.
    if resume and last_by_page:
        for p, row in list(last_by_page.items()):
            if row.get("source") == "paddleocr":
                prev_crop = row.get("crop_top_ratio")
                try:
                    if prev_crop is not None and float(prev_crop) != float(crop_top_ratio):
                        done_pages.discard(p)
                except Exception:
                    # If we can't compare, be conservative and redo.
                    done_pages.discard(p)
            # If prior attempt errored, redo.
            if "error" in row:
                done_pages.discard(p)

    if workers < 1:
        workers = 1

    # In parallel mode we do per-page work in workers; main process only writes manifest.
    # In single-worker mode we keep the current chunked renderer for efficiency.
    reader = None
    if prefer_pdf_text and PdfReader is not None and workers == 1:
        try:
            reader = PdfReader(pdf_path)
        except Exception:
            reader = None

    total = end_page - start_page + 1
    print(f"📄 Pagewise text manifest: {output_jsonl}", flush=True)
    print(f"📄 Pagewise text files dir: {output_pages_dir}", flush=True)
    print(f"   PDF: {pdf_path}", flush=True)
    print(f"   Pages: {start_page}-{end_page} ({total})", flush=True)
    print(f"   Resume: {resume} (already cached: {len(done_pages)} pages)", flush=True)
    print(f"   Prefer PDF text first: {prefer_pdf_text} (PyPDF2={'yes' if PdfReader else 'no'})", flush=True)
    print(f"   Min PDF text chars to skip OCR: {min_pdf_text_chars}", flush=True)
    print(f"   OCR crop_top_ratio: {crop_top_ratio}", flush=True)
    print(f"   Render chunk size: {render_chunk_size}", flush=True)
    print(f"   Workers: {workers}", flush=True)
    print("=" * 80, flush=True)

    # --- Parallel path (recommended for very large docs) ---
    if workers > 1:
        pages_to_process = [p for p in range(start_page, end_page + 1) if p not in done_pages]
        total_todo = len(pages_to_process)
        print(f"🧵 Parallel mode: {total_todo} pages to process (skipping {len(done_pages)} done)", flush=True)

        cfg = {
            "pdf_path": pdf_path,
            "out_pages_dir": output_pages_dir,
            "borrower_name": borrower_name,
            "max_chars_cache": int(max_chars_per_page_in_cache),
            "prefer_pdf_text": bool(prefer_pdf_text),
            "min_pdf_text_chars": int(min_pdf_text_chars),
            "dpi": int(dpi),
            "crop_top_ratio": float(crop_top_ratio),
            "overwrite_existing": bool(overwrite_existing),
        }

        # Write manifest from main process only (prevents file corruption).
        completed = 0
        started_at = time.time()
        with mp.get_context("spawn").Pool(processes=workers, initializer=_mp_init, initargs=(cfg,)) as pool:
            for row in pool.imap_unordered(_mp_process_one_page, pages_to_process, chunksize=1):
                _append_jsonl(output_jsonl, row)
                completed += 1
                if completed % 50 == 0 or completed == total_todo:
                    rate = completed / max(1e-6, (time.time() - started_at))
                    print(f"✅ Progress: {completed}/{total_todo} pages ({rate:.2f} pages/sec)", flush=True)
        return

    # Lazy init OCR only if we encounter pages that need OCR (and reuse across chunks).
    ocr: Optional[PaddleOCR] = None

    page = start_page
    while page <= end_page:
        chunk_start = page
        chunk_end = min(end_page, chunk_start + max(1, int(render_chunk_size)) - 1)

        # First pass: try fast PDF text extraction (no OCR / no rasterization)
        pages_needing_ocr: List[int] = []
        for p in range(chunk_start, chunk_end + 1):
            if resume and p in done_pages:
                continue

            if prefer_pdf_text:
                pdf_text = _maybe_extract_pdf_text(reader, p)
                if pdf_text and len(pdf_text) >= int(min_pdf_text_chars):
                    text_path = _page_text_path(output_pages_dir, p)
                    if overwrite_existing or not (resume and os.path.exists(text_path)):
                        _write_text_file(text_path, pdf_text)
                    snippet = _clean_for_prompt(pdf_text, max_chars=max_chars_per_page_in_cache)
                    header = "\n".join([ln for ln in snippet.splitlines()[:8] if ln.strip()])
                    borrower_hit = borrower_name.upper() in pdf_text.upper()
                    row = {
                        "ts": _now_iso(),
                        "pdf_path": pdf_path,
                        "page": p,
                        "dpi": None,
                        "source": "pdf_text",
                        "ocr_char_count": len(pdf_text),
                        "ocr_sha1": _sha1(pdf_text),
                        "borrower_name": borrower_name,
                        "borrower_name_found": borrower_hit,
                        "keywords": _keywords(pdf_text),
                        "header": header,
                        "ocr_snippet": snippet,
                        "page_text_file": text_path,
                        "ocr_meta": {"method": "PyPDF2.extract_text"},
                        "elapsed_sec": 0.0,
                    }
                    _append_jsonl(output_jsonl, row)
                    done_pages.add(p)
                    print(f"⚡ page {p}: used PDF text ({len(pdf_text)} chars)", flush=True)
                    continue

            pages_needing_ocr.append(p)

        # Second pass: OCR only remaining pages; render chunk once (poppler startup amortized)
        if pages_needing_ocr:
            if ocr is None:
                ocr = _init_ocr()
            print(f"🖼️  Rendering pages {chunk_start}-{chunk_end} (OCR needed: {len(pages_needing_ocr)})…", flush=True)
            try:
                images = _extract_images(pdf_path, chunk_start, chunk_end, dpi=dpi)
            except Exception as e:
                for p in pages_needing_ocr:
                    if resume and p in done_pages:
                        continue
                    _append_jsonl(output_jsonl, {"ts": _now_iso(), "pdf_path": pdf_path, "page": p, "error": f"render_failed: {e}"})
                page = chunk_end + 1
                continue

            for idx, img in enumerate(images):
                p = chunk_start + idx
                if p not in pages_needing_ocr:
                    continue
                if resume and p in done_pages:
                    continue

                print(f"🔍 OCR page {p}…", flush=True)
                try:
                    img2 = _crop_top(img, crop_top_ratio)
                    t0 = time.time()
                    ocr_text, meta = _run_ocr_on_image(ocr, img2)  # type: ignore[arg-type]
                    dt = time.time() - t0

                    clean = ocr_text.strip()
                    text_path = _page_text_path(output_pages_dir, p)
                    if overwrite_existing or not (resume and os.path.exists(text_path)):
                        _write_text_file(text_path, clean)
                    snippet = _clean_for_prompt(clean, max_chars=max_chars_per_page_in_cache)
                    header = "\n".join([ln for ln in snippet.splitlines()[:8] if ln.strip()])
                    borrower_hit = borrower_name.upper() in clean.upper()

                    row = {
                        "ts": _now_iso(),
                        "pdf_path": pdf_path,
                        "page": p,
                        "dpi": dpi,
                        "source": "paddleocr",
                        "crop_top_ratio": crop_top_ratio,
                        "ocr_char_count": len(clean),
                        "ocr_sha1": _sha1(clean),
                        "borrower_name": borrower_name,
                        "borrower_name_found": borrower_hit,
                        "keywords": _keywords(clean),
                        "header": header,
                        "ocr_snippet": snippet,
                        "page_text_file": text_path,
                        "ocr_meta": meta,
                        "elapsed_sec": round(dt, 3),
                    }
                    _append_jsonl(output_jsonl, row)
                    done_pages.add(p)
                    print(f"   ✅ {len(clean)} chars (kept {len(snippet)}), {row['elapsed_sec']}s", flush=True)
                except Exception as e:
                    _append_jsonl(output_jsonl, {"ts": _now_iso(), "pdf_path": pdf_path, "page": p, "error": str(e)})
                    print(f"   ❌ OCR failed: {e}", flush=True)

        page = chunk_end + 1


def _load_cache_for_range(cache_jsonl: str, start_page: int, end_page: int) -> List[Dict[str, Any]]:
    rows = _read_jsonl(cache_jsonl)
    by_page: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        p = r.get("page")
        if isinstance(p, int) and start_page <= p <= end_page:
            # last write wins (supports resume/overwrite patterns)
            by_page[p] = r
    return [by_page[p] for p in sorted(by_page.keys())]


def segment_range_with_claude(
    cache_jsonl: str,
    output_json: str,
    start_page: int,
    end_page: int,
    borrower_name: str,
    max_chars_per_page_in_prompt: int,
    batch_pages: int,
    overlap_pages: int,
    max_tokens: int,
    model: str,
    resume: bool,
) -> None:
    """
    Segment a specific page range (already OCR'd) into sub-documents and map schedule pages to shareholders.
    Intended for deep extraction planning when a large contiguous block contains many member packets.
    """
    os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)

    borrower_aliases = _borrower_aliases(borrower_name)

    if batch_pages < 5:
        batch_pages = 5
    if overlap_pages < 0:
        overlap_pages = 0

    # We build up a global result incrementally, freezing anything before prompt_start.
    sub_docs: List[Dict[str, Any]] = []
    packets: List[Dict[str, Any]] = []
    all_pages_payload: List[Dict[str, Any]] = []  # Accumulate all page payloads for final check
    cur = start_page
    pdf_path_any = None

    if resume and os.path.exists(output_json):
        try:
            existing = json.load(open(output_json, "r", encoding="utf-8"))
            res = (existing.get("result") or {}) if isinstance(existing, dict) else {}
            sub_docs = res.get("sub_documents") or []
            packets = res.get("shareholder_packets") or []
            pdf_path_any = existing.get("pdf_path")
            last_batch = existing.get("last_batch") or {}
            last_end = last_batch.get("end")
            if isinstance(last_end, int) and last_end >= start_page:
                cur = min(end_page + 1, last_end + 1)
                print(f"🔁 Resume enabled: continuing from page {cur} (last_end={last_end})", flush=True)
        except Exception as e:
            print(f"⚠️  Could not resume from existing output ({e}); starting fresh.", flush=True)
            sub_docs = []
            packets = []
            cur = start_page

    def _freeze_tail_by_page(items: List[Dict[str, Any]], key_start: str, key_end: str, prompt_start: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        frozen: List[Dict[str, Any]] = []
        tail: List[Dict[str, Any]] = []
        for it in items:
            try:
                end_p = int(it.get(key_end))
            except Exception:
                end_p = 0
            if end_p and end_p < int(prompt_start):
                frozen.append(it)
            else:
                tail.append(it)
        return frozen, tail

    print(f"🧩 Segmenting pages {start_page}-{end_page} via Claude (batched)", flush=True)
    print(f"   batch_pages={batch_pages} overlap_pages={overlap_pages}", flush=True)

    while cur <= end_page:
        batch_start = cur
        batch_end = min(end_page, cur + batch_pages - 1)
        prompt_start = max(start_page, batch_start - overlap_pages)

        pages_rows = _load_cache_for_range(cache_jsonl, prompt_start, batch_end)
        if not pages_rows:
            raise RuntimeError(f"No OCR cache rows found for pages {prompt_start}-{batch_end}. Run ocr first.")
        if pdf_path_any is None:
            pdf_path_any = pages_rows[0].get("pdf_path")

        pages_payload: List[Dict[str, Any]] = []
        for r in pages_rows:
            snippet = _clean_for_prompt(str(r.get("ocr_snippet") or ""), max_chars=max_chars_per_page_in_prompt)
            header = str(r.get("header") or "")
            combined_text = f"{header}\n{snippet}".strip()
            alias_hits = _find_aliases_in_text(combined_text, borrower_aliases)
            people_found = _extract_people_from_text(combined_text)
            pages_payload.append(
                {
                    "page": r.get("page"),
                    "header": header,
                    "keywords": r.get("keywords") or [],
                    "borrower_name_matches": alias_hits,
                    "people_found": people_found,
                    "ocr_snippet": snippet,
                }
            )
        
        # Accumulate page payloads for final borrower-only check
        all_pages_payload.extend(pages_payload)

        frozen_sub, tail_sub = _freeze_tail_by_page(sub_docs, "start_page", "end_page", prompt_start)
        frozen_pkt, tail_pkt = _freeze_tail_by_page(packets, "pages_start", "pages_end", prompt_start)

        prompt = f"""You are given pagewise OCR snippets for ONE packet range and must segment it accurately.

Borrower of interest: {borrower_name}
Borrower name variations: {json.dumps(borrower_aliases, ensure_ascii=False)}

You are processing pages {prompt_start}-{batch_end} (overlapping context included).

YOUR TASKS:
1) Produce SUB-DOCUMENTS covering ONLY pages {prompt_start}-{batch_end} as contiguous ranges.
2) Produce SHAREHOLDER PACKETS covering ONLY pages {prompt_start}-{batch_end}:
   - Each packet is a contiguous page range for a single shareholder/member (or member_name=null if unknown).
   - If a page is a multi-member roster/list, create a packet with member_name=null and list member_names on that packet.

IMPORTANT:
- Use ONLY text provided.
- DO NOT include any pages outside {prompt_start}-{batch_end}.
- Output must be STRICT JSON, concise strings.
- Split packets when the shareholder/member name changes (use people_found / SSN cues).

EXISTING FROZEN SUB_DOCS (do not repeat in output):
{json.dumps(frozen_sub, ensure_ascii=False)}

EXISTING TAIL SUB_DOCS (you may extend/adjust ONLY if overlap requires continuity):
{json.dumps(tail_sub[-10:], ensure_ascii=False)}

EXISTING FROZEN PACKETS (do not repeat in output):
{json.dumps(frozen_pkt, ensure_ascii=False)}

EXISTING TAIL PACKETS (you may extend/adjust ONLY if overlap requires continuity):
{json.dumps(tail_pkt[-15:], ensure_ascii=False)}

PAGES PAYLOAD:
{json.dumps(pages_payload, ensure_ascii=False)}

OUTPUT JSON (STRICT):
{{
  \"sub_documents\": [
    {{
      \"start_page\": {prompt_start},
      \"end_page\": {prompt_start},
      \"doc_type\": \"state_tax_return|federal_tax_return|k1|k1_state|schedule|attachment|instructions|other\",
      \"form_name\": \"Short form name\",
      \"title\": \"Short label\",
      \"is_multi_member_roster\": true/false,
      \"member_names\": [\"...\"],
      \"notes\": \"Optional\"
    }}
  ],
  \"shareholder_packets\": [
    {{
      \"pages_start\": {prompt_start},
      \"pages_end\": {prompt_start},
      \"member_name\": \"FULL NAME\" or null,
      \"member_id_hint\": \"SSN/FEIN\" or null,
      \"forms\": [\"...\"] ,
      \"member_names\": [\"...\"] ,
      \"belongs_to_borrower\": true/false,
      \"reason\": \"One sentence\"
    }}
  ]
}}

Return ONLY JSON."""

        # Robust parsing: if Claude returns invalid JSON, auto-retry with stricter constraints,
        # and if still invalid, shrink the batch and retry the smaller range.
        parsed = None
        attempt = 0
        local_batch_pages = (batch_end - batch_start + 1)
        while parsed is None:
            attempt += 1
            print(f"   ⏳ Claude segment batch {batch_start}-{batch_end} (prompt {prompt_start}-{batch_end}) attempt {attempt}…", flush=True)
            response = call_bedrock(prompt=prompt, max_tokens=max_tokens, model=model)
            try:
                parsed = _parse_json_lenient(response)
                break
            except Exception:
                if attempt == 1:
                    # Retry with much tighter output constraints (short fields).
                    prompt = prompt + (
                        "\n\nSTRICT OUTPUT CONSTRAINTS:\n"
                        "- JSON only.\n"
                        "- Keep 'title', 'form_name', 'notes', 'reason' under 80 chars.\n"
                        "- Prefer fewer objects.\n"
                        "- Do NOT include any prose outside JSON.\n"
                    )
                    continue
                # If still failing, shrink the batch range and restart this batch.
                if local_batch_pages > 15:
                    new_size = max(15, local_batch_pages // 2)
                    batch_end = min(end_page, batch_start + new_size - 1)
                    prompt_start = max(start_page, batch_start - overlap_pages)
                    print(f"   🔧 JSON parse failed twice; shrinking batch to {batch_start}-{batch_end}", flush=True)
                    # Recompute payload for the smaller batch
                    pages_rows = _load_cache_for_range(cache_jsonl, prompt_start, batch_end)
                    pages_payload = []
                    for r in pages_rows:
                        snippet = _clean_for_prompt(str(r.get("ocr_snippet") or ""), max_chars=max_chars_per_page_in_prompt)
                        header = str(r.get("header") or "")
                        combined_text = f"{header}\n{snippet}".strip()
                        alias_hits = _find_aliases_in_text(combined_text, borrower_aliases)
                        people_found = _extract_people_from_text(combined_text)
                        pages_payload.append(
                            {
                                "page": r.get("page"),
                                "header": header,
                                "keywords": r.get("keywords") or [],
                                "borrower_name_matches": alias_hits,
                                "people_found": people_found,
                                "ocr_snippet": snippet,
                            }
                        )
                    frozen_sub, tail_sub = _freeze_tail_by_page(sub_docs, "start_page", "end_page", prompt_start)
                    frozen_pkt, tail_pkt = _freeze_tail_by_page(packets, "pages_start", "pages_end", prompt_start)
                    prompt = f"""You are given pagewise OCR snippets for ONE packet range and must segment it accurately.

Borrower of interest: {borrower_name}
Borrower name variations: {json.dumps(borrower_aliases, ensure_ascii=False)}

You are processing pages {prompt_start}-{batch_end} (overlapping context included).

YOUR TASKS:
1) Produce SUB-DOCUMENTS covering ONLY pages {prompt_start}-{batch_end} as contiguous ranges.
2) Produce SHAREHOLDER PACKETS covering ONLY pages {prompt_start}-{batch_end}.

IMPORTANT:
- Use ONLY text provided.
- DO NOT include any pages outside {prompt_start}-{batch_end}.
- Output must be STRICT JSON, concise strings.

EXISTING FROZEN SUB_DOCS (do not repeat in output):
{json.dumps(frozen_sub, ensure_ascii=False)}

EXISTING TAIL SUB_DOCS (you may extend/adjust ONLY if overlap requires continuity):
{json.dumps(tail_sub[-10:], ensure_ascii=False)}

EXISTING FROZEN PACKETS (do not repeat in output):
{json.dumps(frozen_pkt, ensure_ascii=False)}

EXISTING TAIL PACKETS (you may extend/adjust ONLY if overlap requires continuity):
{json.dumps(tail_pkt[-15:], ensure_ascii=False)}

PAGES PAYLOAD:
{json.dumps(pages_payload, ensure_ascii=False)}

OUTPUT JSON (STRICT):
{{
  \"sub_documents\": [{{\"start_page\":{prompt_start},\"end_page\":{prompt_start},\"doc_type\":\"other\",\"form_name\":\"\",\"title\":\"\",\"is_multi_member_roster\":false,\"member_names\":[],\"notes\":\"\"}}],
  \"shareholder_packets\": [{{\"pages_start\":{prompt_start},\"pages_end\":{prompt_start},\"member_name\":null,\"member_id_hint\":null,\"forms\":[],\"member_names\":[],\"belongs_to_borrower\":false,\"reason\":\"\"}}]
}}

Return ONLY JSON."""
                    parsed = None
                    attempt = 0
                    local_batch_pages = (batch_end - batch_start + 1)
                    continue
                # Give up: write response for debugging and raise.
                debug_path = output_json + ".bad_response.txt"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(str(response))
                raise RuntimeError(f"Claude returned invalid JSON repeatedly. Saved raw response to {debug_path}")

        if not isinstance(parsed, dict):
            raise RuntimeError("Claude returned invalid segmentation JSON (not an object)")

        new_sub = parsed.get("sub_documents") or []
        new_pkt = parsed.get("shareholder_packets") or []
        if not isinstance(new_sub, list) or not isinstance(new_pkt, list):
            raise RuntimeError("Claude returned invalid segmentation JSON (missing lists)")

        # Merge by freezing earlier and replacing tail with Claude's current outputs.
        sub_docs = frozen_sub + new_sub
        packets = frozen_pkt + new_pkt

        # Persist incremental output
        out = {
            "ts": _now_iso(),
            "pdf_path": pdf_path_any,
            "borrower_name": borrower_name,
            "borrower_aliases": borrower_aliases,
            "page_range": {"start": start_page, "end": end_page},
            "batching": {"batch_pages": batch_pages, "overlap_pages": overlap_pages},
            "model": model,
            "result": {
                "packet": {"start_page": start_page, "end_page": end_page, "summary": "Segmented in batches"},
                "sub_documents": sub_docs,
                "shareholder_packets": packets,
            },
            "last_batch": {"start": batch_start, "end": batch_end, "prompt_start": prompt_start},
        }
        # Convenience view: borrower-only packets by strict name match OR page-level alias hits.
        allowed_exact = {"ROBERT DUGAN", "ROBERT M DUGAN"}
        # Build page->alias_hits map from accumulated payloads
        page_to_alias_hits = {p["page"]: p.get("borrower_name_matches", []) for p in all_pages_payload}
        
        borrower_only_packets: List[Dict[str, Any]] = []
        for pkt in packets:
            name = str(pkt.get("member_name") or "").strip().upper()
            # Check if member_name matches
            if name in allowed_exact:
                borrower_only_packets.append(pkt)
            else:
                # Check if any page in packet range has borrower alias hits
                ps = pkt.get("pages_start", 0)
                pe = pkt.get("pages_end", 0)
                has_alias_hit = any(
                    page_to_alias_hits.get(pg, [])
                    for pg in range(ps, pe + 1)
                )
                if has_alias_hit:
                    borrower_only_packets.append(pkt)
        out["borrower_only_packets_exact"] = borrower_only_packets
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"   ✅ Saved partial segmentation: sub_docs={len(sub_docs)} packets={len(packets)}", flush=True)

        cur = batch_end + 1

    print(f"✅ Saved segmentation: {output_json}", flush=True)


def _split_docs_by_page(docs: List[Dict[str, Any]], prompt_start: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Freeze docs that end BEFORE prompt_start; allow Claude to modify/extend docs
    that intersect or occur after prompt_start (the "tail").
    This prevents losing earlier docs when batching.
    """
    frozen: List[Dict[str, Any]] = []
    tail: List[Dict[str, Any]] = []
    for d in docs:
        try:
            end_p = int(d.get("end_page"))
        except Exception:
            end_p = 0
        if end_p and end_p < int(prompt_start):
            frozen.append(d)
        else:
            tail.append(d)
    return frozen, tail


def cluster_with_claude(
    cache_jsonl: str,
    output_index_json: str,
    start_page: int,
    end_page: int,
    borrower_name: str,
    batch_pages: int,
    overlap_pages: int,
    max_chars_per_page_in_prompt: int,
    max_tokens: int,
    model: str,
    resume: bool,
    keep_last_existing_docs_in_prompt: int,
) -> None:
    os.makedirs(os.path.dirname(output_index_json) or ".", exist_ok=True)

    existing_index: Dict[str, Any] = {}
    if resume and os.path.exists(output_index_json):
        with open(output_index_json, "r", encoding="utf-8") as f:
            existing_index = json.load(f)

    docs: List[Dict[str, Any]] = existing_index.get("documents", []) if isinstance(existing_index.get("documents"), list) else []

    print(f"🧩 Clustering via Claude (text-only)", flush=True)
    print(f"   OCR cache: {cache_jsonl}", flush=True)
    print(f"   Output index: {output_index_json}", flush=True)
    print(f"   Pages: {start_page}-{end_page}", flush=True)
    print(f"   Batch pages: {batch_pages}, overlap: {overlap_pages}", flush=True)
    print(f"   Existing docs: {len(docs)} (resume={resume})", flush=True)
    print("=" * 80, flush=True)

    cur = start_page
    while cur <= end_page:
        batch_start = cur
        batch_end = min(end_page, cur + batch_pages - 1)
        # include overlap from previous batch for continuity
        prompt_start = max(start_page, batch_start - overlap_pages)

        pages_rows = _load_cache_for_range(cache_jsonl, prompt_start, batch_end)
        if not pages_rows:
            raise RuntimeError(f"No OCR cache rows found for pages {prompt_start}-{batch_end}. Run ocr first.")

        # Build compact per-page payload for Claude
        pages_payload: List[Dict[str, Any]] = []
        for r in pages_rows:
            snippet = _clean_for_prompt(str(r.get("ocr_snippet") or ""), max_chars=max_chars_per_page_in_prompt)
            header = str(r.get("header") or "")
            combined_text = f"{header}\n{snippet}".strip()
            borrower_aliases = _borrower_aliases(borrower_name)
            alias_hits = _find_aliases_in_text(combined_text, borrower_aliases)
            people_found = _extract_people_from_text(combined_text)
            pages_payload.append(
                {
                    "page": r.get("page"),
                    "header": header,
                    "keywords": r.get("keywords") or [],
                    # More robust than the original exact-name flag in the OCR cache.
                    "borrower_name_found": bool(alias_hits),
                    "borrower_name_matches": alias_hits,
                    # Hints for splitting multi-shareholder packets
                    "people_found": people_found,
                    "ocr_snippet": snippet,
                }
            )

        # Page-range-based freezing is more reliable than count-based tail windows.
        frozen_docs, tail_docs = _split_docs_by_page(docs, prompt_start)
        # Limit how much tail history we send for continuity (keep most recent).
        if keep_last_existing_docs_in_prompt > 0 and len(tail_docs) > keep_last_existing_docs_in_prompt:
            tail_docs = tail_docs[-keep_last_existing_docs_in_prompt:]

        prompt = f"""You are given pagewise OCR from a huge PDF that contains MANY different documents concatenated together.

Your job is to build/maintain a DOCUMENT INDEX by clustering CONTIGUOUS page ranges into individual documents.

Borrower of interest: {borrower_name}
Borrower name variations (treat these as the SAME person): {json.dumps(_borrower_aliases(borrower_name), ensure_ascii=False)}

IMPORTANT:
- You only see OCR text snippets; do NOT assume anything not present.
- Output must be STRICT JSON, no markdown.
- Document boundaries MUST be contiguous page ranges.
- Prefer larger coherent clusters over splitting every page.
- If a document spans across batches, you MUST extend the existing last document rather than creating a new one.
- Some pages are instructions/glossary; cluster them as their own document blocks and mark them NOT eligible for deep extraction.
- "worksheet" documents are NOT admissible evidence; cluster them but set needs_deep_extraction=false.
- Many state/corporate packets contain shareholder-specific pages for MANY people. You MUST split those into separate contiguous blocks per person when you see the person change (use people_found / Name of Partner or Shareholder / SSN context).
- borrower_relevant=true ONLY when borrower_name_matches is non-empty OR the block is an entity-return section that is immediately adjacent to the borrower's own shareholder/K-1 pages (needed to support borrower income).
- If a block clearly belongs to another person (people_found shows another individual and borrower_name_matches is empty), borrower_relevant MUST be false and needs_deep_extraction MUST be false.

EXISTING DOCUMENT INDEX (frozen; DO NOT MODIFY; DO NOT REPEAT in output):
{json.dumps(frozen_docs, ensure_ascii=False)}

EXISTING TAIL DOCS (editable for continuity; you may extend/adjust ONLY these if needed):
{json.dumps(tail_docs, ensure_ascii=False)}

NEW PAGEWISE OCR (pages {prompt_start}-{batch_end}; your clustering output must cover this range):
{json.dumps(pages_payload, ensure_ascii=False)}

Output schema (IMPORTANT: output ONLY the UPDATED TAIL DOCS (as needed) plus any NEW DOCS required to fully cover pages {prompt_start}-{batch_end}; DO NOT repeat frozen docs):
{{
  "documents": [
    {{
      "start_page": 1,
      "end_page": 3,
      "doc_type": "state_tax_return|federal_tax_return|w2|k1|instructions|disclosure|urla|1008|worksheet|other",
      "title": "Short human label",
      "borrower_relevant": true/false,
      "needs_deep_extraction": true/false,
      "reason": "One sentence",
      "signals": {{
        "borrower_names_found": ["..."],
        "keywords": ["..."]
      }}
    }}
  ],
  "notes": "Optional short note about any uncertainty"
}}

Rules for needs_deep_extraction:
- YES if the block contains mortgage-relevant financial line items for the borrower (income, K-1 amounts for borrower, W-2 wages, depreciation, state returns with amounts, etc.)
- NO if it's instructions, glossary, blank, or K-1/other forms for a different person.
- NO if it's a worksheet.

Return ONLY JSON."""

        print(f"\n🔄 Batch pages {batch_start}-{batch_end} (prompt includes {prompt_start}-{batch_end})", flush=True)
        print(f"   ⏳ Calling Claude…", flush=True)
        response = call_bedrock(prompt=prompt, max_tokens=max_tokens, model=model)
        parsed = _parse_json_lenient(response)
        if not isinstance(parsed, dict) or "documents" not in parsed or not isinstance(parsed["documents"], list):
            raise RuntimeError("Claude returned invalid clustering JSON (missing documents list)")

        updated_tail_and_new_docs = parsed["documents"]

        # Rebuild documents: all frozen docs (everything before prompt_start) + updated tail/new docs.
        # This ensures earlier docs can never disappear due to batching.
        docs = frozen_docs + updated_tail_and_new_docs

        out = {
            "ts": _now_iso(),
            "pdf_path": pages_rows[0].get("pdf_path"),
            "borrower_name": borrower_name,
            "page_range": {"start": start_page, "end": end_page},
            "batching": {"batch_pages": batch_pages, "overlap_pages": overlap_pages},
            "documents": docs,
            "last_batch": {"start": batch_start, "end": batch_end, "prompt_start": prompt_start},
            "notes": parsed.get("notes"),
        }

        with open(output_index_json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

        print(f"   ✅ Saved index: {len(docs)} docs total", flush=True)

        cur = batch_end + 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster documents within a large PDF using OCR + Claude (text-only).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ocr = sub.add_parser("ocr", help="Run local PaddleOCR and write JSONL cache")
    p_ocr.add_argument("--pdf", required=True, help="Absolute path to PDF")
    p_ocr.add_argument("--out_manifest", required=True, help="Output manifest JSONL path (one row per page)")
    p_ocr.add_argument("--out_pages_dir", required=True, help="Output directory for per-page .txt files")
    p_ocr.add_argument("--start", type=int, required=True, help="Start page (1-based)")
    p_ocr.add_argument("--end", type=int, required=True, help="End page (1-based)")
    p_ocr.add_argument("--dpi", type=int, default=150)
    p_ocr.add_argument("--borrower", default=DEFAULT_BORROWER_NAME)
    p_ocr.add_argument("--max_chars_cache", type=int, default=4000, help="Max OCR chars stored per page in cache")
    p_ocr.add_argument("--prefer_pdf_text", action="store_true", help="Try fast PDF text extraction first (skip OCR if present)")
    p_ocr.add_argument("--min_pdf_text_chars", type=int, default=80, help="If PDF text has >= this many chars, skip OCR")
    p_ocr.add_argument("--crop_top_ratio", type=float, default=0.35, help="OCR only top portion for clustering (0-1); set 1.0 for full page")
    p_ocr.add_argument("--render_chunk_size", type=int, default=10, help="Render this many pages at once to amortize poppler startup")
    p_ocr.add_argument("--overwrite_existing", action="store_true", help="Overwrite existing per-page .txt files when resuming")
    p_ocr.add_argument("--workers", type=int, default=1, help="Parallel workers for OCR/text extraction (recommended: 10)")
    p_ocr.add_argument("--resume", action="store_true")

    p_cluster = sub.add_parser("cluster", help="Call Claude to build/update a document index from OCR cache")
    p_cluster.add_argument("--cache", required=True, help="OCR cache JSONL path")
    p_cluster.add_argument("--out", required=True, help="Output index JSON path")
    p_cluster.add_argument("--start", type=int, required=True)
    p_cluster.add_argument("--end", type=int, required=True)
    p_cluster.add_argument("--borrower", default=DEFAULT_BORROWER_NAME)
    p_cluster.add_argument("--batch_pages", type=int, default=40)
    p_cluster.add_argument("--overlap_pages", type=int, default=2)
    p_cluster.add_argument("--max_chars_prompt", type=int, default=1200)
    p_cluster.add_argument("--keep_last_existing", type=int, default=25, help="How many existing tail docs to include for continuity")
    p_cluster.add_argument("--max_tokens", type=int, default=4000)
    p_cluster.add_argument("--model", default="claude-haiku-4-5")
    p_cluster.add_argument("--resume", action="store_true")

    p_segment = sub.add_parser("segment", help="Segment a specific page range into sub-docs and shareholder packets (Claude)")
    p_segment.add_argument("--cache", required=True, help="OCR cache JSONL path")
    p_segment.add_argument("--out", required=True, help="Output JSON path")
    p_segment.add_argument("--start", type=int, required=True)
    p_segment.add_argument("--end", type=int, required=True)
    p_segment.add_argument("--borrower", default=DEFAULT_BORROWER_NAME)
    p_segment.add_argument("--max_chars_prompt", type=int, default=900)
    p_segment.add_argument("--batch_pages", type=int, default=50)
    p_segment.add_argument("--overlap_pages", type=int, default=2)
    p_segment.add_argument("--max_tokens", type=int, default=6000)
    p_segment.add_argument("--model", default="claude-haiku-4-5")
    p_segment.add_argument("--resume", action="store_true")

    args = parser.parse_args()

    if args.cmd == "ocr":
        build_ocr_cache(
            pdf_path=args.pdf,
            output_jsonl=args.out_manifest,
            output_pages_dir=args.out_pages_dir,
            start_page=args.start,
            end_page=args.end,
            dpi=args.dpi,
            borrower_name=args.borrower,
            max_chars_per_page_in_cache=args.max_chars_cache,
            prefer_pdf_text=bool(args.prefer_pdf_text),
            min_pdf_text_chars=int(args.min_pdf_text_chars),
            crop_top_ratio=float(args.crop_top_ratio),
            render_chunk_size=int(args.render_chunk_size),
            overwrite_existing=bool(args.overwrite_existing),
            resume=args.resume,
            workers=int(args.workers),
        )
    elif args.cmd == "cluster":
        cluster_with_claude(
            cache_jsonl=args.cache,
            output_index_json=args.out,
            start_page=args.start,
            end_page=args.end,
            borrower_name=args.borrower,
            batch_pages=args.batch_pages,
            overlap_pages=args.overlap_pages,
            max_chars_per_page_in_prompt=args.max_chars_prompt,
            max_tokens=args.max_tokens,
            model=args.model,
            resume=args.resume,
            keep_last_existing_docs_in_prompt=args.keep_last_existing,
        )
    elif args.cmd == "segment":
        segment_range_with_claude(
            cache_jsonl=args.cache,
            output_json=args.out,
            start_page=args.start,
            end_page=args.end,
            borrower_name=args.borrower,
            max_chars_per_page_in_prompt=int(args.max_chars_prompt),
            batch_pages=int(args.batch_pages),
            overlap_pages=int(args.overlap_pages),
            max_tokens=int(args.max_tokens),
            model=args.model,
            resume=bool(args.resume),
        )
    else:
        raise RuntimeError(f"Unknown cmd: {args.cmd}")


if __name__ == "__main__":
    main()


