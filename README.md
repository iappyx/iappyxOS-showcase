# iappyxOS Showcase

Apps built with [iappyxOS](https://github.com/iappyx/iappyxOS) — real Android apps generated from HTML/JS on a phone.

## Apps

| App | Description | Bridges |
|-----|-------------|---------|
| [Radio Player](radio-player/) | Internet radio with live station logos, audio visualizer, and now-playing metadata | audio, storage, httpClient, sensor, notification, vibration, alarm |
| [SSH Client](ssh-terminal/) | Terminal emulation, saved connection profiles, and SFTP file browser | ssh, storage |
| [LocalSend](localsend/) | File sharing between nearby devices, compatible with the LocalSend protocol | httpServer, httpClient, nsd, udp, storage, device, notification, vibration |
| [Network Scanner](network-scanner/) | Local network host discovery and port scanning | device, httpServer, screen, storage, tcp, vibration |
| [Unicorn Checkers](unicorn-checkers/) | Checkers game with unicorn-themed pieces, AI opponent, and undo | vibration, storage |

## How to use

1. Open [iappyxOS](https://github.com/iappyx/iappyxOS) on your Android device
2. Go to Create → Showcase
3. Browse and tap an app → "Load into editor"
4. Preview it, give it a name, and build

Or copy the `app.html` from any folder and paste it into iappyxOS manually.

## Submit your app

Have a great app built with iappyxOS? Submit it:

1. In iappyxOS → My Apps → tap menu on your app → "Submit to Showcase"
2. Add your GitHub token in Settings (needs `public_repo` scope)
3. Fill in the details and tap Submit
4. A pull request is created automatically

Or submit manually: fork this repo, add a folder with `app.html`, `showcase.json`, and `README.md`, then open a PR.

### Folder structure

```
your-app/
├── app.html          # the generated HTML
├── showcase.json     # metadata (name, description, author, bridges)
├── screenshot.png    # optional screenshot
└── README.md         # short description + bridges used
```

### showcase.json format

```json
{
  "name": "My App",
  "description": "Short description of what the app does.",
  "author": "your-github-username",
  "bridges": ["audio", "storage"],
  "added": "2026-04-12"
}
```