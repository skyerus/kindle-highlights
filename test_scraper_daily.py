"""Daily selection and publish guards never contact Discord in these tests."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import db
import main


class DailyDeletionTests(unittest.TestCase):
    def test_selection_filters_deleted_quotes_and_records_selected_key(self):
        deleted = {'highlight': 'Deleted', 'book_title': 'Book', 'author': 'A'}
        kept = dict(deleted, highlight='Kept')
        render, send = Mock(), Mock()
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'selected.key'
            with patch.object(main, 'load', return_value=[deleted, kept]), \
                 patch.object(main, 'load_tombstones', return_value={db.quote_key(deleted)}), \
                 patch.dict(sys.modules, {'renderer': SimpleNamespace(render_quote_to_png=render), 'sender': SimpleNamespace(send=send)}):
                self.assertEqual(main.main(['--quote-key-output', str(marker)]), 0)
            send.assert_called_once_with(kept)
            self.assertEqual(marker.read_text().strip(), db.quote_key(kept))

    def test_deleted_publish_marker_exits_three_without_send_or_render(self):
        key = db.quote_key({'highlight': 'Deleted', 'book_title': 'Book', 'author': 'A'})
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'selected.key'
            marker.write_text(key)
            with patch.object(main, 'load_tombstones', return_value={key}):
                self.assertEqual(main.main(['--check-quote-key', str(marker)]), 3)
            with patch.object(main, 'load_tombstones', return_value=set()):
                self.assertEqual(main.main(['--check-quote-key', str(marker)]), 0)

    def test_malformed_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'selected.key'
            marker.write_text('invalid')
            with patch.object(main, 'load_tombstones', return_value=set()):
                with self.assertRaises(ValueError):
                    main.main(['--check-quote-key', str(marker)])


if __name__ == '__main__':
    unittest.main()
