#!/usr/bin/env python3
"""
query.py
========
Test the road trip database — find locations near a GPS coordinate.

Usage:
    python query.py --db nl.db --lat 52.96 --lon 5.80
    python query.py --db nl.db --lat 52.96 --lon 5.80 --radius 10 --language nl
"""

import sqlite3
import math
import argparse


def query_nearby(db_path, lat, lon, radius_km=2.0, limit=5, language="en"):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * abs(math.cos(math.radians(lat))))
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT l.title, l.lat, l.lon, lt.spoken_text, l.type
        FROM locations l
        JOIN location_texts lt ON lt.location_id = l.id
        WHERE lt.language = ?
          AND l.lat BETWEEN ? AND ?
          AND l.lon BETWEEN ? AND ?
        ORDER BY ((l.lat - ?) * (l.lat - ?) + (l.lon - ?) * (l.lon - ?))
        LIMIT ?
    """, (language, lat - dlat, lat + dlat, lon - dlon, lon + dlon,
          lat, lat, lon, lon, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description="Query road trip database")
    parser.add_argument("--db",       required=True)
    parser.add_argument("--lat",      type=float, required=True)
    parser.add_argument("--lon",      type=float, required=True)
    parser.add_argument("--radius",   type=float, default=2.0)
    parser.add_argument("--limit",    type=int,   default=5)
    parser.add_argument("--language", default="en", help="Language (default: en)")
    args = parser.parse_args()

    rows = query_nearby(args.db, args.lat, args.lon, args.radius, args.limit, args.language)

    if not rows:
        print(f"No results within {args.radius} km of ({args.lat}, {args.lon}) for language='{args.language}'")
        return

    print(f"\nLocations within {args.radius} km of ({args.lat}, {args.lon}) [{args.language}]:\n")
    for title, lat, lon, spoken, type_ in rows:
        dist_km = math.sqrt((lat - args.lat)**2 + (lon - args.lon)**2) * 111
        print(f"  [{type_ or 'other'}] {title}  ({dist_km:.1f} km)")
        print(f"  \"{spoken}\"")
        print()


if __name__ == "__main__":
    main()
