"""Melonbooks APK 2.5.0 protocol; download purchased original packages only."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import socket
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from urllib.error import HTTPError, URLError

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

# Public client protocol constants from LJ5/a in the supplied APK.
ACCESS_KEY = bytes(x ^ 255 for x in bytes.fromhex('accb89aea994baad89b894878fb4a5be')).decode()
TRANSPORT_KEY = bytes(x ^ 255 for x in bytes.fromhex('adca889195cdcdaeb3bc9dc9b79b9792'))
API = 'https://api.melonbooks.co.jp/'
LOGIN = 'https://www.melonbooks.co.jp/app/'
UA = 'MelonbooksMultiPlayerApp-Android-2.5.0'
BOOK_TYPES = {'ZIPJPEG', 'PDF', 'EPUB', 'EPUB_REFLOW'}
SEGMENT_BYTES = 8 * 1024 * 1024

class DownloadError(Exception):
    pass

class Cancelled(DownloadError):
    pass

def encrypt(text: str, iv: bytes | None = None) -> str:
    iv = os.urandom(16) if iv is None else iv
    pad = PKCS7(128).padder()
    data = pad.update(text.encode('utf-8')) + pad.finalize()
    enc = Cipher(algorithms.AES(TRANSPORT_KEY), modes.CBC(iv)).encryptor()
    return (iv + enc.update(data) + enc.finalize()).hex()

def decrypt(text: str) -> str:
    data = bytes.fromhex(text)
    if len(data) < 32 or len(data) % 16:
        raise DownloadError('登录返回数据长度不正确。')
    dec = Cipher(algorithms.AES(TRANSPORT_KEY), modes.CBC(data[:16])).decryptor()
    padded = dec.update(data[16:]) + dec.finalize()
    unpad = PKCS7(128).unpadder()
    return (unpad.update(padded) + unpad.finalize()).decode('utf-8')

def result_of(obj):
    try:
        body = obj['melonbooks']
        status = body.get('status') or {}
        error = status.get('error') or {}
        if error.get('code'):
            code = str(error['code'])
            raise DownloadError('服务器返回错误：' + (code if re.fullmatch(r'[A-Z0-9_-]{1,40}', code) else '未知代码'))
        result = body['result']
        if result is None:
            raise ValueError()
        return result
    except (KeyError, TypeError, ValueError):
        raise DownloadError('服务器返回了无法识别的数据。') from None

def login_url(device_id: str) -> str:
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
    # Android Uri.getQuery() returns decoded query values before AES encoding.
    query = f'device=android;{device_id};13;Windows Download Client&platform=android&access_key={ACCESS_KEY}&timestamp={stamp}'
    return LOGIN + '?' + urlencode({'p': encrypt(query)})

def parse_callback(url: str) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != 'melonbooks' or parsed.netloc != 'login' or len(parsed.path.strip('/').split('/')) != 1:
        raise DownloadError('这不是有效的登录返回地址。')
    try:
        result = result_of(json.loads(decrypt(unquote(parsed.path.strip('/')))))
        if not isinstance(result, dict) or not all(result.get(k) for k in ('customer_id', 'access_token', 'refresh_token', 'expires_in')):
            raise ValueError()
        return result
    except (ValueError, UnicodeError, TypeError):
        raise DownloadError('登录返回数据无效，请重新登录。') from None

def https_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise DownloadError('服务器未返回有效的 HTTPS 下载地址。')
    return url

class SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        # Never forward API form credentials to another URL.
        if req.data is not None:
            raise DownloadError('接口发生重定向，请重新登录或检查客户端版本。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def api_tls_context():
    # The API server selects finite-field DHE with undersized DH parameters.
    # Exclude DHE instead of lowering OpenSSL security or disabling validation.
    context = ssl.create_default_context()
    context.set_ciphers('DEFAULT:!DHE:!aNULL:!eNULL:!MD5:!RC4')
    return context

def network_error(error):
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return DownloadError('HTTPS 证书校验失败。请检查系统时间和网络代理的证书配置。')
    if isinstance(reason, ssl.SSLError):
        return DownloadError('HTTPS 安全连接协商失败，请检查网络或客户端兼容性。')
    if isinstance(reason, socket.gaierror):
        return DownloadError('无法解析服务器域名，请检查 DNS 或网络连接。')
    if isinstance(reason, TimeoutError):
        return DownloadError('服务器连接或响应超时，请稍后重试。')
    return DownloadError('连接服务器失败，请检查网络或代理后重试。')

def open_request(req, timeout=45):
    try:
        handlers = [SecureRedirect()]
        if urlsplit(req.full_url).hostname == 'api.melonbooks.co.jp':
            handlers.append(HTTPSHandler(context=api_tls_context()))
        return build_opener(*handlers).open(req, timeout=timeout)
    except HTTPError as e:
        raise DownloadError(f'网络请求失败（HTTP {e.code}）。请重新登录后重试。') from None
    except (URLError, TimeoutError, OSError) as e:
        raise network_error(e) from None

def safe_name(text):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(text)).strip(' .')[:90]
    if not text or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', text):
        text = '_' + text
    return text

def title_of(book):
    return ' '.join(str(book.get(k) or '') for k in ('product_name', 'vol_name')).strip() or str(book['product_id'])

def original_name(book):
    kind = str(book.get('file_type', '')).upper()
    if kind not in BOOK_TYPES:
        raise DownloadError('该作品不是支持的漫画或电子书文件类型。')
    digest = hashlib.md5(str(int(book['product_id'])).encode()).hexdigest()
    return f'{digest}.{kind.lower()}.ebg'

class Client:
    def __init__(self, session, opener=open_request):
        self.session = dict(session)
        self.opener = opener
        self.books = {}

    def post(self, path, fields):
        data = urlencode({'access_key': ACCESS_KEY, **fields}, doseq=True).encode()
        req = Request(API + path, data=data, headers={'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded'})
        with self.opener(req) as response:
            raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise DownloadError('书架响应过大。')
        try:
            return result_of(json.loads(raw))
        except (ValueError, UnicodeError):
            raise DownloadError('接口返回的不是有效 JSON，请稍后重试。') from None

    def refresh_if_needed(self):
        try:
            expiry = datetime.strptime(self.session['expires_in'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone(timedelta(hours=9)))
            if expiry > datetime.now(timezone.utc) + timedelta(minutes=1):
                return
        except (KeyError, TypeError, ValueError):
            pass
        result = self.post('app/refresh.php', {k: self.session[k] for k in ('customer_id', 'refresh_token')})
        if not isinstance(result, dict) or not result.get('access_token') or not result.get('expires_in'):
            raise DownloadError('更新登录会话失败，请重新登录。')
        self.session.update(result)

    def sync(self):
        self.refresh_if_needed()
        result = self.post('app/sync_v2.php', {'access_token': self.session['access_token']})
        if not isinstance(result, dict) or not isinstance(result.get('orders'), list):
            raise DownloadError('无法识别已购书架，请检查客户端版本。')
        books = {}
        for book in result['orders']:
            if book.get('status') == 'delete' or str(book.get('file_type', '')).upper() not in BOOK_TYPES:
                continue
            try:
                pid = str(int(book['product_id']))
            except (KeyError, TypeError, ValueError):
                raise DownloadError('书架包含无效作品编号。') from None
            books[pid] = book
        self.books = books
        return list(books.values())

    def download_url(self, book):
        if str(book['product_id']) not in self.books:
            raise DownloadError('请先同步已购书架并从列表选择作品。')
        if book.get('download_url'):
            return https_url(book['download_url'])
        self.refresh_if_needed()
        result = self.post('app/dl.php', {'access_token': self.session['access_token'], 'product_key[]': [encrypt(str(book['product_id']))]})
        if not isinstance(result, list):
            raise DownloadError('服务器没有返回下载地址。')
        for entry in result:
            if str(entry.get('product_id')) == str(book['product_id']) and entry.get('onetime_url'):
                return https_url(entry['onetime_url'])
        raise DownloadError('未取得该已购作品的下载地址。')

    def _transfer(self, url, target, sha, expected, cancel, progress):
        size, total = 0, 0
        validator = None
        ranged = True
        while True:
            if cancel.is_set():
                raise Cancelled('已取消，未完成文件已清理。')
            requested_end = size + SEGMENT_BYTES - 1
            headers = {'User-Agent': UA, 'Accept-Encoding': 'identity'}
            if ranged:
                headers['Range'] = f'bytes={size}-{requested_end}'
                if validator:
                    headers['If-Range'] = validator
            with self.opener(Request(url, headers=headers)) as response:
                # Reuse the resolved signed file URL rather than consuming a
                # one-time redirect again for every segment.
                resolved_url = response.geturl() if hasattr(response, 'geturl') else url
                url = https_url(resolved_url)
                content_type = response.headers.get('Content-Type', '').lower()
                if any(t in content_type for t in ('text/', 'json', 'xml', 'multipart/')):
                    raise DownloadError('下载地址返回了错误页面，未保存为漫画。')
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    raise DownloadError('服务器返回了不适合字节校验的压缩数据。')
                try:
                    length = int(response.headers.get('Content-Length') or 0)
                except ValueError:
                    raise DownloadError('服务器返回的文件长度无效。') from None
                if length < 0:
                    raise DownloadError('服务器返回的文件长度无效。')
                if response.status == 206 and ranged:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not match:
                        raise DownloadError('服务器返回的分段范围无效。')
                    first, last, full = map(int, match.groups())
                    if first != size or last < first or last > requested_end or full <= last or (total and total != full):
                        raise DownloadError('服务器返回的分段范围不一致，下载已停止。')
                    segment_length = last - first + 1
                    if length and length != segment_length:
                        raise DownloadError('分段长度与服务器声明不一致。')
                    etag = response.headers.get('ETag', '')
                    if validator and etag != validator:
                        raise DownloadError('下载期间服务器文件标识发生变化，请重新下载。')
                    if not validator and last + 1 < full:
                        if not re.fullmatch(r'"[^"\r\n]*"', etag):
                            # Without a strong validator, never concatenate separate responses.
                            ranged = False
                            continue
                        validator = etag
                    total = full
                elif response.status == 200 and size == 0:
                    ranged = False
                    total = length
                    segment_length = length
                else:
                    # If-Range returning 200 means the entity may have changed.
                    raise DownloadError('服务器未返回预期分段，下载已停止以避免文件损坏。')
                if expected and total and total != expected:
                    raise DownloadError('服务器文件大小与书架记录不一致，请刷新书架后重试。')
                received = 0
                try:
                    while True:
                        if cancel.is_set():
                            raise Cancelled('已取消，未完成文件已清理。')
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        if size == 0 and chunk.lstrip()[:20].lower().startswith((b'<!doctype html', b'<html', b'{"melonbooks"')):
                            raise DownloadError('服务器返回错误内容。')
                        received += len(chunk)
                        if segment_length and received > segment_length:
                            raise DownloadError('收到的数据超过声明的分段长度。')
                        target.write(chunk)
                        sha.update(chunk)
                        size += len(chunk)
                        progress(size, total or expected)
                except (URLError, TimeoutError, OSError) as e:
                    raise network_error(e) from None
                if segment_length and received != segment_length:
                    raise DownloadError('下载连接提前结束，文件未完成，请重试。')
            if not ranged or size == total:
                return size, total

    def download(self, book, folder, cancel, progress=lambda done, total: None):
        if cancel.is_set():
            raise Cancelled('已取消。')
        dest_dir = Path(folder).resolve() / f'{safe_name(title_of(book))} [{int(book["product_id"])}]'
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / original_name(book)
        if dest.exists():
            raise DownloadError(f'文件已存在，未覆盖：{dest.name}')
        url = self.download_url(book)
        tmp = dest.with_name(dest.name + '.' + uuid.uuid4().hex + '.part')
        size = 0
        sha = hashlib.sha256()
        try:
            with tmp.open('xb') as f:
                size, total = self._transfer(url, f, sha, int(book.get('file_size') or 0), cancel, progress)
                f.flush()
                os.fsync(f.fileno())
            expected = int(book.get('file_size') or 0)
            if cancel.is_set():
                raise Cancelled('已取消。')
            if size == 0 or (total and size != total) or (expected and size != expected):
                raise DownloadError('下载大小与服务器记录不一致，未标记完成，请重试。')
            # Windows rename does not replace an existing destination.
            tmp.rename(dest)
        finally:
            tmp.unlink(missing_ok=True)
        metadata = {k: book.get(k) for k in ('product_id', 'product_name', 'vol_name', 'file_type', 'file_size', 'order_date')}
        metadata.update(filename=dest.name, downloaded_bytes=size, sha256=sha.hexdigest())
        try:
            dest.with_suffix(dest.suffix + '.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            progress(size, size)
        return dest
