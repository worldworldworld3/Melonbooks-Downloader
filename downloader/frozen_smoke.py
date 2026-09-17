"""Explicit offline executable smoke test; never uses a real account."""
import json
import os
from pathlib import Path
import threading
import time
import traceback
import tempfile
from types import SimpleNamespace


def run(report):
    report = Path(report)
    done = threading.Event()
    def watchdog():
        if not done.wait(50):
            report.write_text(json.dumps({'ok': False, 'error': 'Smoke test timed out'}), encoding='utf-8')
            os._exit(2)
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        from desktop import main, book_view
        from core import original_name
        from ebg_decoder import client_private_key
        from runtime import login_session
        for profile in ('android', 'windows'):
            assert client_private_key(profile).key_size >= 1024
        def check(bridge, window):
            try:
                for _ in range(100):
                    if window.evaluate_js('!!window.pywebview?.api && !!document.getElementById("convertLocal")'):
                        break
                    time.sleep(.1)
                else:
                    raise AssertionError('UI not ready')
                assert window.evaluate_js('document.title') == 'Melonbooks Downloader'
                assert window.evaluate_js('document.getElementById("download").textContent') == '下载并自动转换'
                assert window.evaluate_js('document.getElementById("convertLocal").disabled')
                assert 'error' in bridge.convert_local()
                bridge._client = SimpleNamespace(books={})
                bridge._update(logged_in=True, account='离线界面测试')
                bridge.convert_local()
                with tempfile.TemporaryDirectory() as folder:
                    sample = Path(folder) / '不支持的测试文件.txt'
                    sample.write_text('Offline smoke test', encoding='utf-8')
                    bridge._drop({'dataTransfer': {'files': [{'pywebviewFullPath': str(sample)}]}})
                    for _ in range(100):
                        if not bridge.snapshot()['busy'] and window.evaluate_js('document.querySelectorAll("#localRows .blocked").length===1'):
                            break
                        time.sleep(.1)
                    else: raise AssertionError('Local upload/check page did not update')
                    assert window.evaluate_js('!document.getElementById("localPage").hidden && document.getElementById("startLocal").disabled')
                    assert bridge._drop_element._event_handlers.get('drop'), 'Native drop handler missing'
                    # Exercise deletion exclusively in this generated temporary cache.
                    bridge._data = Path(folder) / 'settings'
                    output = Path(folder) / 'output'
                    output.mkdir()
                    protected = output / 'converted.zip'
                    protected.write_bytes(b'keep converted output')
                    bridge._update(folder=str(output), local_open=False)
                    book = dict(product_id=1, product_name='大小显示测试', file_type='ZIPJPEG', file_size=0)
                    bridge._client.books = {'1': book}
                    bridge._books = [book_view(book)]
                    bridge._revision += 1
                    def wait_for(script):
                        for _ in range(100):
                            if window.evaluate_js(script): return
                            time.sleep(.1)
                        raise AssertionError(script)
                    wait_for('document.querySelectorAll("#shelf .book").length===1')
                    assert window.evaluate_js('document.querySelectorAll("#shelf .file-size").length===0 && !document.body.textContent.includes("大小未知")')
                    cache = bridge._cache_folder()
                    cache.mkdir(parents=True)
                    source = cache / original_name(book)
                    source.write_bytes(b'x' * 1048576)
                    Path(str(source) + '.json').write_text(json.dumps(dict(product_id=1, downloaded_bytes=1048576)))
                    bridge._refresh_downloads()
                    wait_for('document.querySelector("#shelf .file-size")?.textContent==="1.0 MB"')
                    window.evaluate_js('document.getElementById("clearCache").click()')
                    wait_for('document.getElementById("cacheDialog").open')
                    assert window.evaluate_js('document.getElementById("cacheDialog").textContent.includes("无法再通过这些缓存重试转换")')
                    window.evaluate_js('document.getElementById("cancelClearCache").click()')
                    assert source.exists()
                    window.evaluate_js('document.getElementById("clearCache").click()')
                    wait_for('document.getElementById("cacheDialog").open')
                    window.evaluate_js('document.getElementById("confirmClearCache").click()')
                    wait_for('document.querySelectorAll("#shelf .file-size").length===0 && document.querySelectorAll("#shelf .is-downloaded").length===0')
                    assert not source.exists() and protected.exists()
                bridge._local.items.clear()
                bridge._client = None
                bridge._update(logged_in=False, account='', local_open=False)
                result = login_session('test', threading.Event(), test=True)
                assert result.get('session', {}).get('access_token') == 'test', 'Isolated login callback failed'
                report.write_text(json.dumps({'ok': True, 'checks': ['bundled crypto profiles', 'WebView2 UI', 'JavaScript bridge', 'login-only local page', 'drop handler and file status', 'size hidden before download', 'actual downloaded size', 'cache confirmation and cancellation', 'temporary cache cleanup preserves output', 'frozen isolated login callback']}), encoding='utf-8')
            except Exception:
                report.write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}), encoding='utf-8')
            finally:
                done.set()
                window.destroy()
        main(check)
    except Exception:
        report.write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}), encoding='utf-8')
        done.set()
