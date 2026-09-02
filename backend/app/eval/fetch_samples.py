"""Download the pinned eval sample PDFs listed in tests/fixtures/samples.json.

Only fetches URLs already pinned in samples.json -- no crawling, no ID
guessing. interapp4.rd.go.th/TPW/ has no robots.txt and serves these as
static paths, but the IDs are non-sequential, so URLs must stay pinned
rather than enumerated (see the plan's source-vetting notes).

Usage:
    python -m app.eval.fetch_samples
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from app.pdf.extract import extract_document

FIXTURES_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "samples.json"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "samples"
USER_AGENT = "tor-analysis-eval-fetch/0.1 (research script for a TOR-extraction eval; no scraping beyond pinned URLs)"
DEFAULT_DELAY_SECONDS = 1.0  # be polite by default -- sequential only, never parallel


def _download(url: str, dest: Path) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    dest.write_bytes(data)
    return data


def main() -> int:
    samples = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["samples"]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for i, sample in enumerate(samples):
        if i > 0:
            # some sources (e.g. audit.go.th) require a longer Crawl-delay --
            # honor it per-sample instead of assuming one delay fits every source
            time.sleep(sample.get("min_delay_seconds", DEFAULT_DELAY_SECONDS))

        dest = OUTPUT_DIR / f"{sample['id']}.pdf"
        print(f"fetching {sample['id']} <- {sample['url']}")
        try:
            data = _download(sample["url"], dest)
        except Exception as exc:  # noqa: BLE001 -- report and continue to the next sample
            print(f"  ERROR: download failed: {exc}", file=sys.stderr)
            continue

        if len(data) != sample["content_length"]:
            print(
                f"  WARNING: size changed since pinned ({sample['content_length']} -> "
                f"{len(data)} bytes) -- source file may have been replaced",
                file=sys.stderr,
            )

        result = extract_document(str(dest))
        ratio = result.scan_report.usable_text_ratio
        print(
            f"  {len(data)} bytes, {result.scan_report.page_count} pages, "
            f"usable_text_ratio={ratio:.0%}"
        )
        if ratio == 0.0:
            print(
                f"  WARNING: {sample['id']} has no extractable text at all (scanned) "
                f"-- not usable as an eval fixture in v0.1 (no OCR)",
                file=sys.stderr,
            )

        bad_fonts = result.scan_report.all_fonts_without_tounicode
        if bad_fonts:
            # NOTE: this is informational only, not a reliable pass/fail signal --
            # TH Sarabun subset fonts commonly lack /ToUnicode yet still render fine
            # via an internal cmap. It only actually breaks output for some fonts
            # (confirmed for one sample tagged "Helvetica" -- clearly a mislabeled/
            # broken font resource). There's no cheap automated way found so far to
            # tell the two cases apart short of reading the extracted text; manual
            # verification remains necessary regardless of this warning.
            print(
                f"  NOTE: {sample['id']} has fonts without a /ToUnicode CMap "
                f"({', '.join(bad_fonts)}) -- usually harmless for TH Sarabun subsets, "
                f"but verify the extracted text is real Thai and not scrambled before "
                f"using this as an eval fixture.",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
