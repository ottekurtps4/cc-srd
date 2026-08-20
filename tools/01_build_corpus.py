from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

ROOT = Path(r"C:\Users\p1\Desktop\embeddings")

BOOKS = {
    "kc": "Kings and Cantrips",
    "kw": "Kingdoms and Warfare",
    "ph": "Player's Handbook",
    "rg": "Ryoko's Guide",
    "sf": "Strongholds and Followers",
    "tc": "Tasha's Cauldron",
    "xc": "Xardon's Codex",
}

PAGE_MARKER = "<<<PAGE:{:04d}>>>"

GENERATED_DIRS = (
    "source",
    "extracted",
    "structure",
    "chunks",
    "classified",
    "embeddings",
    "manifests",
    "output",
    "review",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\x00", "")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text.strip()


def create_book_structure(book_dir: Path) -> None:
    for name in GENERATED_DIRS:
        (book_dir / name).mkdir(parents=True, exist_ok=True)


def extract_pdf(pdf_path: Path):
    pages = []
    image_inventory = []

    with pymupdf.open(pdf_path) as doc:
        total_pages = len(doc)

        for index, page in enumerate(doc):
            pdf_page = index + 1

            try:
                page_text = page.get_text("text", sort=True)
            except TypeError:
                page_text = page.get_text("text")

            page_text = page_text or ""
            images = page.get_images(full=True)

            for image_number, image in enumerate(images, start=1):
                image_inventory.append(
                    {
                        "pdf_page": pdf_page,
                        "image_number": image_number,
                        "xref": image[0],
                    }
                )

            pages.append(
                {
                    "pdf_page": pdf_page,
                    "text": page_text,
                    "character_count": len(page_text),
                    "image_count": len(images),
                }
            )

            print(
                f"      Page {pdf_page}/{total_pages} "
                f"| chars={len(page_text):,} "
                f"| images={len(images)}"
            )

    return pages, image_inventory


def build_page_aware_text(pages) -> str:
    output = []
    for page in pages:
        output.append(PAGE_MARKER.format(page["pdf_page"]))
        output.append("")
        output.append(page["text"].strip())
        output.append("")
    return "\n".join(output).strip() + "\n"


def process_book(code: str, title: str) -> dict:
    book_dir = ROOT / code
    pdf_path = book_dir / f"{code}.pdf"

    print()
    print("=" * 72)
    print(f"{code.upper()} — {title}")
    print("=" * 72)

    if not book_dir.exists():
        print(f"SKIP: Folder does not exist: {book_dir}")
        return {"code": code, "title": title, "status": "missing_folder"}

    if not pdf_path.exists():
        print(f"SKIP: Source PDF does not exist: {pdf_path}")
        return {"code": code, "title": title, "status": "missing_pdf"}

    create_book_structure(book_dir)

    source_dir = book_dir / "source"
    extracted_dir = book_dir / "extracted"
    manifest_dir = book_dir / "manifests"

    print("  [1/6] Hashing original PDF...")
    original_hash = sha256_file(pdf_path)
    original_size = pdf_path.stat().st_size

    source_copy = source_dir / f"{code}_original.pdf"

    print("  [2/6] Preserving source copy...")
    if not source_copy.exists():
        shutil.copy2(pdf_path, source_copy)

    source_copy_hash = sha256_file(source_copy)
    if source_copy_hash != original_hash:
        raise RuntimeError(
            f"Source-copy hash mismatch for {code}. Processing stopped."
        )

    print("  [3/6] Extracting page-aware text...")
    pages, image_inventory = extract_pdf(pdf_path)

    raw_text = build_page_aware_text(pages)
    raw_txt_path = extracted_dir / f"{code}_page_aware_raw.txt"
    write_utf8(raw_txt_path, raw_text)

    print("  [4/6] Normalizing extracted text...")
    normalized_sections = []

    for page in pages:
        normalized_sections.append(PAGE_MARKER.format(page["pdf_page"]))
        normalized_sections.append("")
        normalized_sections.append(normalize_text(page["text"]))
        normalized_sections.append("")

    normalized_text = "\n".join(normalized_sections).strip() + "\n"
    normalized_txt_path = extracted_dir / f"{code}_normalized.txt"
    write_utf8(normalized_txt_path, normalized_text)

    print("  [5/6] Writing inventories...")
    page_manifest = [
        {
            "pdf_page": page["pdf_page"],
            "character_count": page["character_count"],
            "image_count": page["image_count"],
        }
        for page in pages
    ]

    write_json(manifest_dir / f"{code}_pages.json", page_manifest)
    write_json(manifest_dir / f"{code}_images.json", image_inventory)

    print("  [6/6] Writing audit manifest...")
    extraction_time = datetime.now(timezone.utc).isoformat()

    manifest = {
        "schema_version": "0.1",
        "book_code": code,
        "book_title": title,
        "status": "complete",
        "source": {
            "original_path": str(pdf_path),
            "preserved_copy": str(source_copy),
            "size_bytes": original_size,
            "sha256": original_hash,
        },
        "extraction": {
            "utc_timestamp": extraction_time,
            "pdf_pages": len(pages),
            "images_referenced": len(image_inventory),
            "raw_text_path": str(raw_txt_path),
            "normalized_text_path": str(normalized_txt_path),
            "raw_text_sha256": sha256_file(raw_txt_path),
            "normalized_text_sha256": sha256_file(normalized_txt_path),
        },
        "processing_policy": {
            "source_modified": False,
            "images_deleted": False,
            "text_deleted": False,
            "llm_used": False,
            "embeddings_used": False,
            "classification_performed": False,
        },
    }

    manifest_path = manifest_dir / f"{code}_manifest.json"
    write_json(manifest_path, manifest)

    print()
    print(f"  COMPLETE: {code.upper()}")
    print(f"  Pages:    {len(pages):,}")
    print(f"  Images:   {len(image_inventory):,}")
    print(f"  TXT:      {normalized_txt_path}")

    return manifest


def main():
    print()
    print("BOOK BUCKET — CORPUS BUILDER v0.1")
    print(f"Root: {ROOT}")
    print()

    if not ROOT.exists():
        print(f"ERROR: Root folder does not exist:\n{ROOT}")
        sys.exit(1)

    results = []

    for code, title in BOOKS.items():
        try:
            results.append(process_book(code, title))
        except Exception as exc:
            print()
            print(f"ERROR processing {code.upper()}: {exc}")
            results.append(
                {
                    "code": code,
                    "title": title,
                    "status": "error",
                    "error": str(exc),
                }
            )

    master_manifest = {
        "schema_version": "0.1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "books": results,
    }

    write_json(ROOT / "book_bucket_manifest.json", master_manifest)

    print()
    print("=" * 72)
    print("BOOK BUCKET PASS COMPLETE")
    print("=" * 72)

    for result in results:
        code = result.get("book_code", result.get("code", "??"))
        status = result.get("status", "unknown")
        print(f"{code.upper():4} {status}")

    print()
    print("Master manifest:", ROOT / "book_bucket_manifest.json")


if __name__ == "__main__":
    main()
