"""Official login in an isolated WebView2 window, returning session over a pipe."""
import json
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit
from core import login_url, parse_callback, encrypt
import webview

def trace(message):
    if sys.stderr is not None:
        print(message, file=sys.stderr, flush=True)

def run(device_id, test=False):
    answer = {}
    initialized = False
    window = webview.create_window('Melonbooks 官方登录', html='<html><body>正在打开官方登录页…</body></html>', width=940, height=780)

    def navigation(sender, args):
        url = str(args.Uri)
        if test: trace('navigation: '+urlsplit(url).scheme)
        if urlsplit(url).scheme == 'melonbooks':
            args.Cancel = True
            try:
                answer['session'] = parse_callback(url)
            except Exception:
                answer['error'] = '登录返回数据无法识别，请重新登录。'
            threading.Thread(target=window.destroy, daemon=True).start()

    def attach():
        if test: trace('attached')
        window.native.webview.NavigationStarting += navigation

    def loaded():
        nonlocal initialized
        if test: trace('loaded')
        if initialized:
            return
        initialized = True
        if test:
            fake = {'melonbooks': {'result': {'customer_id': 1, 'access_token': 'test', 'refresh_token': 'test', 'expires_in': '2099-01-01 00:00:00'}}}
            window.evaluate_js('location.href = ' + json.dumps('melonbooks://login/' + encrypt(json.dumps(fake))))
        else:
            window.load_url(login_url(device_id))

    window.events.before_show += attach
    window.events.loaded += loaded
    webview.settings['ALLOW_DOWNLOADS'] = False
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.start(gui='edgechromium', private_mode=True, debug=False)
    return answer or {'error': '登录窗口已关闭。'}

if __name__ == '__main__':
    try:
        data = json.loads(sys.stdin.readline())
        result = run(data['device_id'], data.get('test', False))
    except Exception:
        result = {'error': '登录窗口启动失败，请确认已安装 Microsoft Edge WebView2 Runtime。'}
    print(json.dumps(result), flush=True)
