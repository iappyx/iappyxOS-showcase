#!/usr/bin/env python3
"""
step2_rewrite.py
================
Rewrites Wikipedia article text into spoken road trip sentences using
Claude Haiku Batch API, then stores results in the location_texts table.

Schema:
    locations(id, title, lat, lon, raw_summary, type)
    location_texts(location_id, language, spoken_text)

Supports multiple languages — run once per language:
    python step2_rewrite.py --country NL --language en
    python step2_rewrite.py --country NL --language nl

Only submits articles not yet in location_texts for that language.

Usage:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python step2_rewrite.py --country NL
    python step2_rewrite.py --country NL --language nl
"""

import anthropic
import sqlite3
import json
import time
import sys
import os
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Prompts per language
# ---------------------------------------------------------------------------
PROMPTS = {
    "en": {
        "system": (
            "You are a knowledgeable, friendly passenger in a car on a road trip through the Netherlands. "
            "The driver is passing a location. Your job is to say one genuinely interesting thing about it "
            "— something that makes them feel the place is alive and worth noticing. "
            "Write exactly 2 sentences in natural spoken English. "
            "No lists, no headers, no markdown. "
            "Start directly with the interesting fact. "
            "Do not start with 'You are passing' or 'You are driving'. "
            "The source text may be in Dutch — write your response in English regardless. "
            "If the text contains nothing interesting beyond basic administrative facts, "
            "just describe what the place is in 2 plain sentences. Never invent facts."
        ),
        "prompt": (
            "Location: {title}\n"
            "Wikipedia text: {extract}\n\n"
            "Write 2 spoken English sentences about this location for a road trip audio guide."
        ),
    },
    "nl": {
        "system": (
            "Je bent een enthousiaste, goed geïnformeerde passagier in een auto op een roadtrip door Nederland. "
            "De bestuurder rijdt langs een locatie. Jouw taak is om één oprecht interessant feit te vertellen "
            "— iets waardoor de bestuurder het gevoel krijgt dat de plek de moeite waard is. "
            "Schrijf precies 2 zinnen in natuurlijk gesproken Nederlands. "
            "Geen lijstjes, geen opmaak. "
            "Begin direct met het interessante feit. "
            "Begin niet met 'Je rijdt langs' of 'Je passeert'. "
            "Als de tekst niets interessants bevat buiten basisfeiten, "
            "beschrijf dan gewoon wat de plek is in 2 eenvoudige zinnen. Verzin nooit feiten."
        ),
        "prompt": (
            "Locatie: {title}\n"
            "Wikipedia tekst: {extract}\n\n"
            "Schrijf 2 gesproken Nederlandse zinnen over deze locatie voor een roadtrip audiogids."
        ),
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ensure_schema(db_path):
    """Create tables if they don't exist. Safe to call on existing DB."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL UNIQUE,
            lat         REAL NOT NULL,
            lon         REAL NOT NULL,
            raw_summary TEXT,
            type        TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS location_texts (
            location_id  INTEGER NOT NULL REFERENCES locations(id),
            language     TEXT    NOT NULL,
            spoken_text  TEXT    NOT NULL,
            PRIMARY KEY (location_id, language)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lat  ON locations(lat)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lon  ON locations(lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lang ON location_texts(language)")
    conn.commit()
    conn.close()


def load_existing_titles(db_path):
    """Titles already in locations table."""
    if not Path(db_path).exists():
        return set()
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT title FROM locations").fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


def load_translated_titles(db_path, language):
    """Titles that already have a spoken_text for this language."""
    if not Path(db_path).exists():
        return set()
    try:
        conn = sqlite3.connect(db_path)
        # Check if location_texts table exists
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "location_texts" not in tables:
            conn.close()
            return set()
        rows = conn.execute("""
            SELECT l.title FROM locations l
            JOIN location_texts lt ON lt.location_id = l.id
            WHERE lt.language = ?
        """, (language,)).fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Step 3 — Submit batch (only titles missing for this language)
# ---------------------------------------------------------------------------
def submit_batch(articles, texts, batch_id_file, db_path, language):
    client = anthropic.Anthropic()

    # Titles already in locations table (for any language)
    existing_titles = load_existing_titles(db_path)
    # Titles already translated for THIS language
    translated_titles = load_translated_titles(db_path, language)

    if translated_titles:
        print(f"      {len(translated_titles):,} titles already have '{language}' text — skipping")

    prompts = PROMPTS[language]
    id_to_title  = {}
    requests_list = []
    idx = 0

    for title, extract in texts.items():
        if title not in articles:
            continue
        if title in translated_titles:
            continue  # already have this language — skip
        custom_id = f"loc_{idx}"
        id_to_title[custom_id] = title
        requests_list.append({
            "custom_id": custom_id,
            "params": {
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 150,
                "system":     prompts["system"],
                "messages": [{
                    "role":    "user",
                    "content": prompts["prompt"].format(
                        title=title,
                        extract=extract[:800]
                    )
                }],
            }
        })
        idx += 1

    if not requests_list:
        print(f"[3/4] Nothing new for language='{language}' — already up to date.")
        return None

    mapping_file = batch_id_file.replace("_batch_id.txt", "_id_map.json")
    with open(mapping_file, "w") as f:
        json.dump(id_to_title, f, ensure_ascii=False)

    n = len(requests_list)
    est_input  = n * 280 / 1_000_000 * 0.50
    est_output = n * 70  / 1_000_000 * 2.50
    print(f"[3/4] Submitting {n:,} requests (language='{language}') to Claude Haiku Batch API...")
    print(f"      Estimated cost: ${est_input:.2f} + ${est_output:.2f} = ${est_input+est_output:.2f}")

    response = client.beta.messages.batches.create(requests=requests_list)
    batch_id = response.id

    with open(batch_id_file, "w") as f:
        f.write(batch_id)

    print(f"      Batch ID : {batch_id}  (saved to {batch_id_file})")
    print(f"      Status   : {response.processing_status}")
    return batch_id


# ---------------------------------------------------------------------------
# Step 3b — Poll
# ---------------------------------------------------------------------------
def wait_for_batch(batch_id):
    client = anthropic.Anthropic()
    print("[3/4] Waiting for batch (typically 1–2 hours)...")
    dots = 0
    while True:
        batch  = client.beta.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        counts = batch.request_counts
        sys.stdout.write(
            f"\r      {status} | "
            f"processing={counts.processing}  "
            f"succeeded={counts.succeeded}  "
            f"errored={counts.errored}  "
            f"{'.' * (dots % 4)}   "
        )
        sys.stdout.flush()
        dots += 1
        if status == "ended":
            print(f"\n      Complete: {counts.succeeded} succeeded, {counts.errored} errors")
            return
        if status in ("canceling", "canceled"):
            print("\n      Batch was canceled.")
            sys.exit(1)
        time.sleep(30)


# ---------------------------------------------------------------------------
# Step 4 — Download results and write to location_texts
# ---------------------------------------------------------------------------
def build_database(batch_id, articles, texts, db_path, batch_id_file, language):
    client = anthropic.Anthropic()

    mapping_file = batch_id_file.replace("_batch_id.txt", "_id_map.json")
    with open(mapping_file) as f:
        id_to_title = json.load(f)

    print("[4/4] Downloading batch results...")
    results = {}
    for result in client.beta.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            title = id_to_title.get(result.custom_id)
            if title:
                results[title] = result.result.message.content[0].text.strip()

    print(f"      {len(results):,} spoken texts downloaded")

    ensure_schema(db_path)

    conn = sqlite3.connect(db_path)
    c    = conn.cursor()

    inserted_loc = 0
    inserted_txt = 0
    skipped      = 0

    for title, spoken in results.items():
        if title not in articles:
            skipped += 1
            continue
        info = articles[title]

        # Insert into locations if not already there
        c.execute(
            "INSERT OR IGNORE INTO locations (title, lat, lon, raw_summary, type) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, info["lat"], info["lon"],
             texts.get(title, ""), info.get("type"))
        )
        if c.rowcount > 0:
            inserted_loc += 1

        # Get the location_id
        row = c.execute("SELECT id FROM locations WHERE title = ?", (title,)).fetchone()
        if not row:
            skipped += 1
            continue
        location_id = row[0]

        # Insert spoken text for this language
        c.execute(
            "INSERT OR IGNORE INTO location_texts (location_id, language, spoken_text) "
            "VALUES (?, ?, ?)",
            (location_id, language, spoken)
        )
        if c.rowcount > 0:
            inserted_txt += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()

    size_mb = Path(db_path).stat().st_size / 1_048_576
    print(f"      {inserted_loc:,} new locations inserted")
    print(f"      {inserted_txt:,} new '{language}' texts inserted  ({skipped} skipped)")
    print(f"      Database: {db_path} ({size_mb:.1f} MB)")
    return inserted_txt


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Rewrite Wikipedia texts with Claude Haiku into road trip spoken sentences"
    )
    parser.add_argument("--country",  default="NL",
                        help="Country code matching step1 files (default: NL)")
    parser.add_argument("--language", default="en",
                        choices=list(PROMPTS.keys()),
                        help="Output language (default: en)")
    parser.add_argument("--output",   default=None,
                        help="Output SQLite path (default: {country}.db)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    country       = args.country.upper()
    language      = args.language
    articles_file = f"{country.lower()}_articles.json"
    texts_file    = f"{country.lower()}_texts.json"
    batch_id_file = f"{country.lower()}_{language}_batch_id.txt"
    db_path       = args.output or f"{country.lower()}.db"

    for f in [articles_file, texts_file]:
        if not Path(f).exists():
            print(f"Error: {f} not found — run step1_fetch.py first.")
            sys.exit(1)

    with open(articles_file) as f:
        articles = json.load(f)
    with open(texts_file) as f:
        texts = json.load(f)

    translated = load_translated_titles(db_path, language)
    new_count  = sum(1 for t in texts if t in articles and t not in translated)

    print(f"\n=== Step 3-4: Rewrite + Build Database ===")
    print(f"Country    : {country}")
    print(f"Language   : {language}")
    print(f"Articles   : {len(articles):,}")
    print(f"Texts      : {len(texts):,}")
    print(f"In DB ({language:<2}) : {len(translated):,}")
    print(f"New to add : {new_count:,}")
    print(f"Output     : {db_path}\n")

    if new_count == 0:
        print("Nothing new to process — already up to date.")
        return

    if Path(batch_id_file).exists():
        with open(batch_id_file) as f:
            batch_id = f.read().strip()
        print(f"[3/4] Resuming existing batch: {batch_id}")
    else:
        batch_id = submit_batch(articles, texts, batch_id_file, db_path, language)
        if batch_id is None:
            return

    wait_for_batch(batch_id)
    inserted = build_database(batch_id, articles, texts, db_path, batch_id_file, language)

    Path(batch_id_file).unlink(missing_ok=True)

    print(f"\n=== Done ===")
    print(f"  {db_path}  (+{inserted:,} '{language}' texts)")
    print(f"\nTo add Dutch:")
    print(f"  python step2_rewrite.py --country {country} --language nl")
    print(f"\nStrip raw text for app:")
    print(f"  python strip_db.py --input {db_path}")


if __name__ == "__main__":
    main()
