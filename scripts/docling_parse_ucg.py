#!/usr/bin/env python3
from pathlib import Path
import json
import sys

from docling.document_converter import DocumentConverter

PDF_PATH = Path("data/Uganda_Clinical_Guidelines_2023.pdf")
OUT_DIR = Path("data/docling_outputs")
MARKDOWN_PATH = OUT_DIR / "ucg23_docling.md"
JSON_PATH = OUT_DIR / "ucg23_docling.json"


def main():
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH.resolve()}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"🚀 Parsing PDF with Docling...")
    converter = DocumentConverter()
    result = converter.convert(str(PDF_PATH))
    doc = result.document

    # save markdown
    markdown = doc.export_to_markdown()
    MARKDOWN_PATH.write_text(markdown, encoding="utf-8")
    print(f"✅ Wrote markdown → {MARKDOWN_PATH}")

    # save structured JSON
    doc_dict = doc.export_to_dict()
    JSON_PATH.write_text(json.dumps(doc_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Wrote docling JSON → {JSON_PATH}")

    print("🎉 Done parsing UCG-23!")


if __name__ == "__main__":
    main()
