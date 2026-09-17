import hashlib
import io
import threading
import unittest
from unittest.mock import patch
from core import Client, DownloadError, Cancelled

class Reply(io.BytesIO):
    def __init__(self, body, status=206, **headers):
        super().__init__(body)
        self.status=status
        self.headers=headers

class SegmentTests(unittest.TestCase):
    def transfer(self, opener, cancel=None, progress=lambda *_:None):
        c=Client({},opener);out=io.BytesIO();sha=hashlib.sha256()
        with patch('core.SEGMENT_BYTES',4):
            result=c._transfer('https://example.com/book',out,sha,10,cancel or threading.Event(),progress)
        self.assertEqual(result,(10,10))
        self.assertEqual(out.getvalue(),b'0123456789')
        self.assertEqual(sha.hexdigest(),hashlib.sha256(b'0123456789').hexdigest())

    def test_validated_sequential_ranges(self):
        calls=[]
        def opener(req):
            calls.append(req)
            first,last=map(int,req.get_header('Range')[6:].split('-'));last=min(last,9)
            if first:self.assertEqual(req.get_header('If-range'),'"version1"')
            return Reply(b'0123456789'[first:last+1],**{'Content-Range':f'bytes {first}-{last}/10','Content-Length':str(last-first+1),'ETag':'"version1"'})
        self.transfer(opener)
        self.assertEqual([c.get_header('Range') for c in calls],['bytes=0-3','bytes=4-7','bytes=8-11'])

    def test_server_ignores_range(self):
        self.transfer(lambda req:Reply(b'0123456789',status=200,**{'Content-Length':'10'}))

    def test_next_range_uses_resolved_file_url(self):
        calls=[]
        def opener(req):
            calls.append(req.full_url)
            first,last=map(int,req.get_header('Range')[6:].split('-'));last=min(last,9)
            reply=Reply(b'0123456789'[first:last+1],**{'Content-Range':f'bytes {first}-{last}/10','ETag':'"v1"'})
            reply.geturl=lambda:'https://cdn.example.com/signed-file'
            return reply
        self.transfer(opener)
        self.assertEqual(calls,['https://example.com/book','https://cdn.example.com/signed-file','https://cdn.example.com/signed-file'])

    def test_missing_or_weak_etag_falls_back_without_appending(self):
        for etag in ['', 'W/"v1"']:
            calls=[]
            def opener(req):
                calls.append(req)
                if len(calls)==1:return Reply(b'0123',**{'Content-Range':'bytes 0-3/10','ETag':etag})
                self.assertIsNone(req.get_header('Range'))
                return Reply(b'0123456789',status=200,**{'Content-Length':'10'})
            self.transfer(opener)
            self.assertEqual(len(calls),2)

    def test_rejects_wrong_range_total_version_or_full_response(self):
        for mode in ['offset','total','etag','status','truncated','overlong']:
            with self.subTest(mode=mode):
                calls=[]
                def opener(req):
                    calls.append(req)
                    if len(calls)==1:return Reply(b'0123',**{'Content-Range':'bytes 0-3/10','ETag':'"v1"'})
                    cr={'offset':'bytes 0-3/10','total':'bytes 4-7/11'}.get(mode,'bytes 4-7/10')
                    body={'truncated':b'45','overlong':b'45678'}.get(mode,b'4567')
                    return Reply(body,status=200 if mode=='status' else 206,**{'Content-Range':cr,'ETag':'"v2"' if mode=='etag' else '"v1"'})
                with self.assertRaises(DownloadError):self.transfer(opener)
                self.assertEqual(len(calls),2)

    def test_cancel_at_segment_boundary_does_not_reconnect(self):
        cancel=threading.Event();calls=[]
        def opener(req):
            calls.append(req)
            return Reply(b'0123',**{'Content-Range':'bytes 0-3/10','ETag':'"v1"'})
        with self.assertRaises(Cancelled):self.transfer(opener,cancel,lambda *_:cancel.set())
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
