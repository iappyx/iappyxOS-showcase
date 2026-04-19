# Road Trip Audio Guide

A pipeline that turns Wikipedia's geographic data into a spoken audio guide for road trips. As you drive, your phone automatically speaks interesting facts about the places you pass — churches, windmills, villages, castles, canals — in English or Dutch.

Runs entirely offline on Android via [iappyxOS](https://github.com/iappyx/iappyxOS).

---

## How it works

1. Wikipedia publishes free database dumps containing every geotagged article
2. The pipeline downloads these dumps, extracts article text, and classifies each location by type (village, church, windmill, etc.) using Wikidata
3. Claude Haiku rewrites each Wikipedia article into 2 natural spoken sentences optimised for listening while driving
4. Everything is packed into a SQLite database and bundled into an Android app
5. The app watches your GPS position, queries nearby unheard locations, and speaks them via TTS

---

## Pipeline scripts

### `step1_fetch.py` — Build article database
Downloads Wikimedia database dumps and extracts all geotagged articles with their full text.

```bash
python step1_fetch.py --country NL
```

Downloads three files (~2 GB total, one-time):
- `nlwiki-latest-geo_tags.sql.gz` — geographic coordinates per article
- `nlwiki-latest-page.sql.gz` — page metadata
- `nlwiki-latest-pages-articles.xml.bz2` — full article text

Output: `nl_articles.json` (~56,000 locations) and `nl_texts.json` (~68 MB of article text).

Incremental — safe to re-run, merges new articles without reprocessing existing ones.

Supported countries: `NL` `BE` `DE` `FR` `GB` `ES` `IT`

---

### `step1b_classify.py` — Add location types
Downloads the Wikidata QID mapping and classifies each location by type (village, church, windmill, museum, etc.) using the Wikidata API.

```bash
python step1b_classify.py --country NL
```

Downloads `nlwiki-latest-page_props.sql.gz` (51 MB), then makes ~1,120 batch API calls to Wikidata (about 2 minutes). Results are cached in `nl_qid_types.json` so it never re-queries.

Updates both `nl_articles.json` (adds `type` field) and `nl.db` (adds `type` column to existing rows).

Type distribution for Netherlands (~56,000 locations):
```
other            38,153    (streets, farms, minor features)
church            4,355
building          2,365
village           2,064
neighbourhood     1,991
bridge            1,730
railway station   1,600
museum              731
municipality        654
park                482
...
```

---

### `step2_rewrite.py` — Rewrite with Claude
Submits all articles to Claude Haiku via the Batch API, which rewrites each Wikipedia article into 2 natural spoken sentences for road trip listening. Supports multiple languages.

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# English
python step2_rewrite.py --country NL --language en

# Dutch
python step2_rewrite.py --country NL --language nl
```

- Uses Claude Haiku via the [Batch API](https://docs.anthropic.com/en/docs/build-with-claude/message-batches) (50% cost reduction vs real-time)
- Estimated cost: ~$15–20 per country per language
- Takes 1–2 hours (batch processing)
- Fully incremental — skips articles already processed, never reprocesses

The Dutch prompt instructs Claude to write natural spoken Dutch. The English prompt instructs Claude to write for a road trip passenger.

Spoken texts are stored in the `location_texts` table keyed by `(location_id, language)`.

---

### `strip_db.py` — Prepare for shipping
Creates a lean copy of the database for bundling into the app. NULLs the `raw_summary` column (Wikipedia source text, not needed in the app) and VACUUMs. Reduces file size by ~50%.

```bash
python strip_db.py --input nl.db
```

Output: `nl_app.db`

---

### `explore.py` — Browser-based explorer
A local web UI to explore the database. Search, filter by type, find nearby locations, preview spoken text in both languages.

```bash
pip install flask
python explore.py --db nl.db
# Opens http://localhost:5500
```

Features:
- Type filter sidebar with counts
- Full-text search
- Nearby finder (enter coordinates + radius)
- Language switcher (EN / NL)
- Detail panel with spoken text and Wikipedia source

---

### `query.py` — CLI test
Quick command-line test to find locations near a GPS coordinate.

```bash
python query.py --db nl.db --lat 52.96 --lon 5.80
python query.py --db nl.db --lat 52.96 --lon 5.80 --radius 10 --language nl
```

---

## Database schema

```sql
CREATE TABLE locations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL UNIQUE,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    raw_summary TEXT,    -- NULLed in nl_app.db
    type        TEXT     -- 'village', 'church', 'windmill', etc.
);

CREATE TABLE location_texts (
    location_id  INTEGER NOT NULL REFERENCES locations(id),
    language     TEXT    NOT NULL,   -- 'en', 'nl', 'de', ...
    spoken_text  TEXT    NOT NULL,
    PRIMARY KEY (location_id, language)
);

CREATE TABLE heard (
    location_id  INTEGER PRIMARY KEY,
    heard_at     INTEGER              -- Unix timestamp ms, created by the app
);
```

Adding a new language is just one more `step2_rewrite.py` run — no schema changes needed.

---

## Full pipeline

```bash
pip install requests mwparserfromhell flask anthropic

# 1. Build article database from Wikipedia dumps (~2-3 hours, one-time download)
python step1_fetch.py --country NL

# 2. Classify location types via Wikidata (~2 minutes)
python step1b_classify.py --country NL

# 3. Rewrite with Claude Haiku — English (~1-2 hours, ~$15-20)
export ANTHROPIC_API_KEY=sk-ant-...
python step2_rewrite.py --country NL --language en

# 4. Rewrite with Claude Haiku — Dutch (optional, same cost)
python step2_rewrite.py --country NL --language nl

# 5. Strip for app
python strip_db.py --input nl.db

# 6. Explore
python explore.py --db nl.db

# 7. Test
python query.py --db nl.db --lat 52.96 --lon 5.80
```

---

## The Android app — `roadtrip.html`

Built for [iappyxOS](https://github.com/iappyx/iappyxOS). A single HTML file bundled with `nl_app.db` into an APK.

### Features
- **Drive screen** — status indicator (idle / listening / speaking), speed, nearby count, heard today count, last spoken text
- **Nearby screen** — live list of unheard locations within radius, sorted by distance, tap to speak immediately
- **Settings screen** — language (EN/NL), detection radius, gap between speaks, speed gate, per-type toggles, clear heard list

### Behaviour
- Foreground GPS tracking (survives screen off, shows persistent notification)
- Bounding box query + exact Haversine distance filter
- Speed gate — optionally only speaks when moving above X km/h (avoids triggering while parked)
- Heard tracking — each location expires after 24 hours so it can trigger again on a future trip
- Min gap between speaks (configurable) — prevents being overwhelmed in a city

### Type filtering
By default, `other` and `skip` types are disabled (streets, minor administrative entries). All meaningful types — villages, churches, windmills, museums, castles, bridges, lakes etc. — are enabled. A single "Enable all" button turns everything on.

### Deploying
1. Run `strip_db.py` to generate `nl_app.db`
2. In iappyxOS builder, upload `nl_app.db` via the App Files section
3. Upload `roadtrip.html` as the app file
4. Build APK

---

## Sample outputs

**Joure** (village):
> *"Joure is the birthplace of Douwe Egberts — in 1753 a man named Egbert Douwes opened a small shop here that grew into one of the world's biggest coffee brands. The town has also been making ornate Frisian clocks by hand since the 1700s."*

**Drachten** (city):
> *"Drachten became famous worldwide when traffic engineer Hans Monderman removed all its traffic lights and signs in 2003, turning a busy intersection into a shared space where eye contact replaces rules. The experiment worked — accidents dropped and traffic flowed more smoothly."*

**Terherne** (village):
> *"Terherne was an island until 1908, when a causeway finally connected it to the mainland. The village is also the setting for De Kameleon, a beloved Dutch children's book series that has been captivating young readers since the 1950s."*

**Noorderplantsoen, Groningen** (park):
> *"Noorderplantsoen was laid out in the 1880s on top of the city's old defensive fortifications, turning a military boundary into one of the most loved urban parks in the north of the Netherlands. Every August it hosts Noorderzon, a performing arts festival that draws over 125,000 visitors in just ten days."*

---

## Notes

- Wikipedia coverage varies by country. The Netherlands has excellent coverage (~56,000 geotagged articles). Germany and France are larger but also well-covered.
- The `other` type (38,000 locations in NL) includes many interesting places that Wikidata simply hasn't classified yet. If coverage feels thin, enable it in settings.
- Locations need a Wikipedia article to appear. Very local landmarks (a specific crash site, a local legend's house) won't be in the database.
- The pipeline is fully resumable — if a batch API job or download is interrupted, re-running picks up where it left off.
