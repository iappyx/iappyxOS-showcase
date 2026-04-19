#!/usr/bin/env python3
"""
step1_fetch.py
==============
Builds a complete article database from Wikimedia dumps only.
Zero API calls. Zero rate limits. Complete coverage.

Downloads:
    nlwiki-latest-geo_tags.sql.gz          ~3.5 MB  — all coordinates
    nlwiki-latest-page.sql.gz              ~144 MB  — all page titles
    nlwiki-latest-pages-articles.xml.bz2  ~1.9 GB  — all article text

Outputs:
    {country}_articles.json   — {title: {lat, lon, pageid}}
    {country}_texts.json      — {title: "plain text up to 4000 chars"}

Usage:
    pip install requests mwparserfromhell
    python step1_fetch.py --country NL
"""

import requests
import json
import gzip
import bz2
import re
import sys
import argparse
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    import mwparserfromhell
except ImportError:
    print("Error: mwparserfromhell not installed.")
    print("Run: pip install mwparserfromhell")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BOUNDING_BOXES = {
    "NL": (50.75, 53.55, 3.35, 7.22),
    "BE": (49.50, 51.50, 2.55, 6.40),
    "DE": (47.30, 55.05, 6.00, 15.05),
    "FR": (41.30, 51.10, -5.15, 9.55),
    "GB": (49.90, 58.70, -7.60, 1.80),
    "ES": (35.95, 43.75, -9.30, 4.30),
    "IT": (36.65, 47.10, 6.65, 18.52),
}

LANG_MAP = {
    "NL": "nl", "BE": "nl", "DE": "de",
    "FR": "fr", "GB": "en", "ES": "es", "IT": "it",
}

DUMP_BASE = "https://dumps.wikimedia.org/{wiki}/latest"


# ---------------------------------------------------------------------------
# Download with progress bar
# ---------------------------------------------------------------------------
def download(url, dest):
    if Path(dest).exists():
        mb = Path(dest).stat().st_size / 1_048_576
        print(f"  Already downloaded: {dest} ({mb:.1f} MB)")
        return
    print(f"  Downloading {url}")
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    done  = 0
    with open(dest, "wb") as f:
        for chunk in r.iter_content(1024 * 256):
            f.write(chunk)
            done += len(chunk)
            if total:
                sys.stdout.write(
                    f"\r  {done/1_048_576:.1f} MB / {total/1_048_576:.1f} MB "
                    f"({done/total*100:.0f}%)  "
                )
                sys.stdout.flush()
    print(f"\n  Saved: {dest} ({Path(dest).stat().st_size/1_048_576:.1f} MB)")


# ---------------------------------------------------------------------------
# Parse geo_tags dump → {page_id: (lat, lon)}
# Columns: (gt_id, page_id, globe, primary, lat, lon, ...)
# ---------------------------------------------------------------------------
def parse_geo_tags(gz_path):
    print(f"  Parsing {gz_path}...")
    coords  = {}
    pattern = re.compile(r"\(\d+,(\d+),'earth',1,(-?\d+\.?\d*),(-?\d+\.?\d*)")
    with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("INSERT INTO"):
                continue
            for m in pattern.finditer(line):
                coords[int(m.group(1))] = (float(m.group(2)), float(m.group(3)))
    print(f"  Found {len(coords):,} geotagged pages")
    return coords


# ---------------------------------------------------------------------------
# Parse page dump → {page_id: title}  (namespace 0, non-redirects only)
# Columns: (page_id, namespace, title, is_redirect, ...)
# ---------------------------------------------------------------------------
def parse_pages(gz_path):
    print(f"  Parsing {gz_path} (takes ~30 sec)...")
    titles  = {}
    pattern = re.compile(r"\((\d+),0,'((?:[^'\\]|\\.)*)',0,")
    with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("INSERT INTO"):
                continue
            for m in pattern.finditer(line):
                page_id = int(m.group(1))
                title   = (m.group(2)
                           .replace("\\'", "'")
                           .replace("\\\\", "\\")
                           .replace("_", " "))
                titles[page_id] = title
    print(f"  Found {len(titles):,} article titles")
    return titles


# ---------------------------------------------------------------------------
# Build articles.json from geo_tags + page dumps
# ---------------------------------------------------------------------------
def build_articles(bbox, lang, articles_file):
    existing = {}
    if Path(articles_file).exists():
        with open(articles_file) as f:
            existing = json.load(f)
        print(f"  Loaded {len(existing):,} existing articles")

    wiki     = f"{lang}wiki"
    base_url = DUMP_BASE.format(wiki=wiki)
    geo_gz   = f"{wiki}-latest-geo_tags.sql.gz"
    page_gz  = f"{wiki}-latest-page.sql.gz"

    print(f"\n[1/3] Downloading coordinate + title dumps...")
    download(f"{base_url}/{geo_gz}",  geo_gz)
    download(f"{base_url}/{page_gz}", page_gz)

    print(f"\n  Parsing...")
    coords = parse_geo_tags(geo_gz)
    titles = parse_pages(page_gz)

    min_lat, max_lat, min_lon, max_lon = bbox
    articles  = dict(existing)
    new_count = 0

    for page_id, (lat, lon) in coords.items():
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            continue
        if page_id not in titles:
            continue
        title = titles[page_id]
        if title not in articles:
            articles[title] = {"lat": lat, "lon": lon, "pageid": page_id}
            new_count += 1

    with open(articles_file, "w") as f:
        json.dump(articles, f, ensure_ascii=False)

    print(f"  Total: {len(articles):,} articles in bbox ({new_count:,} new)")
    print(f"  Saved → {articles_file}")
    return articles


# ---------------------------------------------------------------------------
# Parse full article text from XML dump
# Streams through the bz2 file — never loads it all into memory
# ---------------------------------------------------------------------------
def parse_article_texts(bz2_path, titles_wanted, texts_file, min_chars=100):
    # Load existing cache so we can resume if interrupted
    texts = {}
    if Path(texts_file).exists():
        with open(texts_file) as f:
            texts = json.load(f)
        print(f"  Resuming — {len(texts):,} texts already extracted")

    remaining = {t for t in titles_wanted if t not in texts}
    if not remaining:
        print(f"  All texts already extracted.")
        return texts

    print(f"  Extracting text for {len(remaining):,} articles from XML dump...")
    print(f"  (Streaming through {Path(bz2_path).stat().st_size/1_048_576:.0f} MB — takes a few minutes)")

    found    = 0
    scanned  = 0
    NS       = "{http://www.mediawiki.org/xml/export-0.11/}"

    with bz2.open(bz2_path, "rb") as raw:
        context = ET.iterparse(raw, events=("end",))
        for event, elem in context:
            if elem.tag != f"{NS}page":
                continue

            scanned += 1
            title_elem = elem.find(f"{NS}title")
            if title_elem is None or title_elem.text not in remaining:
                elem.clear()
                continue

            title = title_elem.text

            # Skip non-article namespaces
            ns_elem = elem.find(f"{NS}ns")
            if ns_elem is not None and ns_elem.text != "0":
                elem.clear()
                continue

            # Get wikitext
            text_elem = elem.find(f".//{NS}text")
            raw_text  = (text_elem.text or "") if text_elem is not None else ""

            # Strip wikitext markup to plain text
            try:
                wikicode   = mwparserfromhell.parse(raw_text)
                plain_text = wikicode.strip_code().strip()
            except Exception:
                plain_text = raw_text[:4000]

            if len(plain_text) >= min_chars:
                texts[title] = plain_text[:4000]
                found += 1

            remaining.discard(title)
            elem.clear()

            if found % 1000 == 0 and found > 0:
                with open(texts_file, "w") as f:
                    json.dump(texts, f, ensure_ascii=False)
                mb = Path(texts_file).stat().st_size / 1_048_576
                sys.stdout.write(
                    f"\r  Scanned {scanned:,} pages — "
                    f"{found:,} extracted — "
                    f"{mb:.1f} MB — "
                    f"{len(remaining):,} still to find..."
                )
                sys.stdout.flush()

            if not remaining:
                break  # found everything we need — stop early

    # Final save
    with open(texts_file, "w") as f:
        json.dump(texts, f, ensure_ascii=False)

    mb = Path(texts_file).stat().st_size / 1_048_576
    print(f"\n  Done: {len(texts):,} texts extracted ({mb:.1f} MB)")
    if remaining:
        print(f"  {len(remaining):,} articles not found in dump "
              f"(deleted, redirects, or stubs below {min_chars} chars)")
    return texts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Build road trip article database from Wikimedia dumps"
    )
    parser.add_argument("--country", default="NL",
                        choices=list(BOUNDING_BOXES.keys()),
                        help="Country code (default: NL)")
    parser.add_argument("--min-chars", type=int, default=100,
                        help="Minimum article length to include (default: 100)")
    args = parser.parse_args()

    country       = args.country.upper()
    lang          = LANG_MAP.get(country, "en")
    bbox          = BOUNDING_BOXES[country]
    wiki          = f"{lang}wiki"
    articles_file = f"{country.lower()}_articles.json"
    texts_file    = f"{country.lower()}_texts.json"
    xml_bz2       = f"{wiki}-latest-pages-articles.xml.bz2"
    base_url      = DUMP_BASE.format(wiki=wiki)

    print(f"\n=== Step 1-2: Build article database from dumps ===")
    print(f"Country  : {country}")
    print(f"Language : {lang}.wikipedia.org")
    print(f"Bbox     : lat {bbox[0]}–{bbox[1]}, lon {bbox[2]}–{bbox[3]}\n")

    # Step 1: build articles.json from coordinate + title dumps
    articles = build_articles(bbox, lang, articles_file)

    # Step 2: download XML dump if needed, then extract texts
    print(f"\n[2/3] Downloading full article text dump (~1.9 GB, one-time)...")
    download(f"{base_url}/{xml_bz2}", xml_bz2)

    print(f"\n[3/3] Extracting article texts...")
    texts = parse_article_texts(xml_bz2, set(articles.keys()), texts_file, args.min_chars)

    sz_mb = Path(texts_file).stat().st_size / 1_048_576
    print(f"\n=== Done ===")
    print(f"  {articles_file}  ({len(articles):,} locations)")
    print(f"  {texts_file}     ({len(texts):,} with content, {sz_mb:.1f} MB)")
    print(f"\nNext:")
    print(f"  python step2_rewrite.py --country {country}")


if __name__ == "__main__":
    main()