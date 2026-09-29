# Shared highlights from Kindle and CrossPoint

This keeps Amazon, KOReader, and CrossPoint excerpts in the existing `highlights.json` archive. It collects quotes; it does not copy annotation positions back into books on another reader.

## Flow

1. A reader saves a highlight on its own storage.
2. The reader sends it to the Mac collector when the home network and Mac are available.
3. The collector commits the incoming record to local SQLite before acknowledging it.
4. A background publisher merges pending quotes into the latest GitHub `highlights.json`. Failed publication remains pending and is retried.
5. The existing daily quote workflow continues to select from that archive.

The Amazon refresh remains another producer. The collector uses optimistic GitHub file updates, and refresh fetches and merges against the latest remote state, so concurrent updates must not overwrite each other.

`highlights.json` is in a public repository. Anything published there is publicly readable. The separate collector token, device identities, and local file paths must stay on the Mac/readers, outside the repository.

## Install on the Mac

Requires macOS, Python 3.11+, and an authenticated GitHub CLI with write access to the archive repository:

```sh
gh auth status
python3 scripts/install-macos.py --repo skyerus/kindle-highlights --branch main
```

The installer creates:

- `~/Library/Application Support/Reading Highlights/` — collector code, SQLite state, token and logs.
- `~/Library/LaunchAgents/com.skye.reading-highlights.plist` — starts at login and restarts after crashes.

The default port is **8084**, separate from the book library on 8083. The token is generated once in `data/token` with owner-only permissions and is preserved during reinstall. Configure that token and the Mac's LAN address in each reader. Use a stable DHCP reservation or a working `.local` hostname.

The LaunchAgent starts after login. FileVault must first be unlocked after reboot. Closing the lid, sleeping, shutting down or leaving the home network can make the Mac unavailable. Readers retain their saved highlights and retry; no public port forwarding is required.

The GitHub CLI credentials remain on the Mac. Neither reader needs a GitHub or Amazon password.

## Status and recovery

```sh
curl http://localhost:8084/healthz
python3 "$HOME/Library/Application Support/Reading Highlights/collector.py" status
launchctl print gui/$(id -u)/com.skye.reading-highlights
```

Check the service logs under the application directory if GitHub publishing is failing. A successful device upload means the collector saved the highlight locally; GitHub publication may follow later. Do not delete the collector's data directory to fix a network error.

Back up the entire `Reading Highlights/data` directory while the service is stopped (or use SQLite's backup API). The GitHub archive and each reader's saved annotations provide separate copies, but pending records and publication state live in the collector database.

## Reader setup

See [`koreader/sharedhighlights.koplugin/README.md`](../koreader/sharedhighlights.koplugin/README.md) for installation, settings, offline retries and manual synchronization on KOReader.

CrossPoint requires the custom X4 Pro firmware with clipping capture and **Sync Highlights** support; stock releases without this feature cannot create excerpts. Keep a known-good firmware image and preserve the SD card contents before installation. The collector uses the same protocol for both readers.

## Collector protocol

`POST /v1/highlights` requires `Authorization: Bearer <collector-token>` and a JSON body:

```json
{
  "source": "koreader",
  "device_id": "reader-unique-id",
  "highlights": [
    {
      "id": "stable-highlight-id",
      "book_title": "Book title",
      "author": "Author",
      "text": "The selected excerpt.",
      "note": "Optional note",
      "created_at": "2026-09-29T12:00:00Z",
      "location": "Optional source-specific location"
    }
  ]
}
```

The response's `accepted` list identifies durably saved records. A client must retain unacknowledged records and may safely retry. Clients should send small batches; the server limits requests to 1 MiB and 128 records. CrossPoint sends one clipping per request to bound memory use.

The archive is additive. Removing a highlight from a reader does not remove a previously collected quote from GitHub.
