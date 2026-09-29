# Shared highlights for KOReader

Copy this entire `sharedhighlights.koplugin` folder into KOReader's `plugins`
folder and restart KOReader. Tested against the annotation, history, networking,
and subprocess APIs in v2026.07.2-185-gdcf6e3b42. Physical Kindle validation is
still required.

In **Tools → Shared highlights**, set **Collector URL** to the Mac's base URL
(for example `http://mac.local:8084`) and enter the collector token. Choose
**Sync highlights** for the first import. Keep the Kindle and Mac on the same
trusted network; plain HTTP sends the bearer token over that network. Only RFC1918 private IP addresses, loopback addresses, `localhost`, and single-label
`.local` hostnames are accepted. HTTPS is rejected because the bundled TLS client does not verify certificates by
default. URL paths, query strings and embedded credentials are rejected. Configuration
is stored separately in `settings/sharedhighlights-config.json` with fields `url`,
`token`, and `device_id`; the token is never put in global reader settings. The
plugin requests file mode 0600, but Kindle FAT storage cannot enforce Unix file
permissions. Keep this file and device backups private; never commit it to GitHub.

Highlights and notes are queued when annotations change or a book closes. The
plugin attempts upload after a change, reader opening, resume, or network
connection. Wi-Fi must already be connected: the plugin never enables it or
opens a network prompt. Network requests run in a subprocess, with an 8-second
socket timeout and a 20-second parent deadline. On suspend or reader closing,
the request is cancelled and its child is reaped asynchronously; queued records
remain for the next active instance. Failed uploads remain queued and
retry at the next event or manual sync. There is no background timer waking an
idle device repeatedly.

The first connected sync in each plugin instance and every manual sync reads
all books still available in KOReader reading history, plus the currently open
book. This imports existing modern-format highlights. Old sidecars containing
only legacy `highlight`/`bookmarks` data must first be opened in this KOReader
version so its own migration creates `annotations`. Missing books and books
removed from history are not imported automatically.

Queue state is written atomically and fsynced (errors are checked) to
`settings/sharedhighlights-queue.json`. Acknowledgements apply only to the exact
revision sent, so edits made during upload stay queued. A stable annotation ID
uses book title, author, creation time and selection position; renaming/moving a
book file with unchanged metadata does not create a new identity. Changing the
book metadata creates a new identity (the collector deduplicates quote content).
Deleted highlights are not removed from the shared archive. Quotes exceeding
the collector field limits are skipped and retained in the book's annotations.

Uploads contain at most 16 highlights and less than 512 KiB of highlight JSON.
Only IDs explicitly acknowledged by the collector are marked as stored. “Stored
on the collector” means saved durably on the Mac, not yet published to GitHub.
Your configured collector handles GitHub publication separately.

## Verification

Run `lua koreader/sharedhighlights.koplugin/tests/queue_test.lua` from the repository
root. These host tests verify deduplication, edits racing acknowledgements,
unknown acknowledgements, moved books, reverting an in-flight edit, and batch
limits. Run `lua koreader/sharedhighlights.koplugin/tests/process_test.lua` to test
asynchronous SIGKILL reaping, repeat cancellation, isolated instance transitions,
and the trusted LAN URL validator. They do not exercise
Kindle UI or its networking stack.

Device acceptance: configure the collector, manually import an existing book,
create a highlight while offline, restart KOReader, reconnect Wi-Fi and sync.
Verify the quote reaches the collector once, then add a note and verify that
revision is accepted. Confirm the reader remains interactive with the Mac
unreachable and the quote remains queued. Back up KOReader settings before
installing; remove the plugin folder and restart to uninstall. Keep its queue
file until all pending highlights are safely imported.
