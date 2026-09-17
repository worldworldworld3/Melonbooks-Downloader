import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop import Bridge
from core import original_name
import test_ebg_decoder as fixtures


class LocalConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.DecoderTests.setUpClass()

    def setUp(self):
        self.fixture = fixtures.DecoderTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        with patch('desktop.HERE', self.root):
            self.bridge = Bridge()
        self.bridge._state.update(folder=str(self.root / 'results'), logged_in=True, account='1')
        self.book = dict(product_id=123, product_name='已购作品', file_type='ZIPJPEG',
                         drm_key=self.fixture.license, file_size=self.fixture.source.stat().st_size)
        self.bridge._client = Mock(books={'123': self.book})
        def start(operation, job):
            job()
            return {'ok': True}
        self.bridge._start = start
        self.bridge.convert_local()
        self.key_patch = patch('ebg_decoder.client_private_key', return_value=self.fixture.private)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def test_preflight_verifies_key_and_does_not_write_output(self):
        self.bridge._add_paths([self.fixture.source, self.fixture.source])
        rows = self.bridge.snapshot()['local_files']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'ready')
        self.assertEqual(rows[0]['title'], '已购作品')
        self.assertFalse((self.root / 'results').exists())
        self.assertNotIn(self.fixture.license, json.dumps(self.bridge.snapshot()))

    def test_embedded_license_cannot_bypass_current_account(self):
        self.fixture.build(embedded=True)
        self.bridge._client.books = {}
        self.bridge._add_paths([self.fixture.source])
        self.assertEqual(self.bridge.snapshot()['local_files'][0]['status'], 'blocked')
        self.assertIn('error', self.bridge.start_local_conversion())

    def test_wrong_account_key_and_unsupported_files_are_blocked(self):
        self.book['drm_key'] = '0' * len(self.fixture.license)
        text = self.root / 'readme.txt'
        text.write_text('test')
        self.bridge._add_paths([self.fixture.source, text])
        self.assertEqual([r['status'] for r in self.bridge.snapshot()['local_files']], ['blocked', 'blocked'])
        self.assertIn('扩展名', self.bridge.snapshot()['local_files'][1]['detail'])

    def test_batch_conversion_outputs_only_payload_and_preserves_original(self):
        original = self.fixture.source.read_bytes()
        self.bridge._add_paths([self.fixture.source])
        self.bridge.start_local_conversion()
        outputs = list((self.root / 'results').iterdir())
        self.assertEqual([p.name for p in outputs], ['已购作品.zip'])
        self.assertEqual(outputs[0].read_bytes(), self.fixture.payload)
        self.assertEqual(self.fixture.source.read_bytes(), original)
        self.assertEqual(self.bridge.snapshot()['local_files'][0]['status'], 'done')

    def test_changed_file_is_rechecked_and_not_converted(self):
        self.bridge._add_paths([self.fixture.source])
        self.fixture.source.write_bytes(b'bad')
        self.bridge.start_local_conversion()
        self.assertEqual(self.bridge.snapshot()['local_files'][0]['status'], 'failed')
        self.assertFalse((self.root / 'results').exists())

    def test_download_sources_and_metadata_stay_in_cache(self):
        def download(book, folder, cancel, progress):
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / original_name(book)
            shutil.copyfile(self.fixture.source, path)
            Path(str(path) + '.json').write_text('{}')
            return path
        self.bridge._client.download.side_effect = download
        self.bridge.download(['123'])
        self.assertEqual([p.suffix for p in (self.root / 'results').iterdir()], ['.zip'])
        self.assertTrue(list(self.bridge._cache_folder().glob('*.ebg')))
        self.assertEqual(self.bridge._downloaded([self.book]), ['123'])

    def test_native_drop_routes_to_queue_and_respects_login(self):
        event = {'dataTransfer': {'files': [{'pywebviewFullPath': str(self.fixture.source)}]}}
        self.bridge._drop(event)
        self.assertEqual(len(self.bridge.snapshot()['local_files']), 1)
        self.bridge.remove_local_file()
        self.bridge._client = None
        self.bridge._drop(event)
        self.assertEqual(self.bridge.snapshot()['local_files'], [])

    def test_account_change_clears_previous_eligibility(self):
        self.bridge._add_paths([self.fixture.source])
        session = {'customer_id': 'another-account'}
        with patch('desktop.login_session', return_value={'session': session}), \
             patch('desktop.Client', return_value=Mock(books={})), \
             patch.object(self.bridge, '_sync'):
            self.bridge.login()
        self.assertEqual(self.bridge.snapshot()['local_files'], [])
        self.assertFalse(self.bridge.snapshot()['local_open'])
        self.assertIn('error', self.bridge.start_local_conversion())


if __name__ == '__main__': unittest.main()
