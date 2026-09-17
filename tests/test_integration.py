"""Download/convert orchestration tests; no network or user account required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from desktop import Bridge, ConversionCancelled


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch('desktop.HERE', self.root):
            self.bridge = Bridge()
        self.bridge._state['folder'] = str(self.root)
        self.books = {str(i): dict(product_id=i, product_name=f'Book {i}',
                                  file_type='ZIPJPEG', drm_key='private') for i in (1, 2)}
        self.bridge._client = Mock(books=self.books)
        self.bridge._client.download.side_effect = [self.root / 'one.ebg', self.root / 'two.ebg']
        self.bridge._start = lambda operation, job: job()

    def test_each_download_is_converted_with_server_title_and_license(self):
        with patch('desktop.convert_independent', return_value=self.root / 'out.zip') as convert:
            self.bridge.download(['1', '2'])
        self.assertEqual(convert.call_count, 2)
        first = convert.call_args_list[0]
        self.assertEqual(first.args[:2], (self.root / 'one.ebg', self.root))
        self.assertEqual(first.kwargs['license_data'], 'private')
        self.assertEqual(first.kwargs['title_override'], 'Book 1')
        self.assertEqual(self.bridge.snapshot()['downloaded'], ['1', '2'])
        self.assertNotIn('private', str(self.bridge.snapshot()))

    def test_conversion_failure_keeps_download_and_continues_queue(self):
        with patch('desktop.convert_independent', side_effect=[ValueError('Unsupported'), self.root / 'out.zip']):
            self.bridge.download(['1', '2'])
        state = self.bridge.snapshot()
        self.assertTrue(state['error'])
        self.assertEqual(state['downloaded'], ['1', '2'])
        self.assertIn('1 本转换失败', state['message'])

    def test_conversion_cancel_stops_next_download(self):
        with patch('desktop.convert_independent', side_effect=ConversionCancelled):
            with self.assertRaises(ConversionCancelled): self.bridge.download(['1', '2'])
        self.assertEqual(self.bridge._client.download.call_count, 1)
        self.assertEqual(self.bridge.snapshot()['downloaded'], ['1'])

    def test_local_conversion_requires_login_and_busy_guard(self):
        self.bridge._client = None
        self.bridge._window = Mock()
        for method in (self.bridge.convert_local, self.bridge.choose_local_files,
                       self.bridge.start_local_conversion, self.bridge.check_local_files):
            self.assertIn('error', method())
        self.bridge._window.create_file_dialog.assert_not_called()
        self.bridge._client = Mock(books={})
        self.bridge._state['busy'] = True
        self.assertIn('error', self.bridge.convert_local())


if __name__ == '__main__': unittest.main()
