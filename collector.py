"""Durable LAN highlight inbox and GitHub archive publisher (Python stdlib only)."""
import argparse
from contextlib import contextmanager
import base64
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from db import merge

MAX_BODY = 1024 * 1024
LOG = logging.getLogger("collector")


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("body must be an object")
    source = payload.get("source")
    if source not in ("koreader", "crosspoint"):
        raise ValueError("unsupported source")
    def string(value, name, maximum, required=True):
        if not isinstance(value, str) or len(value.encode("utf-8")) > maximum or (required and not value.strip()):
            raise ValueError("invalid " + name)
        return value
    device = string(payload.get("device_id"), "device_id", 256)
    records = payload.get("highlights")
    if not isinstance(records, list) or not 1 <= len(records) <= 128:
        raise ValueError("highlights must contain 1 to 128 records")
    clean = []
    seen = set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("highlight must be an object")
        record = {key: string(item.get(key, ""), key, size, key != "author")
                  for key, size in (("id", 256), ("book_title", 4096), ("author", 4096), ("text", 65536))}
        for key, size in (("note", 65536), ("created_at", 128), ("location", 4096)):
            if key in item:
                record[key] = string(item[key], key, size, False)
        if record["id"] in seen:
            raise ValueError("duplicate id within batch")
        seen.add(record["id"])
        clean.append(record)
    return source, device, clean


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE IF NOT EXISTS inbox (source TEXT, device TEXT, id TEXT, payload TEXT NOT NULL, revision TEXT NOT NULL, published TEXT, PRIMARY KEY(source,device,id))")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        try:
            con.execute("PRAGMA synchronous=FULL")
            with con:
                yield con
        finally:
            con.close()

    def accept(self, payload):
        source, device, records = validate(payload)
        with self.connect() as con:
            for record in records:
                data = json.dumps(record, ensure_ascii=False, sort_keys=True)
                revision = hashlib.sha256(data.encode()).hexdigest()
                con.execute("INSERT INTO inbox(source,device,id,payload,revision) VALUES(?,?,?,?,?) ON CONFLICT(source,device,id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision", (source, device, record["id"], data, revision))
        return [record["id"] for record in records]

    def pending(self):
        with self.connect() as con:
            return con.execute("SELECT source,device,id,payload,revision FROM inbox WHERE published IS NULL OR published != revision ORDER BY source,device,id").fetchall()

    def acknowledge(self, rows):
        with self.connect() as con:
            con.executemany("UPDATE inbox SET published=? WHERE source=? AND device=? AND id=? AND revision=?", [(r[4], r[0], r[1], r[2], r[4]) for r in rows])


def archive_rows(rows):
    quotes = []
    for source, device, ident, payload, revision in rows:
        item = json.loads(payload)
        quotes.append({"highlight": item["text"], "book_title": item["book_title"], "author": item["author"], "cover_url": ""})
    return quotes


class GitHub:
    def __init__(self, repo, branch=None, executable="gh"):
        self.repo, self.branch, self.executable = repo, branch, executable

    def api(self, endpoint, method="GET", data=None):
        command = [self.executable, "api", endpoint, "--method", method]
        if data is not None:
            command += ["--input", "-"]
        result = subprocess.run(command, input=json.dumps(data) if data is not None else None, capture_output=True, text=True, timeout=45)
        if result.returncode:
            # Do not print gh response bodies, credentials, or highlight text into logs.
            raise RuntimeError("GitHub API request failed (exit %d)" % result.returncode)
        return json.loads(result.stdout)

    def read(self):
        from urllib.parse import quote
        if self.branch is None:
            self.branch = self.api("repos/" + self.repo)["default_branch"]
        result = self.api("repos/%s/contents/highlights.json?ref=%s" % (self.repo, quote(self.branch, safe="")))
        if result.get("encoding") == "none":
            result_blob = self.api("repos/%s/git/blobs/%s" % (self.repo, result["sha"]))
            content = result_blob["content"]
        else:
            content = result["content"]
        quotes = json.loads(base64.b64decode(content))
        if not isinstance(quotes, list) or any(not isinstance(q, dict) or not all(isinstance(q.get(k), str) for k in ("highlight", "book_title", "author")) for q in quotes):
            raise ValueError("remote archive has unexpected schema")
        return quotes, result["sha"]

    def write(self, quotes, sha):
        content = (json.dumps(quotes, ensure_ascii=False, indent=2) + "\n").encode()
        self.api("repos/%s/contents/highlights.json" % self.repo, "PUT", {"message": "Sync reader highlights", "content": base64.b64encode(content).decode(), "sha": sha, "branch": self.branch})


def publish_once(store, github, attempts=3):
    rows = store.pending()
    if not rows:
        return 0
    additions = archive_rows(rows)
    for attempt in range(attempts):
        try:
            current, sha = github.read()
            updated = merge(current, additions)
            if current != updated:
                github.write(updated, sha)
            store.acknowledge(rows)
            return len(rows)
        except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired):
            if attempt + 1 == attempts:
                raise
            # Reread the latest SHA and union on every retry, including conflicts.
    return 0


def server(store, token, host, port):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, format, *args):
            pass

        def reply(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.reply(200 if self.path == "/healthz" else 404, {"status": "ok"} if self.path == "/healthz" else {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/highlights":
                return self.reply(404, {"error": "not found"})
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode()):
                return self.reply(401, {"error": "unauthorized"})
            try:
                if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                    raise ValueError("Content-Length required")
                length = int(self.headers["Content-Length"])
                if not 0 < length <= MAX_BODY:
                    return self.reply(413, {"error": "body exceeds limit"})
                if self.headers.get_content_type() != "application/json":
                    return self.reply(415, {"error": "application/json required"})
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("incomplete request")
                accepted = store.accept(json.loads(body))
            except (ValueError, UnicodeError):
                return self.reply(400, {"error": "invalid highlight batch"})
            except sqlite3.Error:
                LOG.exception("Local storage failure")
                return self.reply(503, {"error": "storage unavailable; retry"})
            self.reply(200, {"accepted": accepted, "status": "stored"})
    return ThreadingHTTPServer((host, port), Handler)


def initialize(directory):
    directory = Path(directory).expanduser()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    token_path = directory / "token"
    try:
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as output:
            output.write(secrets.token_urlsafe(32) + "\n")
    os.chmod(token_path, 0o600)
    token = token_path.read_text().strip()
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("token file must contain a random ASCII token of at least 32 characters")
    return directory, token


def publication_status(directory, state, error=None):
    """Best-effort diagnostic state; failure must never stop durable inbox retries."""
    from datetime import datetime, timezone
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".publication-status-", delete=False) as output:
            temporary = Path(output.name)
            json.dump({"status": state, "attempted_at": datetime.now(timezone.utc).isoformat(), "error_type": error}, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(Path(directory) / "publication-status.json")
    except OSError as exc:
        LOG.warning("Could not update publication status (%s)", type(exc).__name__)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def publisher_loop(store, github, directory, stop, interval):
    while not stop.is_set():
        try:
            count = publish_once(store, github)
        except Exception as exc:
            publication_status(directory, "pending", type(exc).__name__)
            LOG.warning("Publication pending; will retry (%s)", type(exc).__name__)
        else:
            publication_status(directory, "synced")
            if count:
                LOG.info("Published %d annotations", count)
        stop.wait(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "serve", "publish", "status"))
    parser.add_argument("--state-dir", default="~/Library/Application Support/Reading Highlights/data")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8084)
    parser.add_argument("--repo", default="skyerus/kindle-highlights")
    parser.add_argument("--branch")
    parser.add_argument("--gh", default="gh", help="absolute gh executable path for launchd")
    parser.add_argument("--publish-interval", type=int, default=60)
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.publish_interval < 10:
        parser.error("publish interval must be at least 10 seconds")
    directory, token = initialize(args.state_dir)
    store = Store(directory / "inbox.sqlite3")
    if args.command == "init":
        print("Initialized collector; pairing token is in " + str(directory / "token"))
        return
    status_path = directory / "publication-status.json"
    if args.command == "status":
        status = json.loads(status_path.read_text()) if status_path.exists() else {"status": "not_attempted"}
        status["pending"] = len(store.pending())
        print(json.dumps(status))
        return
    github = GitHub(args.repo, args.branch, args.gh)
    if args.command == "publish":
        try:
            count = publish_once(store, github)
        except Exception as exc:
            publication_status(directory, "pending", type(exc).__name__)
            raise
        publication_status(directory, "synced")
        print("Published %d pending annotations" % count)
        return
    stop = threading.Event()
    httpd = server(store, token, args.host, args.port)
    if not args.no_publish:
        threading.Thread(target=publisher_loop, args=(store, github, directory, stop, args.publish_interval), daemon=True).start()
    LOG.info("Collector listening on %s:%d", args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
