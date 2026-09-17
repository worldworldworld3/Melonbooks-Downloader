"""HTML bookshelf host. Only sanitized book metadata crosses the webview bridge."""
import json
import hashlib
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from collections import deque
from urllib.parse import urlsplit
from core import Client, DownloadError, Cancelled, title_of, original_name
import webview

HERE = Path(__file__).resolve().parent
from runtime import data_dir, login_session
sys.path.insert(0, str(HERE.parent / 'decoder'))
from ebg_decoder import convert_independent
from decode_support import Cancelled as ConversionCancelled
from official_license import PurchasedLicenses
from local_conversion import LocalQueue
from cache_storage import inventory, clear_previewed

def downloaded_sizes(books, folder):
    """Recognize final packages by original name and expected byte count."""
    files = {}
    for root, dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith('.ebg'): continue
            path = Path(root) / name
            try: size = path.stat().st_size
            except OSError: continue
            if size > 0: files.setdefault(name.lower(), []).append((path, size))
    result = {}
    for book in books:
        try:
            name = original_name(book)
            expected = int(book.get('file_size') or 0)
        except (DownloadError, ValueError, TypeError): continue
        for path, size in files.get(name, []):
            valid = expected > 0 and size == expected
            if expected <= 0:
                try:
                    meta = json.loads(Path(str(path) + '.json').read_text(encoding='utf-8'))
                    valid = str(meta['product_id']) == str(book['product_id']) and meta['downloaded_bytes'] == size
                except (OSError, ValueError, KeyError, TypeError): pass
            if valid:
                result[str(book['product_id'])] = size
                break
    return result

def downloaded_ids(books, folder):
    return list(downloaded_sizes(books, folder))

def book_view(book):
    thumb = str(book.get('thumbnail_url') or '')
    parsed = urlsplit(thumb)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        thumb = ''
    return dict(id=str(book['product_id']), title=title_of(book),
                circle=str(book.get('circle_name') or ''),
                author=str(book.get('vol_author_name') or book.get('author_name') or ''),
                thumbnail=thumb, format=str(book.get('file_type') or ''),
                size=0, date=str(book.get('order_date') or ''),
                adult=int(book.get('age_limit') or 0) > 0)

class Bridge:
    def __init__(self):
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._window = None
        self._client = None
        self._process = None
        self._closing = False
        self._revision = 0
        self._books = []
        self._data = data_dir(HERE)
        self._local = LocalQueue(self)
        self._cache_plan = None
        folder = str((Path.home() / 'Downloads' / 'Melonbooks Downloader') if getattr(sys, 'frozen', False) else HERE.parent / 'downloads')
        try:
            saved = json.loads((self._data / 'settings.json').read_text(encoding='utf-8'))['folder']
            if isinstance(saved, str) and Path(saved).is_absolute(): folder = saved
        except (OSError, ValueError, KeyError, TypeError): pass
        self._state = dict(busy=False, operation='', logged_in=False, account='',
            message='请先登录。', error=False,
            folder=folder, progress=0, progress_text='',
            downloaded=[], demo=False, local_open=False)
        path = self._data / 'device.json'
        try: self._device = str(uuid.UUID(json.loads(path.read_text())['device_id']))
        except (OSError, ValueError, KeyError, TypeError):
            self._device = str(uuid.uuid4())
            path.write_text(json.dumps({'device_id': self._device}), encoding='utf-8')

    def _update(self, **values):
        with self._lock: self._state.update(values)

    def snapshot(self, revision=-1):
        with self._lock:
            out = dict(self._state, revision=self._revision)
            out['downloaded'] = list(self._state['downloaded'])
            out['local_files'] = self._local.snapshot()
            if revision != self._revision: out['books'] = list(self._books)
            return out

    def _start(self, operation, job):
        with self._lock:
            if self._state['busy'] or self._closing: return {'error': '请等待当前操作完成。'}
            self._state.update(busy=True, operation=operation, error=False, progress=0, progress_text='')
            self._cancel.clear()
        def work():
            try: job()
            except (Cancelled, ConversionCancelled) as e: self._update(message=str(e) or '转换已取消，源文件保留，可通过转换本地文件重试。', error=False)
            except ValueError as e: self._update(message=str(e), error=True)
            except DownloadError as e: self._update(message=str(e), error=True)
            except Exception: self._update(message='操作失败，请检查网络、磁盘空间或目录权限。', error=True)
            finally: self._update(busy=False, operation='')
        threading.Thread(target=work, daemon=True).start()
        return {'ok': True}

    def _sync(self):
        self._update(message='正在加载已购书架…')
        try: books = self._client.sync()
        except DownloadError as e: raise DownloadError(f'账号已登录，但书架加载失败：{e} 请点击刷新重试。') from None
        sizes = self._downloaded_sizes(books)
        views = [dict(book_view(b), size=sizes.get(str(b['product_id']), 0)) for b in books]
        downloaded = list(sizes)
        with self._lock:
            self._books = views
            self._state['downloaded'] = downloaded
            self._revision += 1
        self._local.check()
        self._update(message=f'已同步 {len(views)} 本漫画 / 电子书。')

    def login(self):
        def job():
            self._update(message='请在官方登录窗口完成登录。')
            result = login_session(self._device, self._cancel, lambda: self._closing)
            if 'session' not in result: raise DownloadError(result.get('error', '登录未完成。'))
            self._client = Client(result['session'])
            with self._lock:
                self._books = []
                self._local.items.clear()
                self._state['local_open'] = False
                self._revision += 1
            self._update(logged_in=True, account=str(result['session']['customer_id']), downloaded=[])
            if not self._closing: self._sync()
        return self._start('login', job)

    def refresh(self):
        if not self._client: return {'error': '请先登录账号。'}
        return self._start('sync', self._sync)

    def choose_folder(self):
        with self._lock:
            if self._state['busy']: return {'error': '操作进行中，暂时不能更改保存目录。'}
        selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if selected:
            folder = str(Path(selected[0]).resolve())
            try:
                (self._data / 'settings.json').write_text(json.dumps({'folder': folder}), encoding='utf-8')
            except OSError: return {'error': '无法保存目录设置，请检查权限。'}
            self._update(folder=folder)
            self._refresh_downloads()
        return {'ok': True}

    def open_folder(self):
        try:
            folder=Path(self._state['folder']); folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)
            return {'ok': True}
        except OSError: return {'error': '无法打开保存目录，请检查目录权限。'}

    def cancel(self):
        self._cancel.set()
        self._update(message='正在取消，等待当前下载或转换结束…')
        return {'ok': True}

    def download(self, ids):
        if not self._client: return {'error': '请先登录账号。'}
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in self._client.books for i in ids):
            return {'error': '请从已购书架选择作品。'}
        books = [self._client.books[i] for i in dict.fromkeys(ids)]
        folder = self._state['folder']
        def job():
            downloaded = self._downloaded(self._client.books.values())
            self._update(downloaded=downloaded)
            if any(str(book['product_id']) in downloaded for book in books):
                raise DownloadError('选择中包含已下载作品，已取消其勾选，请重新开始下载。')
            failures = []
            for index, book in enumerate(books, 1):
                if self._cancel.is_set(): raise Cancelled('已取消，已完成的源文件和转换结果保留。')
                title = title_of(book)
                self._update(message=f'[{index}/{len(books)}] 正在下载 {title}', progress=0)
                started = time.monotonic()
                last = [0.0]
                samples = deque([(started, 0)])
                def progress(done, total):
                    now = time.monotonic()
                    if now-last[0] < .15 and done != total: return
                    last[0] = now
                    samples.append((now, done))
                    while len(samples) > 2 and samples[1][0] < now - 5:
                        samples.popleft()
                    speed = (done - samples[0][1]) / max(.001, now - samples[0][0])
                    self._update(progress=min(100, done * 100 / total) if total else 0,
                        progress_text=f'{done/1048576:.1f} MB' + (f' / {total/1048576:.1f} MB' if total else '') + f' · {speed/1048576:.2f} MB/s')
                try: source = self._client.download(book, self._cache_folder(), self._cancel, progress)
                except DownloadError as e: raise type(e)(f'已完成 {index-1}/{len(books)} 本；{title}：{e}') from None
                with self._lock:
                    self._state['downloaded'].append(str(book['product_id']))
                    try: actual_size = Path(source).stat().st_size
                    except OSError: actual_size = 0
                    self._books = [dict(view, size=actual_size) if view['id'] == str(book['product_id']) else view for view in self._books]
                    self._revision += 1
                try:
                    self._convert(source, book=book)
                except (ValueError, OSError) as e:
                    failures.append(f'{title}：{e}')
            if failures:
                self._update(message=f'下载完成 {len(books)} 本；{len(failures)} 本转换失败，源文件已保留。可在“转换本地文件”页面添加下载缓存重试。' + '；'.join(failures), error=True, progress=100, progress_text='')
            else:
                self._update(message=f'下载并转换完成，共 {len(books)} 本。', progress=100, progress_text='')
        return self._start('download', job)

    def _convert(self, source, book=None, authorization=None):
        source = Path(source)
        self._update(message=f'正在独立转换 {title_of(book) if book else source.name}',
                     progress=0, progress_text='独立解码 · ZIP/PDF 校验')
        provider = PurchasedLicenses(self._client, title_of, self._cancel) if self._client else None
        return convert_independent(source, Path(self._state['folder']), self._cancel,
            lambda text: self._update(progress_text=text),
            license_data=authorization[0] if authorization else book.get('drm_key') if book else None,
            title_override=authorization[1] if authorization else title_of(book) if book else None, license_provider=provider)

    def _cache_folder(self):
        # Keep source packages and metadata entirely outside the chosen output folder.
        identity = str(Path(self._state['folder']).resolve()).casefold().encode('utf-8')
        return self._data / 'source-cache' / hashlib.sha256(identity).hexdigest()[:20]

    def _downloaded_sizes(self, books):
        books = list(books)
        return {**downloaded_sizes(books, self._state['folder']),
                **downloaded_sizes(books, self._cache_folder())}

    def _downloaded(self, books):
        return list(self._downloaded_sizes(books))

    def _refresh_downloads(self):
        sizes = self._downloaded_sizes(self._client.books.values() if self._client else [])
        with self._lock:
            self._state['downloaded'] = list(sizes)
            self._books = [dict(view, size=sizes.get(view['id'], 0)) for view in self._books]
            self._revision += 1

    def cache_preview(self):
        with self._lock:
            if self._state['busy']: return {'error': '请等待当前操作完成。'}
            try: files = inventory(self._data)
            except (OSError, ValueError) as error: return {'error': str(error)}
            token = uuid.uuid4().hex
            self._cache_plan = (token, files)
            return {'token': token, 'count': len(files), 'bytes': sum(info[0] for _, info in files)}

    def clear_cache(self, token):
        with self._lock:
            if self._state['busy']: return {'error': '请等待当前操作完成。'}
            if not self._cache_plan or token != self._cache_plan[0]:
                return {'error': '请重新打开清除缓存确认窗口。'}
            files = self._cache_plan[1]
            self._cache_plan = None
            def job():
                removed, skipped, freed = clear_previewed(self._data, files, self._state['folder'])
                self._refresh_downloads()
                with self._lock:
                    for row in self._local.items:
                        if row['status'] != 'done' and not row['path'].exists():
                            row.update(status='blocked', detail='源文件已清除，请重新下载或添加文件。')
                self._update(message=f'已清除 {removed} 个缓存文件，释放 {freed/1048576:.1f} MB。'
                    + (f' {skipped} 个文件已变化或无法删除，已保留，请重试。' if skipped else '')
                    + ' 转换结果未删除；已重新检查下载标记。', error=bool(skipped), progress=100)
            return self._start('cache', job)

    def _local_guard(self):
        if not self._client: return {'error': '请先登录账号并同步已购书架。'}
        if self._state['busy']: return {'error': '请等待当前操作完成。'}
        return None

    def convert_local(self):
        with self._lock:
            error = self._local_guard()
            if error: return error
            self._state['local_open'] = True
        return {'ok': True}

    def close_local(self):
        with self._lock:
            if self._state['busy']: return {'error': '请先等待操作完成或取消操作。'}
            self._state['local_open'] = False
        return {'ok': True}

    def _add_paths(self, paths):
        with self._lock:
            error = self._local_guard()
            if error: return error
            if not self._state['local_open']: return {'error': '请先打开本地转换页面。'}
            return self._start('check', lambda: self._local.add(paths))

    def choose_local_files(self):
        with self._lock:
            error = self._local_guard()
            if error: return error
        selected = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
            file_types=('Melonbooks files (*.melon;*.ebg)', 'All files (*.*)'))
        return self._add_paths(selected) if selected else {'ok': True}

    def add_cached_files(self):
        return self._add_paths(list(self._cache_folder().rglob('*.ebg')))

    def check_local_files(self):
        with self._lock:
            error = self._local_guard()
            if error: return error
            return self._start('check', self._local.check)

    def remove_local_file(self, item_id=None):
        with self._lock:
            error = self._local_guard()
            if error: return error
            self._local.items[:] = [row for row in self._local.items if item_id and row['id'] != item_id]
        return {'ok': True}

    def start_local_conversion(self):
        with self._lock:
            error = self._local_guard()
            if error: return error
            if not any(row['status'] == 'ready' for row in self._local.items):
                return {'error': '没有通过当前账号授权校验的文件。'}
            return self._start('convert', self._local.convert)

    def _drop(self, event):
        files = event.get('dataTransfer', {}).get('files', [])
        paths = [file['pywebviewFullPath'] for file in files if file.get('pywebviewFullPath')]
        if not paths:
            self._update(message='未取得拖入文件的本地路径，请点击“添加文件”。')
            return
        result = self._add_paths(paths)
        if result and result.get('error'): self._update(message=result['error'])

    def _close(self):
        self._closing = True
        self._cancel.set()
        if self._process:
            try: self._process.terminate()
            except OSError: pass
        if self._state['busy']:
            def wait():
                while self._state['busy']: time.sleep(.15)
                self._window.destroy()
            threading.Thread(target=wait, daemon=True).start()
            return False
        return True

def main(on_ready=None):
    bridge=Bridge()
    html=(HERE/'frontend/index.html').read_text(encoding='utf-8')
    html=html.replace('/* APP_CSS */',(HERE/'frontend/style.css').read_text(encoding='utf-8'))
    html=html.replace('/* APP_JS */',(HERE/'frontend/app.js').read_text(encoding='utf-8'))
    window=webview.create_window('Melonbooks Downloader',html=html,js_api=bridge,
        width=1200,height=850,min_size=(740,580),background_color='#f6f7f4')
    bridge._window=window
    window.events.closing += bridge._close
    def attach():
        def guard(sender,args):
            if urlsplit(str(args.Uri)).scheme not in ('about','data'):
                args.Cancel=True
        window.native.webview.NavigationStarting += guard
        bridge._guard=guard
    window.events.before_show += attach
    def bind_drop():
        from webview.dom import DOMEventHandler
        bridge._drop_element = window.dom.get_element('#dropZone')
        bridge._drop_element.on('drop', DOMEventHandler(bridge._drop, prevent_default=True))
    window.events.loaded += bind_drop
    webview.settings['ALLOW_DOWNLOADS']=False
    webview.settings['ALLOW_FILE_URLS']=False
    webview.start((lambda: on_ready(bridge, window)) if on_ready else None,
                  gui='edgechromium', private_mode=True)

if __name__=='__main__': main()
