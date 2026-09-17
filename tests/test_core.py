import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from core import *

class Response(io.BytesIO):
    def __init__(self, data, content_type='application/octet-stream', length=None):
        super().__init__(data)
        self.status=200
        self.headers={'Content-Type':content_type,'Content-Length':str(len(data) if length is None else length)}

def envelope(value):
    return json.dumps({'melonbooks':{'status':{'code':200},'result':value}}).encode()

class Tests(unittest.TestCase):
    def setUp(self):
        self.book={'product_id':123,'product_name':'Test/Book','file_type':'ZIPJPEG','file_size':5}
        self.session={'customer_id':1,'access_token':'secret','refresh_token':'refresh','expires_in':'2099-01-01 00:00:00'}

    def test_callback_and_query(self):
        text='中文 & 日本語'
        self.assertEqual(decrypt(encrypt(text)),text)
        callback='melonbooks://login/'+encrypt(envelope(self.session).decode())
        self.assertEqual(parse_callback(callback),self.session)
        with self.assertRaises(DownloadError): parse_callback(callback.replace('login','evil'))
        query=decrypt(parse_qs(urlsplit(login_url('test-device')).query)['p'][0])
        self.assertIn('device=android;test-device;',query)
        self.assertIn('&timestamp=',query)

    def test_sync_download_and_no_overwrite(self):
        seen=[]
        def opener(req):
            seen.append(req)
            if req.full_url.endswith('sync_v2.php'):
                return Response(envelope({'orders':[self.book,{**self.book,'product_id':124,'status':'delete'},{**self.book,'product_id':125,'file_type':'MP3'}]}))
            if req.full_url.endswith('dl.php'):
                fields=parse_qs(req.data.decode())
                self.assertEqual(decrypt(fields['product_key[]'][0]),'123')
                self.assertEqual(fields['access_token'],['secret'])
                return Response(envelope([{'product_id':123,'onetime_url':'https://files.example/book'}]))
            self.assertIsNone(req.data)
            return Response(b'abcde')
        client=Client(self.session,opener)
        self.assertEqual(client.sync(),[self.book])
        with tempfile.TemporaryDirectory() as folder:
            path=client.download(self.book,folder,threading.Event())
            self.assertEqual(path.read_bytes(),b'abcde')
            self.assertEqual(path.name,'202cb962ac59075b964b07152d234b70.zipjpeg.ebg')
            metadata=path.with_suffix('.ebg.json').read_text()
            self.assertNotIn('secret',metadata)
            self.assertNotIn('onetime_url',metadata)
            with self.assertRaises(DownloadError):client.download(self.book,folder,threading.Event())
            self.assertFalse(list(Path(folder).rglob('*.part')))

    def test_failure_and_cancel_cleanup(self):
        for mode in ['short','html','cancel']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                book={**self.book,'download_url':'https://files.example/book'}
                event=threading.Event()
                response=Response(b'ab' if mode=='short' else b'abcde','text/html' if mode=='html' else 'application/octet-stream')
                c=Client(self.session,lambda req:response);c.books={'123':book}
                def progress(*args):
                    if mode=='cancel':event.set()
                with self.assertRaises(DownloadError):c.download(book,folder,event,progress)
                self.assertFalse(list(Path(folder).rglob('*.ebg')))
                self.assertFalse(list(Path(folder).rglob('*.part')))

    def test_unpurchased_and_insecure_url(self):
        c=Client(self.session)
        with self.assertRaises(DownloadError): c.download_url(self.book)
        for url in ['http://example.com','file:///etc/passwd','https://a:b@example.com']:
            with self.assertRaises(DownloadError): https_url(url)
        with self.assertRaises(DownloadError): result_of({'melonbooks':{'status':{'error':{'code':'E0000001'}}}})

    def test_refresh(self):
        def opener(req):
            self.assertTrue(req.full_url.endswith('refresh.php'))
            fields=parse_qs(req.data.decode())
            self.assertEqual(fields['refresh_token'],['refresh'])
            return Response(envelope({'access_token':'new','expires_in':'2099-01-01 00:00:00'}))
        c=Client({**self.session,'expires_in':'2000-01-01 00:00:00'},opener)
        c.refresh_if_needed();self.assertEqual(c.session['access_token'],'new')

    def test_tls_compatibility_keeps_certificate_validation(self):
        context=api_tls_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version,ssl.TLSVersion.TLSv1_2)
        self.assertFalse(any(c['kea']=='kx-dhe' for c in context.get_ciphers()))
        self.assertTrue(any(c['kea']=='kx-ecdhe' for c in context.get_ciphers()))

    def test_tls_override_only_for_api(self):
        with patch('core.build_opener') as builder:
            open_request(Request('https://api.melonbooks.co.jp/app/sync_v2.php'))
            self.assertTrue(any(isinstance(h,HTTPSHandler) for h in builder.call_args.args))
            open_request(Request('https://files.example/book'))
            self.assertFalse(any(isinstance(h,HTTPSHandler) for h in builder.call_args.args))

    def test_network_error_categories_do_not_leak_request(self):
        for error,word in [(ssl.SSLError('secret'),'协商'),(ssl.SSLCertVerificationError('secret'),'证书'),(socket.gaierror('secret'),'域名'),(TimeoutError('secret'),'超时')]:
            message=str(network_error(URLError(error)))
            self.assertIn(word,message)
            self.assertNotIn('secret',message)

if __name__=='__main__': unittest.main()
