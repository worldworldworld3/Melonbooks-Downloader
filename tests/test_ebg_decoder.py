import io
import hashlib
import json
import os
import struct
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from decode_support import Cancelled
from ebg_decoder import EbgFile, KTST, cbc, client_private_key, convert_independent, license_secret
from official_license import PurchasedLicenses


def encrypt(key, data):
    iv = os.urandom(16)
    pad = PKCS7(128).padder()
    data = pad.update(data) + pad.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return iv + enc.update(data) + enc.finalize()


def chunk(tag, data):
    return tag + struct.pack('<I', len(data)) + data + b'\0' * (len(data) % 2)


class DecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'book.zipjpeg.ebg'
        self.output = self.root / 'output'
        self.cancel = threading.Event()
        self.secret, self.key = os.urandom(16), os.urandom(16)
        self.license = self.private.public_key().encrypt(self.secret, padding.PKCS1v15()).hex()
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('图像.bin', os.urandom(1200000))
        self.payload = raw.getvalue()
        self.parts = {}
        self.build()

    def build(self, kind='zip', embedded=False, title='作品标题'):
        self.parts = {
            b'META': f'<meta><file_type>{kind}</file_type><title>{title}</title><content_id>123</content_id></meta>'.encode(),
            b'KEY ': ('<keyinfo><version>1</version><key>' + encrypt(self.secret, self.key).hex() + '</key></keyinfo>').encode(),
            b'KTST': encrypt(self.key, KTST), b'data': encrypt(self.key, self.payload),
        }
        if embedded:
            self.parts[b'LCNS'] = json.dumps({'data': {'key': self.license}}).encode()
        self.write()

    def write(self, extra=b''):
        body = b'BeBG' + b''.join(chunk(k, v) for k, v in self.parts.items()) + extra
        self.source.write_bytes(b'RIFF' + struct.pack('<I', len(body)) + body)

    def convert(self, **kwargs):
        options = dict(license_data=self.license, private_key=self.private)
        options.update(kwargs)
        return convert_independent(self.source, self.output, self.cancel, lambda _: None, **options)

    def test_full_zip_round_trip_no_viewer_and_collision(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not launch viewer')):
            first, second = self.convert(), self.convert()
        self.assertEqual(first.name, '作品标题.zip')
        self.assertEqual(second.name, '作品标题 (1).zip')
        self.assertEqual(first.read_bytes(), self.payload)
        self.assertEqual(second.read_bytes(), self.payload)
        self.assertFalse(list(self.output.glob('*.part')))

    def test_pdf_with_embedded_license(self):
        self.payload = b'%PDF-1.4\nfixture\n%%EOF\n'
        self.build(kind='pdf', embedded=True)
        self.source = self.source.rename(self.root / 'book.pdf.ebg.melon')
        result = self.convert(license_data=None)
        self.assertEqual(result.suffix, '.pdf')
        self.assertEqual(result.read_bytes(), self.payload)

    def test_provider_supplies_title_and_license(self):
        self.build(title='')
        provider = Mock(return_value=(self.license, '书架作品标题'))
        result = self.convert(license_data=None, license_provider=provider)
        self.assertEqual(result.name, '书架作品标题.zip')
        provider.assert_called_once_with('123', source=self.source)

    def test_wrong_book_license_never_exports(self):
        wrong = self.private.public_key().encrypt(os.urandom(16), padding.PKCS1v15()).hex()
        with self.assertRaisesRegex(ValueError, '密钥校验失败'):
            self.convert(license_data=wrong)
        self.assertFalse(self.output.exists())

    def test_bad_license_is_redacted(self):
        for bad in ('secret-password', {'data': {'key': 'secret-password'}}, '0' * 512):
            with self.assertRaises(ValueError) as result:
                self.convert(license_data=bad)
            self.assertNotIn('secret-password', str(result.exception))

    def test_missing_license_and_missing_title(self):
        with self.assertRaisesRegex(ValueError, '登录'):
            self.convert(license_data=None)
        self.build(title='')
        with self.assertRaisesRegex(ValueError, '标题'):
            self.convert()

    def test_truncated_duplicate_and_wrong_form(self):
        original = self.source.read_bytes()
        for raw in (original[:-1], original[:8] + b'WAVE' + original[12:]):
            self.source.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.convert()
        self.write(chunk(b'META', self.parts[b'META']))
        with self.assertRaisesRegex(ValueError, '重复'):
            self.convert()

    def test_payload_corruption_no_partial_output(self):
        data = bytearray(self.parts[b'data'])
        data[128] ^= 1
        self.parts[b'data'] = bytes(data)
        self.write()
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            self.convert()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_bad_padding(self):
        data = bytearray(self.parts[b'data'])
        data[-17] ^= 0xff  # Corrupt the final padding byte deterministically.
        self.parts[b'data'] = bytes(data)
        self.write()
        with self.assertRaisesRegex(ValueError, '填充'):
            self.convert()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_cancellation_mid_stream_removes_partial(self):
        real = EbgFile.decrypt_to
        def cancelling(book, target, key, cancel):
            target.write(b'partial')
            cancel.set()
            real(book, target, key, cancel)
        with patch.object(EbgFile, 'decrypt_to', cancelling), self.assertRaises(Cancelled):
            self.convert()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_packaged_key_loads_without_executable(self):
        key = client_private_key()
        value = key.public_key().encrypt(self.secret, padding.PKCS1v15()).hex()
        self.assertEqual(license_secret(value), self.secret)

    def test_packaged_android_profile_and_json_license(self):
        self.license = json.dumps({'data': {'version': '1', 'key':
            client_private_key('android').public_key().encrypt(self.secret, padding.PKCS1v15()).hex()},
            'signature': 'test fixture'})
        self.assertEqual(self.convert(private_key=None).read_bytes(), self.payload)

    def test_windows_profile_fallback(self):
        self.license = client_private_key('windows').public_key().encrypt(self.secret, padding.PKCS1v15()).hex()
        self.assertEqual(self.convert(private_key=None).read_bytes(), self.payload)

    def test_ktst_matches_native_first_block_only(self):
        self.parts[b'KTST'] = self.parts[b'KTST'][:32] + os.urandom(16)
        self.write()
        self.assertEqual(self.convert().read_bytes(), self.payload)

    def test_renamed_file_matches_only_valid_purchased_license(self):
        wrong = self.private.public_key().encrypt(os.urandom(16), padding.PKCS1v15()).hex()
        client = Mock(books={'456': {'drm_key': wrong, 'title': '另一作品'},
                             '789': {'drm_key': self.license, 'title': '匹配作品'}})
        provider = PurchasedLicenses(client, lambda b: b['title'])
        self.build(title='')
        with patch('ebg_decoder.client_private_key', return_value=self.private):
            result = self.convert(license_data=None, license_provider=provider)
        self.assertEqual(result.name, '匹配作品.zip')
        self.assertEqual(result.read_bytes(), self.payload)

    def test_ambiguous_authorization_does_not_guess_title(self):
        client = Mock(books={'456': {'drm_key': self.license, 'title': 'A'},
                             '789': {'drm_key': self.license, 'title': 'B'}})
        provider = PurchasedLicenses(client, lambda b: b['title'])
        with patch('ebg_decoder.client_private_key', return_value=self.private):
            with self.assertRaisesRegex(ValueError, '多个已购条目'):
                provider('123', source=self.source)

    def test_nist_aes_cbc_vector_with_pkcs7_tail(self):
        # NIST SP800-38A F.2.1 first CBC block, followed by a padding block.
        key = bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
        iv = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
        encrypted = bytes.fromhex('7649abac8119b246cee98e9b12e9197d')
        enc = Cipher(algorithms.AES(key), modes.CBC(encrypted)).encryptor()
        tail = enc.update(bytes([16]) * 16) + enc.finalize()
        self.assertEqual(cbc(key, iv + encrypted + tail), bytes.fromhex('6bc1bee22e409f96e93d7e117393172a'))


class LicenseTests(unittest.TestCase):
    def test_only_books_in_purchased_shelf(self):
        client = Mock(books={'123': {'drm_key': 'abc', 'title': '作品'}})
        provider = PurchasedLicenses(client, lambda b: b['title'])
        self.assertEqual(provider('123'), ('abc', '作品'))
        with self.assertRaisesRegex(ValueError, '未能在已购书架'):
            provider('124')
        client.books['123']['drm_key'] = None
        with self.assertRaisesRegex(ValueError, '授权数据'):
            provider('123')

    def test_drm_content_id_differs_from_store_product_id(self):
        client = Mock(books={'456': {'drm_key': 'abc', 'title': '书架作品'}})
        provider = PurchasedLicenses(client, lambda b: b['title'])
        name = hashlib.md5(b'456').hexdigest() + '.zipjpeg.ebg.melon'
        self.assertEqual(provider('232000052800', source=Path(name)), ('abc', '书架作品'))


if __name__ == '__main__':
    unittest.main()
