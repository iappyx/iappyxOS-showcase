#!/usr/bin/env python3
"""
step1b_classify.py
==================
Adds a 'type' field to nl_articles.json and a 'type' column to nl.db
by looking up the Wikidata 'instance of' (P31) property for each article.

Pipeline:
    1. Download nlwiki-latest-page_props.sql.gz (~51 MB)
       → maps page_id → Wikidata QID (e.g. Q515)
    2. Batch query Wikidata API (50 QIDs per call, ~1120 calls total)
       → maps QID → type label (e.g. "city", "village", "hamlet")
    3. Update nl_articles.json with type field
    4. Add type column to nl.db and populate it

Usage:
    python step1b_classify.py --country NL
    python step1b_classify.py --country NL --db nl.db
"""

import requests
import json
import gzip
import re
import time
import sys
import sqlite3
import argparse
from pathlib import Path

DUMP_BASE = "https://dumps.wikimedia.org/{wiki}/latest"

LANG_MAP = {
    "NL": "nl", "BE": "nl", "DE": "de",
    "FR": "fr", "GB": "en", "ES": "es", "IT": "it",
}

# Wikidata QID → type label
# Covers the most common types found in Dutch Wikipedia geotagged articles
QTYPE_MAP = {
    # Settlements
    "Q515":     "city",
    "Q1549591": "city",        # big city
    "Q3957":    "town",
    "Q532":     "village",
    "Q5084":    "hamlet",
    "Q56436498":"hamlet",
    "Q747074":  "municipality",
    "Q2039348": "municipality",
    "Q756927":  "neighbourhood",
    "Q123705":  "neighbourhood",
    "Q21672098":"neighbourhood",
    "Q3840711": "polder",
    "Q253030":  "polder",

    # Water
    "Q8514":    "lake",
    "Q4022":    "river",
    "Q12284":   "canal",
    "Q9430":    "ocean",
    "Q166620":  "reservoir",
    "Q177380":  "waterway",
    "Q46831":   "stream",
    "Q1437698": "lock",        # sluis
    "Q2003221": "lock",

    # Infrastructure
    "Q44782":   "port",
    "Q55488":   "railway station",
    "Q34442":   "road",
    "Q12280":   "bridge",
    "Q1248784": "airport",
    "Q18503":   "highway",

    # Buildings / landmarks
    "Q16560":   "palace",
    "Q44613":   "monastery",
    "Q16970":   "church",
    "Q24398318":"church",
    "Q33506":   "museum",
    "Q570116":  "windmill",
    "Q38723":   "windmill",
    "Q40357":   "castle",
    "Q23413":   "castle",
    "Q44377":   "tower",
    "Q39614":   "cemetery",
    "Q131596":  "nature reserve",
    "Q179049":  "national park",
    "Q22698":   "park",
    "Q483110":  "stadium",
    "Q27686":   "hotel",
    "Q41176":   "building",
    "Q811979":  "building",

    # Geography
    "Q34038":   "island",
    "Q185113":  "polder",
    "Q11799049":"nature area",
    "Q179049":  "nature reserve",
}

# Types to deprioritise or skip in the app
SKIP_TYPES = {
    "Q4167836",  # Wikimedia category
    "Q13406463", # Wikimedia list article
    "Q17362920", # Wikimedia duplicated page
    "Q4167410",  # Wikimedia template
    "Q11266439", # Wikimedia module
}


# ---------------------------------------------------------------------------
# Download with progress
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
                    f"\r  {done/1_048_576:.1f} / {total/1_048_576:.1f} MB "
                    f"({done/total*100:.0f}%)  "
                )
                sys.stdout.flush()
    print(f"\n  Saved: {dest} ({Path(dest).stat().st_size/1_048_576:.1f} MB)")


# ---------------------------------------------------------------------------
# Step 1 — Parse page_props dump → {page_id: QID}
# Columns: (pp_page, pp_propname, pp_value, pp_sortkey)
# We want pp_propname = 'wikibase_item'
# ---------------------------------------------------------------------------
def parse_page_props(gz_path):
    print(f"  Parsing {gz_path}...")
    qids    = {}
    pattern = re.compile(r"\((\d+),'wikibase_item','(Q\d+)',")
    with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("INSERT INTO"):
                continue
            for m in pattern.finditer(line):
                qids[int(m.group(1))] = m.group(2)
    print(f"  Found {len(qids):,} page → Wikidata QID mappings")
    return qids


# ---------------------------------------------------------------------------
# Step 2 — Batch query Wikidata API for instance_of labels
# Returns {QID: type_label}
# ---------------------------------------------------------------------------
def fetch_wikidata_types(qids_needed, cache_file):
    # Load cache
    cache = {}
    if Path(cache_file).exists():
        with open(cache_file) as f:
            cache = json.load(f)
        print(f"  Loaded {len(cache):,} cached QID types")

    remaining = [q for q in qids_needed if q not in cache]
    if not remaining:
        print(f"  All QID types already cached.")
        return cache

    print(f"  Querying Wikidata for {len(remaining):,} QIDs ({len(remaining)//50 + 1} batches)...")

    session = requests.Session()
    session.headers["User-Agent"] = "RoadTripClassifier/1.0 (educational project; python-requests)"

    BATCH = 50
    batches = [remaining[i:i+BATCH] for i in range(0, len(remaining), BATCH)]

    for b_idx, batch in enumerate(batches):
        params = {
            "action":   "wbgetentities",
            "ids":      "|".join(batch),
            "props":    "claims",
            "format":   "json",
        }
        for attempt in range(4):
            try:
                r = session.get(
                    "https://www.wikidata.org/w/api.php",
                    params=params, timeout=30
                )
                r.raise_for_status()
                data = r.json()

                for qid, entity in data.get("entities", {}).items():
                    claims = entity.get("claims", {})
                    p31    = claims.get("P31", [])

                    # Get all instance_of values, prefer known types
                    type_label = "other"
                    for claim in p31:
                        val = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                        val_qid = val.get("id", "")
                        if val_qid in SKIP_TYPES:
                            type_label = "skip"
                            break
                        if val_qid in QTYPE_MAP:
                            type_label = QTYPE_MAP[val_qid]
                            break

                    cache[qid] = type_label
                break

            except Exception as e:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                else:
                    # Mark as unknown so we don't retry forever
                    for qid in batch:
                        if qid not in cache:
                            cache[qid] = "other"

        if (b_idx + 1) % 50 == 0:
            with open(cache_file, "w") as f:
                json.dump(cache, f)
            sys.stdout.write(
                f"\r  Batch {b_idx+1}/{len(batches)} — "
                f"{len(cache):,} types known..."
            )
            sys.stdout.flush()

        time.sleep(0.1)  # Wikidata is generous but let's be polite

    with open(cache_file, "w") as f:
        json.dump(cache, f)

    print(f"\n  Done: {len(cache):,} QID types cached → {cache_file}")
    return cache


# ---------------------------------------------------------------------------
# Step 3 — Update articles.json with type field
# ---------------------------------------------------------------------------
def update_articles(articles_file, page_to_qid, qid_to_type):
    with open(articles_file) as f:
        articles = json.load(f)

    updated = 0
    for title, info in articles.items():
        page_id = info.get("pageid")
        if page_id is None:
            continue
        qid = page_to_qid.get(int(page_id))
        if qid is None:
            continue
        type_label = qid_to_type.get(qid, "other")
        if type_label != info.get("type"):
            info["type"] = type_label
            updated += 1

    with open(articles_file, "w") as f:
        json.dump(articles, f, ensure_ascii=False)

    # Show distribution
    from collections import Counter
    counts = Counter(
        info.get("type", "unknown")
        for info in articles.values()
    )
    print(f"\n  Updated {updated:,} articles in {articles_file}")
    print(f"  Type distribution:")
    for t, n in counts.most_common(15):
        print(f"    {t:<20} {n:,}")

    return articles


# ---------------------------------------------------------------------------
# Step 4 — Add type column to SQLite database
# ---------------------------------------------------------------------------
def update_database(db_path, articles):
    if not Path(db_path).exists():
        print(f"  {db_path} not found — skipping DB update")
        print(f"  (type is already in nl_articles.json for next step2 run)")
        return

    conn = sqlite3.connect(db_path)
    c    = conn.cursor()

    # Add column if it doesn't exist
    cols = [row[1] for row in c.execute("PRAGMA table_info(locations)")]
    if "type" not in cols:
        c.execute("ALTER TABLE locations ADD COLUMN type TEXT")
        print(f"  Added 'type' column to {db_path}")

    # Update each row
    updated = 0
    for title, info in articles.items():
        type_label = info.get("type")
        if type_label:
            c.execute(
                "UPDATE locations SET type = ? WHERE title = ?",
                (type_label, title)
            )
            if c.rowcount > 0:
                updated += 1

    conn.commit()
    conn.close()
    print(f"  Updated {updated:,} rows in {db_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Classify article types using Wikidata instance_of"
    )
    parser.add_argument("--country", default="NL",
                        help="Country code (default: NL)")
    parser.add_argument("--db", default=None,
                        help="SQLite database to update (default: {country}.db)")
    args = parser.parse_args()

    country       = args.country.upper()
    lang          = LANG_MAP.get(country, "en")
    wiki          = f"{lang}wiki"
    articles_file = f"{country.lower()}_articles.json"
    props_gz      = f"{wiki}-latest-page_props.sql.gz"
    cache_file    = f"{country.lower()}_qid_types.json"
    db_path       = args.db or f"{country.lower()}.db"

    if not Path(articles_file).exists():
        print(f"Error: {articles_file} not found — run step1_fetch.py first.")
        return

    print(f"\n=== step1b_classify.py ===")
    print(f"Country  : {country}")
    print(f"Articles : {articles_file}")
    print(f"Database : {db_path}\n")

    # Load articles
    with open(articles_file) as f:
        articles = json.load(f)
    print(f"  Loaded {len(articles):,} articles")

    # Step 1: download + parse page_props dump
    print(f"\n[1/4] Downloading page_props dump...")
    base_url = DUMP_BASE.format(wiki=wiki)
    download(f"{base_url}/{props_gz}", props_gz)

    print(f"\n[2/4] Parsing page_props dump...")
    page_to_qid = parse_page_props(props_gz)

    # Get QIDs for our articles only
    qids_needed = set()
    for info in articles.values():
        page_id = info.get("pageid")
        if page_id and int(page_id) in page_to_qid:
            qids_needed.add(page_to_qid[int(page_id)])

    print(f"  {len(qids_needed):,} unique QIDs to look up")

    # Step 2: fetch types from Wikidata
    print(f"\n[3/4] Fetching instance_of types from Wikidata API...")
    qid_to_type = fetch_wikidata_types(qids_needed, cache_file)

    # Step 3: update articles.json
    print(f"\n[4/4] Updating articles and database...")
    articles = update_articles(articles_file, page_to_qid, qid_to_type)

    # Step 4: update SQLite
    update_database(db_path, articles)

    print(f"\n=== Done ===")
    print(f"  {articles_file} updated with type field")
    print(f"  {db_path} updated with type column")
    print(f"\nRe-run step2_rewrite.py to include type in new DB rows.")


if __name__ == "__main__":
    main()

