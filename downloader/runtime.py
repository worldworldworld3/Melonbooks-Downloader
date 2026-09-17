"""Runtime paths and isolated login process, including frozen Windows builds."""
import multiprocessing
import os
from pathlib import Path
import sys


def data_dir(source_dir):
    if not getattr(sys, 'frozen', False):
        return source_dir
    path = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Melonbooks Downloader'
    path.mkdir(parents=True, exist_ok=True)
    return path


def login_worker(connection, device_id, test=False):
    try:
        from login_window import run
        connection.send(run(device_id, test=test))
    except Exception:
        connection.send({'error': '登录窗口启动失败，请确认已安装 Microsoft Edge WebView2 Runtime。'})
    finally:
        connection.close()


def login_session(device_id, cancel, closing=lambda: False, *, test=False):
    from core import Cancelled, DownloadError
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=login_worker, args=(child, device_id, test))
    process.start()
    child.close()
    try:
        while not parent.poll(.2):
            if cancel.is_set() or closing():
                raise Cancelled('登录已取消。')
            if not process.is_alive():
                raise DownloadError('登录窗口没有正常返回，请重试。')
        try:
            return parent.recv()
        except EOFError:
            raise DownloadError('登录窗口没有正常返回，请重试。') from None
    finally:
        parent.close()
        process.join(.5)
        if process.is_alive():
            process.terminate()
            process.join(5)
