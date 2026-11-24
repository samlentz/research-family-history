#!/usr/bin/env python3
"""Locate candidate pages in a local PDF or page-separated UTF-8 text file."""
import argparse
import itertools
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path


def split_pages(text):
    pages = text.split("\f")
    if len(pages) > 1 and pages[-1] == "":
        pages.pop()  # A terminal form feed closes the last physical page.
    return pages


def read_pages(path):
    if path.suffix.lower() == ".txt":
        yield from split_pages(path.read_text(encoding="utf-8-sig"))
        return
    if path.suffix.lower() != ".pdf":
        raise ValueError("Choose a PDF or a UTF-8 .txt file with form-feed page breaks.")
    converter = shutil.which("pdftotext")
    if converter:
        result = subprocess.run(
            [converter, "-layout", "-enc", "UTF-8", str(path.resolve()), "-"],
            capture_output=True, check=False,
        )
        if result.returncode:
            raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
        yield from split_pages(result.stdout.decode("utf-8"))
        return
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("PDF input needs pdftotext or pypdf. You can also supply page-separated text.") from None
    for page in PdfReader(path).pages:
        yield page.extract_text() or ""


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).replace("\u00ad", "").split())


def ranges(numbers):
    parts = []
    for _, group in itertools.groupby(enumerate(numbers), key=lambda pair: pair[1] - pair[0]):
        run = [n for _, n in group]
        parts.append(str(run[0]) if len(run) == 1 else f"{run[0]}–{run[-1]}")
    return ", ".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("volume", type=Path)
    parser.add_argument("terms", nargs="+", help="Literal names or phrases. Quote each multiword phrase.")
    args = parser.parse_args()
    terms = list(dict.fromkeys(normalize(term) for term in args.terms))
    if "" in terms:
        parser.error("Each search term must contain text.")
    patterns = [(term, re.compile(re.escape(term), re.IGNORECASE)) for term in terms]
    missing = []
    total = matched = 0
    try:
        for total, page in enumerate(read_pages(args.volume), 1):
            text = normalize(page)
            if not text:
                missing.append(total)
                continue
            page_hit = False
            for term, pattern in patterns:
                hit = pattern.search(text)
                if hit:
                    page_hit = True
                    context = text[max(0, hit.start() - 55):hit.end() + 55]
                    print(f"Page {total} | {term} | {context}")
            matched += int(page_hit)
    except Exception as error:
        parser.exit(2, f"Could not finish reading {args.volume.name}: {error}\n")
    print(f"{matched} matching page(s) across {total} page(s). Check the original images.", file=sys.stderr)
    if missing:
        print(f"No extractable text on page(s) {ranges(missing)}. Inspect their images.", file=sys.stderr)


if __name__ == "__main__":
    main()
