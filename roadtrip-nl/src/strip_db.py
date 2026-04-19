#!/usr/bin/env python3
"""
strip_db.py
===========
Creates a lean copy of the road trip database with raw_summary removed.
The stripped version is what you ship with the app — typically 50-60% smaller.

Usage:
    python strip_db.py --input nl.db
    python strip_db.py --input nl.db --output nl_app.db
"""

import sqlite3
import shutil
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Strip raw_summary from road trip database to reduce file size"
    )
    parser.add_argument("--input",  default="nl.db",     help="Source database (default: nl.db)")
    parser.add_argument("--output", default=None,        help="Output database (default: nl_app.db)")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output) if args.output else Path(args.input.replace(".db", "_app.db"))

    if not src.exists():
        print(f"Error: {src} not found.")
        return

    # Copy the file first
    shutil.copy2(src, dst)

    # Open the copy and wipe raw_summary
    conn = sqlite3.connect(dst)
    c = conn.cursor()

    # Check schema — raw_summary is on locations table
    cols = [r[1] for r in c.execute("PRAGMA table_info(locations)")]
    if "raw_summary" in cols:
        count = c.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        c.execute("UPDATE locations SET raw_summary = NULL")
        conn.commit()
    else:
        count = 0
        print("  Note: raw_summary column not found — nothing to strip")

    # Reclaim the space
    conn.execute("VACUUM")
    conn.close()

    src_mb = src.stat().st_size / 1_048_576
    dst_mb = dst.stat().st_size / 1_048_576
    saving  = 100 * (1 - dst_mb / src_mb)

    print(f"Source : {src}  ({src_mb:.1f} MB, {count} rows)")
    print(f"Output : {dst}  ({dst_mb:.1f} MB)")
    print(f"Saving : {saving:.0f}% smaller")
    print(f"\nShip {dst} with the app.")
    print(f"Keep  {src} as your master copy (raw text stays available for future enrichment).")


if __name__ == "__main__":
    main()
