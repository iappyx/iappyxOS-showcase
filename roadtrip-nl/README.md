# Road Trip NL

A driving companion that announces nearby locations using text-to-speech as you drive through the Netherlands. Start a trip, and the app automatically detects and speaks about villages, cities, churches, castles, windmills, canals, and other points of interest as you pass them.

## Features

- Pre-built SQLite database with thousands of Dutch locations and descriptions
- Text-to-speech in English and Dutch
- GPS tracking with speed gate (only announces while driving)
- Configurable detection radius (200m – 2km)
- Heard-list: locations are only announced once per day
- Toggle location types on/off (villages, churches, castles, etc.)
- Works fully offline after install (database is bundled in the APK)

## Resources

This app includes a bundled database file (`nl_app.db`, ~58 MB) that is extracted to writable storage on first launch. The database contains location coordinates, names, types, and spoken descriptions in English and Dutch.

**Bridges used:** location, tts, sqlite, storage, screen, vibration
