"""
Docling-based document parser for the multimodal RAG pipeline.
Uses the docling Python API directly — no raganything / MinerU dependency.

Content item schema (list of dicts):
  - {"type": "text",     "text": str,          "page_idx": int}
  - {"type": "image",    "img_path": str,       "image_caption": str, "image_footnote": str, "page_idx": int}
  - {"type": "table",    "table_body": any,     "table_caption": str, "table_footnote": str, "img_path": str, "page_idx": int}
  - {"type": "equation", "text": str,           "text_format": str,   "page_idx": int}
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from app.rag.utils import logger


def _convert_with_docling(file_path: Path, image_dir: Path) -> list[dict[str, Any]]:
    """
    Use the docling Python API to parse a document and convert its items
    to the MinerU-compatible content_list format used by this pipeline.

    Images are saved as PNG files inside `image_dir`.
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
        from docling.datamodel.base_models import InputFormat
    except ImportError:
        raise RuntimeError(
            "docling is not installed. Run: pip install 'docling>=2.5.0'"
        )

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(
                    do_ocr=True,
                    ocr_options=EasyOcrOptions(lang=["en"]),
                )
            )
        }
    )
    result = converter.convert(str(file_path))
    doc = result.document

    content_list: list[dict[str, Any]] = []
    image_counter = 0
    image_dir.mkdir(parents=True, exist_ok=True)

    try:
        # docling_core item types
        from docling_core.types.doc import (
            DocItemLabel,
            PictureItem,
            TableItem,
            TextItem,
        )
    except ImportError:
        # Older docling versions use different import paths
        from docling.datamodel.document import (  # type: ignore
            PictureItem,
            TableItem,
            TextItem,
        )
        DocItemLabel = None  # type: ignore

    def _page_idx(item) -> int:
        """Extract page number from item provenance (0-based)."""
        try:
            if item.prov:
                return max(0, item.prov[0].page_no - 1)
        except Exception:
            pass
        return 0

    for item, _level in doc.iterate_items():
        if isinstance(item, TextItem):
            text = getattr(item, "orig", None) or getattr(item, "text", "") or ""
            if not text.strip():
                continue

            # Check if it's a formula/equation
            label = getattr(item, "label", None)
            label_str = str(label).lower() if label else ""
            if "formula" in label_str or "equation" in label_str:
                content_list.append({
                    "type": "equation",
                    "text": text,
                    "text_format": "latex",
                    "page_idx": _page_idx(item),
                })
            else:
                content_list.append({
                    "type": "text",
                    "text": text,
                    "page_idx": _page_idx(item),
                })

        elif isinstance(item, TableItem):
            # Export table as HTML for the processor (preserves structure)
            try:
                table_html = item.export_to_html(doc)
            except Exception:
                try:
                    table_html = item.export_to_markdown(doc)
                except Exception:
                    table_html = str(item)

            caption = ""
            footnote = ""
            try:
                if item.captions:
                    caption = " ".join(
                        c.text if hasattr(c, "text") else str(c)
                        for c in item.captions
                    )
                if hasattr(item, "footnotes") and item.footnotes:
                    footnote = " ".join(
                        f.text if hasattr(f, "text") else str(f)
                        for f in item.footnotes
                    )
            except Exception:
                pass

            content_list.append({
                "type": "table",
                "table_body": table_html,
                "table_caption": caption,
                "table_footnote": footnote,
                "img_path": "",
                "page_idx": _page_idx(item),
            })

        elif isinstance(item, PictureItem):
            img_path_str = ""
            try:
                # Try to get the image as a PIL image and save it
                pil_img = item.get_image(doc)
                if pil_img is not None:
                    image_counter += 1
                    img_file = image_dir / f"image_{image_counter}.png"
                    pil_img.save(str(img_file), format="PNG")
                    img_path_str = str(img_file.resolve())
            except Exception:
                # Fallback: try accessing base64 URI from the image field
                try:
                    uri = item.image.uri if hasattr(item, "image") and item.image else None
                    if uri and str(uri).startswith("data:"):
                        b64 = str(uri).split(",", 1)[1]
                        image_counter += 1
                        img_file = image_dir / f"image_{image_counter}.png"
                        img_file.write_bytes(base64.b64decode(b64))
                        img_path_str = str(img_file.resolve())
                except Exception:
                    pass

            caption = ""
            footnote = ""
            try:
                if item.captions:
                    caption = " ".join(
                        c.text if hasattr(c, "text") else str(c)
                        for c in item.captions
                    )
                if hasattr(item, "footnotes") and item.footnotes:
                    footnote = " ".join(
                        f.text if hasattr(f, "text") else str(f)
                        for f in item.footnotes
                    )
            except Exception:
                pass

            # If we couldn't get the image file, treat as text with caption
            if not img_path_str:
                if caption:
                    content_list.append({
                        "type": "text",
                        "text": f"[Image: {caption}]",
                        "page_idx": _page_idx(item),
                    })
                # Skip images we can't process
                continue

            content_list.append({
                "type": "image",
                "img_path": img_path_str,
                "image_caption": caption,
                "image_footnote": footnote,
                "page_idx": _page_idx(item),
            })

    return content_list


def parse_bytes(
    content: bytes,
    filename: str,
    output_dir: str | None = None,
) -> list[dict[str, Any]]:
    """
    Parse a document from in-memory bytes using the docling Python API.

    Args:
        content:    Raw file bytes.
        filename:   Original filename including extension (e.g., "lecture1.pdf").
        output_dir: Directory for Docling output artifacts (including extracted
                    images). The **caller is responsible for cleanup** — image
                    paths inside the returned content_list remain valid only as
                    long as this directory exists.  If None, a new temp directory
                    is created; the caller must remove it after consuming the
                    image files (e.g., after the modal processors have finished).

    Returns:
        List of content item dicts, one per block.
    """
    if output_dir is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="rag_docling_"))
    else:
        tmp_dir = Path(output_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

    input_path = tmp_dir / filename
    input_path.write_bytes(content)

    image_dir = tmp_dir / "images"
    try:
        content_list = _convert_with_docling(input_path, image_dir)
    except Exception as e:
        logger.error(f"Docling parse_bytes failed for '{filename}': {e}")
        raise

    logger.info(
        f"Docling parsed '{filename}': {len(content_list)} content blocks"
    )
    return content_list


def parse_file(
    file_path: str,
    output_dir: str | None = None,
) -> list[dict[str, Any]]:
    """
    Parse a document from a file path on disk.

    Args:
        file_path:  Absolute path to the document.
        output_dir: Optional directory for image output.

    Returns:
        List of content item dicts.
    """
    fp = Path(file_path)
    if output_dir:
        image_dir = Path(output_dir) / "images"
    else:
        image_dir = fp.parent / "docling_images"

    content_list = _convert_with_docling(fp, image_dir)
    logger.info(f"Docling parsed '{file_path}': {len(content_list)} content blocks")
    return content_list


def separate_content(
    content_list: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Split a content list into:
      - pure text (joined into one string for the text RAG pipeline)
      - multimodal items (images, tables, equations)

    Args:
        content_list: Output from parse_bytes / parse_file.

    Returns:
        (text_content, multimodal_items)
    """
    text_parts: list[str] = []
    multimodal_items: list[dict[str, Any]] = []

    for item in content_list:
        ctype = item.get("type", "text")
        if ctype == "text":
            text = item.get("text", "")
            if text.strip():
                text_parts.append(text)
        else:
            multimodal_items.append(item)

    text_content = "\n\n".join(text_parts)
    logger.info(
        f"separate_content: {len(text_parts)} text blocks "
        f"({len(text_content)} chars), {len(multimodal_items)} modal items"
    )
    return text_content, multimodal_items
