import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cache_storage import inventory, clear_previewed
from core import original_name
from desktop import Bridge, book_view


class CacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        with patch('desktop.HERE', self.root):
            self.bridge = Bridge()
        self.bridge._state['folder'] = str(self.root / 'output')
        self.book = dict(product_id=1, product_name='Test', file_type='ZIPJPEG', file_size=0)
        self.bridge._client = SimpleNamespace(books={'1': self.book})
        self.bridge._books = [book_view(self.book)]
        self.cache = self.bridge._cache_folder()
        self.cache.mkdir(parents=True)
        self.source = self.cache / original_name(self.book)
        self.source.write_bytes(b'12345')
        self.meta = Path(str(self.source) + '.json')
        self.meta.write_text(json.dumps(dict(product_id=1, downloaded_bytes=5)))
        def start(operation, job):
            job()
            return {'ok': True}
        self.bridge._start = start

    def test_server_size_hidden_until_completed_source_exists(self):
        self.assertEqual(book_view(dict(self.book, file_size=12345))['size'], 0)
        self.bridge._refresh_downloads()
        self.assertEqual(self.bridge.snapshot()['books'][0]['size'], 5)
        self.meta.unlink()
        self.bridge._refresh_downloads()
        self.assertEqual(self.bridge.snapshot()['books'][0]['size'], 0)
        self.assertEqual(self.bridge.snapshot()['downloaded'], [])

    def test_confirmation_required_and_preview_does_not_delete(self):
        self.assertIn('error', self.bridge.clear_cache('invalid'))
        preview = self.bridge.cache_preview()
        self.assertEqual(preview['count'], 2)
        self.assertTrue(self.source.exists())
        self.assertIn('error', self.bridge.clear_cache('invalid'))
        self.assertTrue(self.source.exists())

    def test_clear_preserves_outputs_and_external_files_updates_state(self):
        output = self.root / 'output'
        output.mkdir()
        converted = output / 'book.zip'
        converted.write_bytes(b'converted')
        external = self.root / 'local.melon'
        external.write_bytes(b'original')
        # Even a ZIP put inside cache is outside the deletion allowlist.
        extra = self.cache / 'book.pdf'
        extra.write_bytes(b'pdf')
        self.bridge._refresh_downloads()
        preview = self.bridge.cache_preview()
        self.bridge.clear_cache(preview['token'])
        self.assertFalse(self.source.exists())
        self.assertFalse(self.meta.exists())
        self.assertTrue(converted.exists() and external.exists() and extra.exists())
        self.assertEqual(self.bridge.snapshot()['downloaded'], [])
        self.assertEqual(self.bridge.snapshot()['books'][0]['size'], 0)
        self.assertIn('error', self.bridge.clear_cache(preview['token']))

    def test_busy_guard(self):
        preview = self.bridge.cache_preview()
        self.bridge._state['busy'] = True
        self.assertIn('error', self.bridge.clear_cache(preview['token']))
        self.assertIn('error', self.bridge.cache_preview())
        self.assertTrue(self.source.exists())

    def test_changed_or_new_files_are_not_deleted(self):
        preview = inventory(self.root)
        self.source.write_bytes(b'changed source')
        new = self.cache / 'new.pdf.ebg'
        new.write_bytes(b'new')
        removed, skipped, _ = clear_previewed(self.root, preview, self.root / 'output')
        self.assertEqual((removed, skipped), (1, 1))
        self.assertTrue(self.source.exists() and new.exists())

    def test_output_inside_cache_refused(self):
        with self.assertRaises(ValueError):
            clear_previewed(self.root, inventory(self.root), self.cache)
        self.assertTrue(self.source.exists())

    def test_all_cache_partitions_cleared_legacy_download_preserved(self):
        other = self.root / 'source-cache' / 'other' / 'sample.pdf.ebg'
        other.parent.mkdir()
        other.write_bytes(b'other')
        legacy = self.root / 'output' / original_name(self.book)
        legacy.parent.mkdir()
        legacy.write_bytes(b'12345')
        Path(str(legacy) + '.json').write_bytes(self.meta.read_bytes())
        preview = self.bridge.cache_preview()
        self.bridge.clear_cache(preview['token'])
        self.assertFalse(other.exists())
        self.assertTrue(legacy.exists())
        self.assertEqual(self.bridge.snapshot()['downloaded'], ['1'])

    def test_traversal_refused(self):
        with self.assertRaises(ValueError):
            clear_previewed(self.root, [(Path('../external.ebg'), (1, 1, 1))], self.root / 'output')

    def test_linked_directories_are_skipped(self):
        external = self.root / 'external'
        external.mkdir()
        protected = external / 'source.ebg'
        protected.write_bytes(b'keep')
        link = self.cache / 'link'
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest('Symbolic links unavailable in this environment')
        files = inventory(self.root)
        self.assertFalse(any('link' in path.parts for path, _ in files))
        clear_previewed(self.root, files, self.root / 'output')
        self.assertTrue(protected.exists())


if __name__ == '__main__': unittest.main()
