# Shared highlights from Kindle and CrossPoint

This keeps Amazon, KOReader, and CrossPoint excerpts in the existing `highlights.json` archive. It collects quotes; it does not copy annotation positions back into books on another reader.

## Flow

1. A reader saves a highlight on its own storage.
2. The reader sends it to the Mac collector when the home network and Mac are available.
3. The collector commits the incoming record to local SQLite before acknowledging it.
4. A background publisher merges pending quotes and deletions into the latest GitHub archive. It publishes `highlights.json` and `highlight-tombstones.json` in one commit. Failed publication remains pending and is retried.
5. The existing daily quote workflow continues to select from that archive.

The Amazon refresh remains another producer. The collector uses a commit based on the latest GitHub branch head and a non-forced branch update. Refresh fetches and merges against the latest archive and deletion markers on every retry, so concurrent updates preserve both additions and deletions.

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

For an upgrade, update and restart the Mac collector before installing a deletion-enabled reader plugin. Older collectors do not understand deletion records and must not acknowledge new-client deletion traffic. Preserve the collector data directory and the reader's pending queue during upgrades.

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

A deletion uses the same endpoint, source, device ID and stable highlight ID:

```json
{
  "source": "koreader",
  "device_id": "reader-unique-id",
  "highlights": [{
    "id": "stable-highlight-id",
    "deleted": true,
    "book_title": "Book title",
    "author": "Author",
    "text": "The selected excerpt."
  }]
}
```

Provide all three quote fields together when available, so a deletion can remove a matching Amazon-imported quote even before this reader uploaded it. An ID-only deletion is also supported.

The collector acknowledges deletions after saving them locally. It remembers the quote identities previously associated with that reader record, removes those exact quotes from the current archive, and persists deletion markers so an old upload or Amazon refresh cannot restore them. A deletion received before an upload also suppresses that later upload for the same reader record. Clients retry deletions until acknowledged, just like additions.

## Deletion behavior

Deletion identity combines book title, author and excerpt text, normalizing Unicode, case and whitespace. Deleting a collected quote suppresses the same quote from all producers. The same words in a different book or with a different author remain separate. This does not remove annotations from another reader; it removes them from the shared archive and future daily selections.

`highlight-tombstones.json` stores SHA256 quote identities, without excerpt text or reader IDs. Keep it with `highlights.json` when backing up or restoring the archive. A malformed deletion file stops publication rather than silently restoring removed quotes. Do not remove these markers to troubleshoot connectivity. There is no automatic undo: re-highlighting a suppressed quote does not restore it.

The daily workflow filters deleted quotes before choosing one. If a quote is deleted while its PNG publication is retrying, the workflow skips publishing that image and leaves the previous image in place. Already-sent Discord messages, an already-published PNG and historical Git commits are not retroactively removed.

Only deletions captured and synchronized by a supporting reader client reach the collector. Removing a line directly from the GitHub archive without its deletion marker does not prevent a future import from adding it again.
