"""Slide/PDF/PPTX -> markdown (Docling) + speaker notes (python-pptx).

Trả về markdown mà mỗi slide là một section `## Slide N — <title>` kèm
anchor provenance để trích nguồn được về sau.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
from shutil import which


def extract_slides(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return _extract_pdf_to_markdown(path)

    try:
        from docling.document_converter import DocumentConverter
    except ImportError as e:
        raise RuntimeError(
            "Chưa cài docling và không có fallback phù hợp cho file này."
        ) from e

    result = DocumentConverter().convert(str(path))
    md = result.document.export_to_markdown()

    notes = speaker_notes(path) if suffix == ".pptx" else {}
    if notes:
        md += "\n\n## Ghi chú giảng viên (speaker notes)\n"
        for slide_no, text in sorted(notes.items()):
            md += f"\n### Slide {slide_no}\n{text}\n"
    return md


def ensure_slide_markdown(path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{path.stem}.md"
    if target.exists() and target.read_text(encoding="utf-8").strip():
        return target
    target.write_text(extract_slides(path), encoding="utf-8")
    return target


def _extract_pdf_to_markdown(pdf_path: Path) -> str:
    if which("pdftotext") and which("pdfinfo"):
        return _extract_pdf_with_poppler(pdf_path)

    try:
        from docling.document_converter import DocumentConverter
        result = DocumentConverter().convert(str(pdf_path))
        return result.document.export_to_markdown()
    except Exception:
        pass

    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        sections = []
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            title = lines[0] if lines else f"Page {idx}"
            body = "\n".join(lines) if lines else "_No extractable text on this page._"
            sections.append(f"## Page {idx} — {title}\n\n{body}\n")
        return "\n".join(sections).strip() + "\n"
    except Exception as e:
        raise RuntimeError(f"Không ingest được PDF {pdf_path}: {e}") from e



def _extract_pdf_with_poppler(pdf_path: Path) -> str:
    page_count = _pdf_page_count(pdf_path)
    slide_sections: list[str] = []
    for page in range(1, page_count + 1):
        text = _extract_pdf_page(pdf_path, page)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0] if lines else f"Slide {page}"
        body = "\n".join(lines) if lines else "_No extractable text on this slide._"
        slide_sections.append(f"## Slide {page} — {title}\n\n{body}\n")
    return "\n".join(slide_sections).strip() + "\n"


def _pdf_page_count(pdf_path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"Không đọc được số trang từ PDF: {pdf_path}")


def _extract_pdf_page(pdf_path: Path, page_number: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page_number), "-l", str(page_number), str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def speaker_notes(pptx_path: Path) -> dict[int, str]:
    """Speaker notes là 'vàng' cho RAG — Docling không lấy được, python-pptx lấy được."""
    try:
        from pptx import Presentation
    except ImportError:
        return {}
    notes: dict[int, str] = {}
    prs = Presentation(str(pptx_path))
    for i, slide in enumerate(prs.slides, start=1):
        if slide.has_notes_slide:
            text = slide.notes_slide.notes_text_frame.text.strip()
            if text:
                notes[i] = text
    return notes
