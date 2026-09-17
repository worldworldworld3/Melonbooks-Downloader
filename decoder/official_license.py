"""Resolve licenses from the current purchased bookshelf; memory only."""
import hashlib
from pathlib import Path
from decode_support import Cancelled


class PurchasedLicenses:
    def __init__(self, client, title_of, cancel=None, log=lambda text: None):
        self.client = client
        self.title_of = title_of
        self.cancel = cancel
        self.log = log
        self.matches = {}

    def __call__(self, content_id, source=None, probe=True):
        # META content_id is a DRM content identifier, not necessarily the
        # storefront product_id. Android filenames use MD5(str(product_id)).
        name = Path(source).name.lower().split('.')[0] if source else ''
        candidates = [book for pid, book in self.client.books.items()
                      if (name and hashlib.md5(str(pid).encode()).hexdigest() == name)
                      or (book.get('content_id') is not None and str(book['content_id']) == str(content_id))]
        if len(candidates) > 1:
            raise ValueError('文件名与内容编号匹配到不同作品，请恢复下载时的原文件名。')
        book = candidates[0] if candidates else self.client.books.get(str(content_id))
        if not book and source and probe:
            book = self.match_authorized_file(source)
        if not book:
            raise ValueError('未能在已购书架匹配该文件，请检查账号并保留下载时的哈希文件名。')
        value = book.get('drm_key')
        if not isinstance(value, str) or not value.strip():
            raise ValueError('服务器没有返回该作品的授权数据，请重新登录同步。')
        return value, self.title_of(book)

    def match_authorized_file(self, source):
        """For renamed/legacy files, match only licenses from this purchased shelf.

        KTST binds a candidate to the encrypted file. No payload is decrypted
        here, and an ambiguous match must not supply a possibly wrong title.
        """
        from ebg_decoder import EbgFile, client_private_key
        path = Path(source)
        stat = path.stat()
        cache_key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
        if cache_key in self.matches:
            return self.matches[cache_key]
        self.log('文件编号无法直接匹配，正在用当前已购书架授权校验作品归属。')
        private = client_private_key()
        found = []
        with path.open('rb') as stream:
            ebg = EbgFile(stream)
            for book in self.client.books.values():
                if self.cancel and self.cancel.is_set():
                    raise Cancelled()
                value = book.get('drm_key')
                if not isinstance(value, str) or not value:
                    continue
                try:
                    ebg.content_key(value, private)
                except ValueError:
                    continue
                found.append(book)
                if len(found) > 1:
                    raise ValueError('多个已购条目可解开此文件，无法唯一确定标题，请保留下载时的原文件名。')
        if not found:
            raise ValueError('当前书架授权未通过该文件的密钥校验。请核对购买账号；也可能是不同客户端的授权格式不兼容。')
        self.matches[cache_key] = found[0]
        return found[0]
