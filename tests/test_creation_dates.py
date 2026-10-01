import copy
import json
import tempfile
import unittest
from pathlib import Path

from collector import Store, publish_once
from db import merge, quote_key


class DateTests(unittest.TestCase):
    def test_merge_enriches_then_retains_earliest_and_respects_deletion(self):
        old = {'book_title': 'Book', 'author': 'Author', 'highlight': 'A quote', 'cover_url': 'cover'}
        dated = dict(old, created_at='2024-04-07T11:29:55')
        self.assertEqual(merge([old], [dated]), [dated])
        for incoming in (old, dict(old, created_at='bad'), dict(old, created_at='2026-10-01T12:00:00Z')):
            self.assertEqual(merge([dated], [incoming]), [dated])
        earlier = dict(old, created_at='2023-01-01T00:00:00Z')
        self.assertEqual(merge([dated], [earlier]), [earlier])
        self.assertEqual(merge([old], [dated], {quote_key(old)}), [])
        self.assertNotIn('created_at', old)

    def test_device_dates_survive_upload_replay_and_github_publish(self):
        class Archive:
            def __init__(self):
                self.quotes, self.deleted = [], set()
            def read(self):
                return copy.deepcopy(self.quotes), set(self.deleted), None
            def write(self, quotes, deleted, snapshot):
                self.quotes, self.deleted = quotes, deleted
        for source, date in (('koreader', '2026-09-29 10:00:00'), ('crosspoint', '2026-09-29T09:00:00Z')):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temp:
                store = Store(Path(temp) / 'inbox.sqlite3')
                row = {'id': 'one', 'book_title': 'Book', 'author': 'Author', 'text': 'A quote', 'created_at': date}
                payload = {'source': source, 'device_id': 'reader', 'highlights': [row]}
                archive = Archive()
                store.accept(payload)
                publish_once(store, archive)
                self.assertEqual(archive.quotes[0]['created_at'], date)
                row.pop('created_at')
                store.accept(payload)
                self.assertEqual(store.pending(), [])
                with store.connect() as con:
                    self.assertEqual(json.loads(con.execute('SELECT payload FROM inbox').fetchone()[0])['created_at'], date)
                row.update(deleted=True)
                store.accept(payload)
                publish_once(store, archive)
                self.assertEqual(archive.quotes, [])
                row.pop('deleted')
                row['created_at'] = date
                store.accept(payload)
                publish_once(store, archive)
                self.assertEqual(archive.quotes, [])

    def test_backfill_enriches_existing_remote_archive(self):
        from tests.test_collector import MemoryGitHub, batch, quote
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'inbox.sqlite3')
            archive = MemoryGitHub([quote()])
            payload = batch()
            payload['highlights'][0]['created_at'] = '2024-04-07T11:29:55'
            store.accept(payload)
            publish_once(store, archive)
            self.assertEqual(len(archive.current), 1)
            self.assertEqual(archive.current[0]['created_at'], '2024-04-07T11:29:55')


if __name__ == '__main__':
    unittest.main()
