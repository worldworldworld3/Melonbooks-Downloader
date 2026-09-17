import unittest
import tempfile
import json
import threading
from pathlib import Path
from unittest.mock import patch
from desktop import Bridge, book_view, downloaded_ids
from core import original_name

class DesktopTests(unittest.TestCase):
    def test_disk_detection(self):
        book = dict(product_id=42, file_type='ZIPJPEG', file_size=4)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'renamed title'
            root.mkdir()
            final = root / original_name(book)
            Path(str(final)+'.part').write_bytes(b'data')
            self.assertEqual(downloaded_ids([book], folder), [])
            final.write_bytes(b'bad')
            self.assertEqual(downloaded_ids([book], folder), [])
            final.write_bytes(b'data')
            self.assertEqual(downloaded_ids([book], folder), ['42'])
            self.assertEqual(downloaded_ids([book], root/'other'), [])
            book['file_size'] = 0
            self.assertEqual(downloaded_ids([book], folder), [])
            Path(str(final)+'.json').write_text(json.dumps(dict(product_id=42, downloaded_bytes=4)))
            self.assertEqual(downloaded_ids([book], folder), ['42'])

    def test_backend_rejects_existing_download(self):
        from unittest.mock import Mock
        bridge = Bridge()
        book = dict(product_id=42, file_type='ZIPJPEG', file_size=4)
        bridge._client = Mock(books={'42': book})
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/original_name(book)).write_bytes(b'data')
            bridge._state['folder'] = folder
            finished = threading.Event()
            def start(operation, job):
                from core import DownloadError
                with self.assertRaises(DownloadError): job()
                finished.set()
            with patch.object(bridge, '_start', side_effect=start): bridge.download(['42'])
            self.assertTrue(finished.is_set())
            bridge._client.download.assert_not_called()
            self.assertEqual(bridge.snapshot()['downloaded'], ['42'])

    def test_saved_folder_restored_and_scanned_on_sync(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder, patch('desktop.HERE', Path(folder)):
            (Path(folder)/'settings.json').write_text(json.dumps({'folder': folder}))
            book = dict(product_id=42, file_type='PDF', file_size=4)
            (Path(folder)/original_name(book)).write_bytes(b'data')
            bridge = Bridge()
            bridge._client = Mock()
            bridge._client.sync.return_value = [book]
            bridge._sync()
            self.assertEqual(bridge.snapshot()['folder'], folder)
            self.assertEqual(bridge.snapshot()['downloaded'], ['42'])
    def test_metadata_boundary(self):
        view=book_view(dict(product_id=1,product_name='<img onerror=bad>',circle_name='社团',author_name='作者',vol_author_name='卷作者',
            thumbnail_url='https://example.com/cover.jpg',access_token='secret',drm_key='secret',download_url='secret'))
        self.assertEqual(view['author'],'卷作者')
        self.assertEqual(view['circle'],'社团')
        self.assertNotIn('secret',str(view))
        for url in ['javascript:alert(1)','file:///C:/test','http://example.com/x','https://user:pass@example.com/x']:
            self.assertEqual(book_view(dict(product_id=1,thumbnail_url=url))['thumbnail'],'')

    def test_snapshot_is_sanitized_and_revision_aware(self):
        bridge=Bridge()
        bridge._client=object()
        bridge._books=[book_view(dict(product_id=12,product_name='测试',drm_key='hidden'))]
        self.assertIn('books',bridge.snapshot(-1))
        self.assertNotIn('books',bridge.snapshot(0))
        self.assertNotIn('hidden',str(bridge.snapshot(-1)))
        self.assertNotIn('_client',bridge.snapshot(-1))

    def test_download_requires_purchased_ids(self):
        bridge=Bridge()
        self.assertIn('error',bridge.download(['1']))
        class FakeClient: books={'1':{'product_id':1}}
        bridge._client=FakeClient()
        self.assertIn('error',bridge.download(['2']))
        self.assertIn('error',bridge.download('1'))
        self.assertIn('error',bridge.download([]))

if __name__=='__main__':unittest.main()
