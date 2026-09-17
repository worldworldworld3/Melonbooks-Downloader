"""Account-bound local conversion queue. No file bytes or licenses enter the UI."""
from pathlib import Path
import uuid

from core import title_of
from decode_support import Cancelled
from ebg_decoder import EbgFile
from official_license import PurchasedLicenses


class LocalQueue:
    def __init__(self, bridge):
        self.bridge = bridge
        self.items = []

    def snapshot(self):
        return [{k: row[k] for k in ('id', 'name', 'size', 'title', 'status', 'detail')}
                for row in self.items]

    def update(self, row, **values):
        with self.bridge._lock:
            row.update(values)

    def inspect(self, path, provider):
        if self.bridge._cancel.is_set(): raise Cancelled()
        if path.suffix.lower() not in ('.melon', '.ebg'):
            raise ValueError('不支持此扩展名，请添加 .melon 或 .ebg 文件。')
        with path.open('rb') as stream:
            ebg = EbgFile(stream)
            # Intentionally require this account's purchased license even when LCNS exists.
            license_data, title = provider(ebg.content_id, source=path)
            ebg.content_key(license_data)
        return license_data, title

    def add(self, paths):
        with self.bridge._lock:
            known = {str(row['path']).casefold() for row in self.items}
            for source in paths:
                path = Path(source).resolve()
                if str(path).casefold() in known: continue
                known.add(str(path).casefold())
                self.items.append(dict(id=uuid.uuid4().hex, path=path, name=path.name,
                    size=0, title='', status='pending', detail='等待当前账号授权校验'))
        self.check()

    def check(self):
        provider = PurchasedLicenses(self.bridge._client, title_of, self.bridge._cancel)
        try:
            for row in self.items:
                if row['status'] == 'done': continue
                self.update(row, status='checking', detail='正在校验文件格式与账号授权…')
                try:
                    size = row['path'].stat().st_size
                    self.update(row, size=size)
                    _, title = self.inspect(row['path'], provider)
                    self.update(row, size=size, title=title, status='ready',
                                detail='授权校验通过。')
                except (ValueError, OSError) as error:
                    self.update(row, status='blocked', detail=str(error))
        finally:
            for row in self.items:
                if row['status'] in ('checking', 'pending'):
                    self.update(row, status='pending', detail='尚未完成校验，请重新校验。')

    def convert(self):
        rows = [r for r in self.items if r['status'] == 'ready']
        provider = PurchasedLicenses(self.bridge._client, title_of, self.bridge._cancel)
        completed = 0
        for row in rows:
            if self.bridge._cancel.is_set(): raise Cancelled()
            self.update(row, status='converting', detail='正在转换…')
            try:
                # Recheck against the current file and account, never trust a UI status.
                authorization = self.inspect(row['path'], provider)
                output = self.bridge._convert(row['path'], authorization=authorization)
                self.update(row, status='done', detail=f'已保存：{output.name}')
                completed += 1
            except Cancelled:
                self.update(row, status='ready', detail='已取消，可重新开始转换。')
                raise
            except (ValueError, OSError) as error:
                self.update(row, status='failed', detail=str(error))
            except Exception:
                self.update(row, status='failed', detail='转换未完成，请重新校验后重试。')
                raise
        self.bridge._update(message=f'本地转换完成 {completed}/{len(rows)} 个。',
                            error=completed != len(rows), progress=100, progress_text='')
