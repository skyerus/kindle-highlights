# kindle-highlights

Daily quote from my Kindle highlights, sent to Discord and shown on my old jailbroken Paperwhite 2 as its screensaver.

## What it does

Once a day, a GitHub Actions workflow picks a random highlight from a local DB, sends it to Discord as text, and renders a 758×1024 greyscale PNG (with cover thumbnail and attribution, content rotated 90° for landscape viewing). The Kindle fetches that PNG twice a day via the Online Screensaver KUAL extension. A small background daemon then ensures the quote actually appears on the lock screen whenever the device locks.

The highlights themselves are refreshed weekly from Amazon (Playwright headless Chromium → `read.amazon.com/notebook`).

## Architecture

```
                    GitHub Actions (.github/workflows/)
                    ├── refresh.yml  (Sun 03:00 UTC weekly)
                    │   scraper.py → Playwright → Amazon notebook
                    │   → db.merge() → commit highlights.json
                    │
                    └── daily.yml    (07:30 UTC daily)
                        main.py → random.choice from highlights.json
                                → render PNG (renderer.py)
                                → send to Discord (sender.py)
                                → commit quote.png
                                                │
                                                ▼
                              raw.githubusercontent.com/.../quote.png
                                                │
                                                ▼
                    ┌──────────────────────────────────────────────┐
                    │  Jailbroken Kindle Paperwhite 2 (FW 5.12.2.2) │
                    │                                              │
                    │  OSS plugin (KUAL extension)                 │
                    │  ├── Every 12h: wake, enable WiFi, fetch     │
                    │  │   PNG → /mnt/us/linkss/screensavers/      │
                    │  │   bg_ss00.png, disable WiFi               │
                    │  │                                           │
                    │  quote-saver daemon                          │
                    │  └── Listens for `goingToScreenSaver`        │
                    │      via lipc-wait-event; repaints           │
                    │      bg_ss00.png on lock                     │
                    └──────────────────────────────────────────────┘
```

## Project files

- `scraper.py` — Playwright + pyotp scrape of `read.amazon.com/notebook`
- `db.py` — load / save / SHA1-dedup-merge for `highlights.json`
- `renderer.py` — Pillow render. Canvas drawn as landscape (1024×758), then transposed 90° to native portrait dimensions (758×1024) since the PW2 lock screen does not rotate.
- `sender.py` — Discord webhook POST
- `main.py` — daily entry point (DB → pick → render → Discord)
- `refresh.py` — weekly entry point (scrape → merge → save)
- `highlights.json` — committed DB
- `quote.png` — committed daily render (consumed by Kindle)
- `.github/workflows/{daily,refresh}.yml`
- `kindle/` — scripts that live on the device (see below)

## Kindle setup (one-time)

The device was a stock PW2 on firmware 5.12.2.2 (serial prefix `905A`). Full stack installed:

1. **WinterBreak v1.7.0** (KindleModding/WinterBreak) — jailbreak via Mesquito exploit through the Kindle Store
2. **Universal Hotfix v2.3.7** (KindleModding/Hotfix) — persistence + sh_integration + KPM (KPM client-side hook didn't bind on this FW; sh_integration works)
3. **MRPI** + **KUAL** (Coplate HDRepack) — package installer and launcher
4. **linkss 0.25** (bfabiszewski/kindle-screensavers) — installed, but **inactive on FW 5.12.x** because the framework's `fsp` mount on `/usr/share/blanket/screensaver` pre-empts linkss's bind-mount and linkss 0.25 explicitly skips when it sees fsp
5. **OnlineScreensaver** (Kuhno92/onlinescreensaverPW2) — KUAL extension that polls the GH URL every 12h
6. **Custom `quote-saver` daemon** (`kindle/quote-saver.sh`) — works around linkss being inactive by listening for `goingToScreenSaver` lipc events and repainting via `eips -f -g`

## Kindle scripts (`kindle/`)

Both go in `/mnt/us/documents/` on the device. They appear as books in the library thanks to sh_integration.

- `quote-saver.sh` — tap once per boot to start the daemon. Idempotent (won't double-start).
- `quote-saver-stop.sh` — kills the daemon.

## Operational notes

- **Tap `quote-saver` after every Kindle reboot.** The daemon doesn't auto-start — auto-start would require an `/etc/upstart/` job, out of scope for now.
- Keep the Kindle in **airplane mode** by default. OSS toggles WiFi on briefly during its scheduled fetch and disables it again.
- The Kindle's storage is intentionally near-full (`fill_disk/`) to block Amazon OTA updates (OTA needs 200+ MB; we leave it at ~20-130 MB).
- If the lock screen ever reverts to Amazon's default, the daemon probably died — tap `quote-saver` again, then lock to test.
- The Discord webhook continues to fire daily regardless of the Kindle's state.

## Required GitHub secrets

- `AMAZON_EMAIL`, `AMAZON_PASSWORD`, `AMAZON_OTP_SECRET` (for refresh.yml)
- `DISCORD_WEBHOOK_URL` (for daily.yml)

## Fetch URL the Kindle uses

```
https://raw.githubusercontent.com/skyerus/kindle-highlights/main/quote.png
```

(The repo is public for this reason — `raw.githubusercontent.com` returns 404 for private repos.)
