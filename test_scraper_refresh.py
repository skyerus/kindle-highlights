"""Amazon refresh must preserve existing and concurrently published device quotes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import db
import refresh


class RefreshTests(unittest.TestCase):
    def test_scrape_batch_does_not_change_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'highlights.json'
            archive.write_text('[{"highlight":"existing","book_title":"Book","author":"A"}]')
            incoming = Path(tmp) / 'incoming.json'
            with patch.object(db, 'DB_PATH', archive), patch.object(refresh, 'get_highlights', return_value=[
                {'highlight': 'new', 'book_title': 'Book', 'author': 'A'}
            ]):
                before = archive.read_bytes()
                self.assertEqual(refresh.main(['--scrape-output', str(incoming)]), 0)
                self.assertEqual(archive.read_bytes(), before)
                self.assertEqual(refresh.main(['--merge-input', str(incoming)]), 0)
                self.assertEqual({q['highlight'] for q in json.loads(archive.read_text())}, {'existing', 'new'})

    def test_bad_batch_does_not_change_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'highlights.json'
            archive.write_text('[]')
            incoming = Path(tmp) / 'incoming.json'
            for batch in [[], {}, [{'highlight': ''}], [{'highlight': 42}]]:
                incoming.write_text(json.dumps(batch))
                with patch.object(db, 'DB_PATH', archive):
                    self.assertEqual(refresh.main(['--merge-input', str(incoming)]), 1)
                self.assertEqual(archive.read_text(), '[]')

    def test_workflow_remerges_after_concurrent_push(self):
        self._workflow_race('refresh.yml', 'Merge and publish highlights against latest archive')

    def test_daily_png_publish_preserves_concurrent_quotes(self):
        self._workflow_race('daily.yml', 'Commit quote.png')

    def test_amazon_reimport_cannot_restore_deleted_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'highlights.json'
            deleted = {'highlight': 'deleted', 'book_title': 'Book', 'author': 'A'}
            kept = dict(deleted, book_title='Other book')
            archive.write_text(json.dumps([deleted, kept]))
            incoming = Path(tmp) / 'incoming.json'
            incoming.write_text(json.dumps([deleted, kept]))
            with patch.object(db, 'DB_PATH', archive), patch.object(refresh, 'load_tombstones', return_value={db.quote_key(deleted)}):
                self.assertEqual(refresh.main(['--merge-input', str(incoming)]), 0)
            self.assertEqual(json.loads(archive.read_text()), [kept])

    def test_refresh_retry_respects_concurrent_deletion(self):
        self._workflow_race('refresh.yml', 'Merge and publish highlights against latest archive', deletion=True)

    def test_daily_retry_preserves_concurrent_deletion(self):
        self._workflow_race('daily.yml', 'Commit quote.png', deletion=True)

    def test_daily_retry_skips_deleted_selected_quote(self):
        self._workflow_race('daily.yml', 'Commit quote.png', deletion=True, deleted_selected=True)

    def _workflow_race(self, filename, step, deletion=False, deleted_selected=False):
        # Run the actual publication shell from the workflow against a local bare
        # remote. A pre-push hook deterministically injects a competing writer.
        workflow = Path(__file__).parent / '.github/workflows' / filename
        content = workflow.read_text()
        section = content.split(f'      - name: {step}\n', 1)[1]
        body = section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        script = '\n'.join(line[10:] for line in body.splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote, runner, rival = (root / name for name in ['remote.git', 'runner', 'rival'])
            def git(*args, cwd=None):
                return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True)
            git('init', '--bare', '--initial-branch=main', str(remote))
            git('clone', str(remote), str(runner))
            git('config', 'user.email', 'test@example.test', cwd=runner)
            git('config', 'user.name', 'Test', cwd=runner)
            for name in ['refresh.py', 'scraper.py', 'db.py', 'main.py']:
                shutil.copy(Path(__file__).parent / name, runner / name)
            quote = lambda text: {'highlight': text, 'book_title': 'Book', 'author': 'A'}
            (runner / 'highlights.json').write_text(json.dumps([quote('old')] + ([quote('deleted')] if deletion else [])))
            (runner / 'quote.png').write_text('previous PNG fixture')
            git('add', '.', cwd=runner)
            git('commit', '-m', 'seed', cwd=runner)
            git('push', 'origin', 'main', cwd=runner)
            git('clone', str(remote), str(rival))
            git('config', 'user.email', 'test@example.test', cwd=rival)
            git('config', 'user.name', 'Test', cwd=rival)
            (rival / 'highlights.json').write_text(json.dumps([quote('old'), quote('device')]))
            if deletion:
                (rival / 'highlight-tombstones.json').write_text(json.dumps([db.quote_key(quote('deleted'))]))
                git('add', 'highlight-tombstones.json', cwd=rival)
            git('add', 'highlights.json', cwd=rival)
            git('commit', '-m', 'concurrent device quote', cwd=rival)
            hook = runner / '.git/hooks/pre-push'
            hook.write_text(f'#!/bin/sh\nif [ ! -f "{root}/pushed" ]; then\n  touch "{root}/pushed"\n  git -C "{rival}" push origin main\nfi\n')
            hook.chmod(0o755)
            (root / 'amazon-highlights.json').write_text(json.dumps([quote('amazon')] + ([quote('deleted')] if deletion else [])))
            (root / 'daily-quote-key').write_text(db.quote_key(quote('deleted' if deleted_selected else 'old')))
            (runner / 'quote.png').write_text('new PNG fixture')
            env = dict(os.environ, TARGET_BRANCH='main', RUNNER_TEMP=str(root))
            result = subprocess.run(['bash', '-e', '-c', script], cwd=runner, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            archive = git('--git-dir', str(remote), 'show', 'main:highlights.json').stdout
            expected = {'old', 'device', 'amazon'} if filename == 'refresh.yml' else {'old', 'device'}
            self.assertEqual({q['highlight'] for q in json.loads(archive)}, expected)
            if filename == 'daily.yml':
                self.assertEqual(git('--git-dir', str(remote), 'show', 'main:quote.png').stdout, 'previous PNG fixture' if deleted_selected else 'new PNG fixture')
                self.assertIn('python main.py --check-quote-key', script)
                self.assertNotIn('--quote-key-output', script)
            if deletion:
                tombstones = git('--git-dir', str(remote), 'show', 'main:highlight-tombstones.json').stdout
                self.assertEqual(json.loads(tombstones), [db.quote_key(quote('deleted'))])
            if deleted_selected:
                self.assertIn('Selected quote was deleted', result.stdout)
            self.assertIn('retrying against latest archive', result.stdout)


if __name__ == '__main__':
    unittest.main()
