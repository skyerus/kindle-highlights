import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import collector
from db import merge


def batch(text="First highlight", ident="one", device="kindle"):
    return {"source": "koreader", "device_id": device, "highlights": [{"id": ident, "book_title": "A Book", "author": "An Author", "text": text}]}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = collector.Store(self.path / "inbox.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_durable_retry_and_edit(self):
        self.assertEqual(self.store.accept(batch()), ["one"])
        self.store.accept(batch())
        reopened = collector.Store(self.path / "inbox.sqlite3")
        rows = reopened.pending()
        self.assertEqual(len(rows), 1)
        reopened.accept(batch("Edited highlight"))
        reopened.acknowledge(rows)  # concurrent edit cannot be acknowledged by an older publish
        self.assertEqual(json.loads(reopened.pending()[0][3])["text"], "Edited highlight")
        reopened.acknowledge(reopened.pending())
        reopened.accept(batch("Edited highlight"))
        self.assertEqual(reopened.pending(), [])

    def test_invalid_batch_is_atomic(self):
        data = batch()
        data["highlights"].append({"id": "bad"})
        with self.assertRaises(ValueError):
            self.store.accept(data)
        self.assertEqual(self.store.pending(), [])
        for field, value in (("text", " " ), ("text", "a" * 65537), ("location", 123), ("id", None)):
            data = batch()
            data["highlights"][0][field] = value
            with self.assertRaises(ValueError):
                self.store.accept(data)

    def test_merge_compatibility_and_book_identity(self):
        old = [{"highlight": "First highlight", "book_title": "A Book", "author": "An Author", "cover_url": "cover"}]
        incoming = collector.archive_rows(self._accept(batch(" First  highlight\n", device="xteink")))
        self.assertEqual(merge(old, incoming), old)
        incoming[0]["book_title"] = "Other Book"
        self.assertEqual(len(merge(old, incoming)), 2)
        incoming[0]["book_title"] = "A Book"
        incoming[0]["highlight"] = "A second highlight"
        self.assertEqual(merge(old, incoming)[1]["cover_url"], "cover")
        self.assertEqual(set(incoming[0]), {"highlight", "book_title", "author", "cover_url"})
        self.assertNotIn("annotations", old[0])

    def _accept(self, payload):
        self.store.accept(payload)
        return self.store.pending()

    def test_conflict_rereads_preserves_latest_and_retries_without_duplication(self):
        self.store.accept(batch())
        class FakeGitHub:
            def __init__(self):
                self.current = [{"highlight": "Amazon quote", "book_title": "Amazon", "author": "Author", "cover_url": ""}]
                self.reads = 0
                self.write_shas = []
            def read(self):
                self.reads += 1
                return copy.deepcopy(self.current), str(self.reads)
            def write(self, quotes, sha):
                self.write_shas.append(sha)
                if self.reads == 1:
                    self.current.append({"highlight": "Concurrent quote", "book_title": "Amazon", "author": "Author", "cover_url": ""})
                    raise RuntimeError("conflict")
                self.current = quotes
        github = FakeGitHub()
        self.assertEqual(collector.publish_once(self.store, github), 1)
        self.assertEqual(len(github.current), 3)
        self.assertEqual(github.reads, 2)
        self.assertEqual(github.write_shas, ["1", "2"])
        self.assertEqual(self.store.pending(), [])
        self.store.accept(batch())
        self.assertEqual(collector.publish_once(self.store, github), 0)

    def test_remote_commit_with_lost_response_retries_without_duplicate(self):
        self.store.accept(batch())
        class LostResponseGitHub:
            def __init__(self):
                self.current = []
                self.reads = 0
                self.writes = 0
            def read(self):
                self.reads += 1
                return copy.deepcopy(self.current), str(self.writes)
            def write(self, quotes, sha):
                self.current = copy.deepcopy(quotes)
                self.writes += 1
                raise OSError("response lost after remote commit")
        github = LostResponseGitHub()
        self.assertEqual(collector.publish_once(self.store, github), 1)
        self.assertEqual(github.reads, 2)
        self.assertEqual(github.writes, 1)
        self.assertEqual([q["highlight"] for q in github.current], ["First highlight"])
        self.assertEqual(self.store.pending(), [])

    def test_edit_after_publication_preserves_previous_quote_and_adds_new(self):
        class MemoryGitHub:
            def __init__(self):
                self.current = []
                self.writes = 0
            def read(self):
                return copy.deepcopy(self.current), str(self.writes)
            def write(self, quotes, sha):
                self.current = copy.deepcopy(quotes)
                self.writes += 1
        github = MemoryGitHub()
        self.store.accept(batch())
        self.assertEqual(collector.publish_once(self.store, github), 1)
        original = copy.deepcopy(github.current[0])
        self.store.accept(batch("Edited highlight"))
        self.assertEqual(collector.publish_once(self.store, github), 1)
        self.assertEqual(github.current[0], original)
        self.assertEqual([q["highlight"] for q in github.current], ["First highlight", "Edited highlight"])
        self.assertEqual(self.store.pending(), [])
        self.store.accept(batch("Edited highlight"))
        self.assertEqual(collector.publish_once(self.store, github), 0)
        self.assertEqual(github.writes, 2)

    def test_failed_publication_retains_pending(self):
        self.store.accept(batch())
        class Offline:
            def read(self):
                raise RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            collector.publish_once(self.store, Offline())
        self.assertEqual(len(self.store.pending()), 1)

    def test_http_auth_and_acknowledgement(self):
        httpd = collector.server(self.store, "t" * 32, "127.0.0.1", 0)
        thread = threading.Thread(target=httpd.serve_forever)
        thread.start()
        try:
            def post(data, token):
                conn = http.client.HTTPConnection(*httpd.server_address, timeout=5)
                conn.request("POST", "/v1/highlights", json.dumps(data), {"Content-Type": "application/json", "Authorization": "Bearer " + token})
                response = conn.getresponse()
                result = response.status, json.loads(response.read())
                conn.close()
                return result
            self.assertEqual(post(batch(), "wrong")[0], 401)
            self.assertEqual(self.store.pending(), [])
            self.assertEqual(post(batch(), "t" * 32), (200, {"accepted": ["one"], "status": "stored"}))
            self.assertEqual(len(self.store.pending()), 1)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()

    def test_concurrent_status_writes_are_atomic(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: collector.publication_status(self.path, str(n)), range(40)))
        status_path = self.path / "publication-status.json"
        self.assertIn(int(json.loads(status_path.read_text())["status"]), range(40))
        self.assertEqual(status_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.path.glob(".publication-status-*")), [])

    def test_status_write_failure_does_not_stop_publisher_retry(self):
        class StopAfterTwo:
            iterations = 0
            def is_set(self):
                return self.iterations == 2
            def wait(self, interval):
                self.iterations += 1
        with patch.object(collector, "publish_once", side_effect=[RuntimeError("offline"), 1]) as publish:
            with patch.object(collector.tempfile, "NamedTemporaryFile", side_effect=PermissionError("readonly")):
                with self.assertLogs("collector", level="WARNING"):
                    collector.publisher_loop(self.store, object(), self.path, StopAfterTwo(), 60)
        self.assertEqual(publish.call_count, 2)

    def test_token_permissions_and_stability(self):
        directory, token = collector.initialize(self.path / "private")
        self.assertEqual((directory / "token").stat().st_mode & 0o777, 0o600)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(collector.initialize(directory)[1], token)


if __name__ == "__main__":
    unittest.main()
