"""Independent BeBG RIFF reader. Does not execute/import the viewer or its DLLs."""
import base64
import hmac
import json
import os
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from decode_support import Cancelled, safe_title, valid_payload

LIMIT = 1024 * 1024
KTST = bytes.fromhex('ab8599ec5446ce13e62579226f58556a')


def cbc(key, blob):
    if len(key) != 16 or len(blob) < 32 or len(blob) % 16:
        raise ValueError('AES 数据长度无效。')
    dec = Cipher(algorithms.AES(key), modes.CBC(blob[:16])).decryptor()
    padded = dec.update(blob[16:]) + dec.finalize()
    unpad = PKCS7(128).unpadder()
    return unpad.update(padded) + unpad.finalize()


def client_private_key(profile='android'):
    # These are fixed application constants, not account or book keys.
    name = {'android': 'android_client_material.json', 'windows': 'client_material.json'}[profile]
    material = json.loads(Path(__file__).with_name(name).read_text(encoding='utf-8'))
    pem = cbc(base64.b64decode(material['wrapping_key'], validate=True),
              base64.b64decode(material['private_key_envelope'], validate=True))
    return serialization.load_pem_private_key(pem, password=None)


def license_secret(license_data, private_key=None):
    """Accept the LCNS JSON shape or the API's hex drm_key field."""
    try:
        if isinstance(license_data, (bytes, str)):
            if len(license_data) > LIMIT:
                raise ValueError()
            text = license_data.decode('utf-8') if isinstance(license_data, bytes) else license_data
            obj = json.loads(text) if text.lstrip().startswith('{') else {'data': {'key': text}}
        else:
            obj = license_data
        encoded = obj['data']['key']
        key = private_key if private_key is not None else client_private_key()
        if not isinstance(encoded, str) or not re.fullmatch(r'[0-9a-fA-F]+', encoded):
            raise ValueError()
        if len(encoded) != key.key_size // 4:
            raise ValueError()
        plain = key.decrypt(bytes.fromhex(encoded), rsa_padding.PKCS1v15())
        if len(plain) < 16:
            raise ValueError()
        return plain[:16]
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError('作品授权数据无效或与当前解码版本不兼容，请重新登录同步书架。') from None


class EbgFile:
    def __init__(self, stream):
        self.stream = stream
        self.chunks = {}
        stream.seek(0, os.SEEK_END)
        total = stream.tell()
        stream.seek(0)
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'BeBG':
            raise ValueError('不是受支持的 RIFF/BeBG 文件。')
        if struct.unpack('<I', header[4:8])[0] + 8 != total:
            raise ValueError('RIFF 声明长度与文件大小不符。')
        position = 12
        while position < total:
            if total - position < 8:
                raise ValueError('文件块头不完整。')
            stream.seek(position)
            tag, size = struct.unpack('<4sI', stream.read(8))
            end = position + 8 + size + size % 2
            if end > total:
                raise ValueError('文件块越界或已截断。')
            if tag in (b'META', b'KEY ', b'KTST', b'data', b'LCNS'):
                if tag in self.chunks:
                    raise ValueError('文件包含重复的关键块。')
                self.chunks[tag] = (position + 8, size)
            position = end
        if not all(tag in self.chunks for tag in (b'META', b'KEY ', b'KTST', b'data')):
            raise ValueError('文件缺少 META、KEY、KTST 或 data 块。')
        try:
            root = ET.fromstring(self.read(b'META'))
            self.kind = (root.findtext('file_type') or '').strip().lower()
            self.title = (root.findtext('title') or '').strip()
            self.content_id = (root.findtext('content_id') or '').strip()
        except ET.ParseError:
            raise ValueError('META XML 无效。') from None
        if self.kind not in ('zip', 'pdf'):
            raise ValueError('独立模式暂只支持 ZIP/PDF 作品。')
        if self.chunks[b'KTST'][1] != 48:
            raise ValueError('KTST 校验块长度无效。')
        size = self.chunks[b'data'][1]
        if size < 32 or size % 16:
            raise ValueError('正文加密块长度无效。')

    def read(self, tag):
        offset, size = self.chunks[tag]
        if size > LIMIT:
            raise ValueError('元数据或授权块过大。')
        self.stream.seek(offset)
        value = self.stream.read(size)
        if len(value) != size:
            raise ValueError('文件在读取期间被截断。')
        return value

    def content_key(self, license_data, private_key=None):
        try:
            root = ET.fromstring(self.read(b'KEY '))
            if root.tag != 'keyinfo' or root.findtext('version') != '1':
                raise ValueError('不支持的 KEY 版本。')
            encoded = (root.findtext('key') or '').strip()
            if not re.fullmatch(r'[0-9a-fA-F]{96}', encoded):
                raise ValueError('KEY 块格式无效。')
            blob = bytes.fromhex(encoded)
        except ET.ParseError:
            raise ValueError('KEY XML 无效。') from None
        test = self.read(b'KTST')
        candidates = [private_key] if private_key is not None else [client_private_key('android'), client_private_key('windows')]
        for private in candidates:
            try:
                secret = license_secret(license_data, private)
            except ValueError:
                continue
            # Native 0x4bdf00 decrypts only the first ciphertext block.
            dec = Cipher(algorithms.AES(secret), modes.CBC(blob[:16])).decryptor()
            key = dec.update(blob[16:32]) + dec.finalize()
            # KTST only checks the first block; EOF padding does not apply.
            dec = Cipher(algorithms.AES(key), modes.CBC(test[:16])).decryptor()
            if hmac.compare_digest(dec.update(test[16:32]) + dec.finalize(), KTST):
                return key
        raise ValueError('作品密钥校验失败：授权与文件或客户端版本不匹配，或文件已损坏。')

    def decrypt_to(self, target, key, cancel):
        offset, size = self.chunks[b'data']
        self.stream.seek(offset)
        iv = self.stream.read(16)
        if len(iv) != 16:
            raise ValueError('正文 IV 不完整。')
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        unpad = PKCS7(128).unpadder()
        remaining = size - 16
        while remaining:
            if cancel.is_set():
                raise Cancelled()
            block = self.stream.read(min(remaining, LIMIT))
            if not block or len(block) % 16:
                raise ValueError('正文读取不完整。')
            remaining -= len(block)
            target.write(unpad.update(dec.update(block)))
        try:
            target.write(unpad.update(dec.finalize()) + unpad.finalize())
        except ValueError:
            raise ValueError('正文填充校验失败，文件可能已损坏。') from None


def convert_independent(source, output_dir, cancel, log, *, license_data=None,
                        title_override=None, license_provider=None, private_key=None):
    """Provider resolves (content_id, source) to (license, title)."""
    source, output_dir = Path(source), Path(output_dir)
    if cancel.is_set():
        raise Cancelled()
    with source.open('rb') as stream:
        book = EbgFile(stream)
        title = (title_override or '').strip() or book.title
        if license_data is None and b'LCNS' in book.chunks:
            license_data = book.read(b'LCNS')
        if license_provider and (license_data is None or not title):
            supplied, server_title = license_provider(book.content_id, source=source)
            license_data = supplied if license_data is None else license_data
            title = title or server_title
        if license_data is None:
            raise ValueError('文件没有内嵌授权，请先登录并同步已购书架。')
        if not title:
            raise ValueError('文件及书架均没有作品标题，请在列表中填写输出标题。')
        if cancel.is_set():
            raise Cancelled()
        key = book.content_key(license_data, private_key)
        log('作品密钥校验通过，正在独立解密正文。')
        output_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.melon-', suffix='.part', dir=output_dir)
        pending = Path(name)
        try:
            with os.fdopen(fd, 'wb') as target:
                book.decrypt_to(target, key, cancel)
            if cancel.is_set():
                raise Cancelled()
            log('解密完成，正在校验输出文件。')
            if not valid_payload(pending, book.kind):
                raise ValueError('解密结果未通过 ZIP/PDF 完整性检查，未导出。')
            stem = safe_title(title, source)
            for index in range(10000):
                if cancel.is_set():
                    raise Cancelled()
                suffix = '' if index == 0 else f' ({index})'
                output = output_dir / f'{stem}{suffix}.{book.kind}'
                try:
                    # Same-directory hard link publishes the validated file
                    # atomically and fails if a concurrent writer claimed it.
                    os.link(pending, output)
                except FileExistsError:
                    continue
                return output
            raise ValueError('同名文件过多，请更换输出目录。')
        finally:
            pending.unlink(missing_ok=True)
