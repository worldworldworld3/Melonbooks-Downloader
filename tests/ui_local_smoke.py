"""Local batch page end-to-end UI test with generated encrypted fixtures."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'downloader'), str(ROOT / 'decoder')]
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from desktop import main
from test_ebg_decoder import DecoderTests

fixture = DecoderTests()
DecoderTests.setUpClass()
fixture.setUp()
unsupported = fixture.root / '不支持的示例文件.txt'
unsupported.write_text('test')
passed = []

def check(bridge, window):
    try:
        for _ in range(100):
            if window.evaluate_js('!!window.pywebview?.api'): break
            time.sleep(.1)
        assert window.evaluate_js('document.getElementById("convertLocal").disabled')
        bridge._client = SimpleNamespace(books={'123': dict(product_id=123,
            product_name='独立解码测试作品', drm_key=fixture.license)})
        bridge._update(logged_in=True, account='离线测试账号', folder=str(fixture.root / 'results'))
        time.sleep(.7)
        window.evaluate_js('document.getElementById("convertLocal").click()')
        for _ in range(100):
            if bridge.snapshot()['local_open']: break
            time.sleep(.1)
        with patch('ebg_decoder.client_private_key', return_value=fixture.private):
            bridge._drop({'dataTransfer': {'files': [dict(pywebviewFullPath=str(path))
                for path in (fixture.source, unsupported, fixture.source)]}})
            for _ in range(100):
                if window.evaluate_js('document.querySelectorAll("#localRows tr").length===2 && document.querySelector("#localRows .ready")!==null && document.querySelector("#localRows .blocked")!==null'): break
                time.sleep(.1)
            else: raise AssertionError('Expected ready and blocked rows')
            assert window.evaluate_js('!document.getElementById("startLocal").disabled')
            assert window.evaluate_js('document.getElementById("libraryPage").hidden')
            assert bridge._drop_element._event_handlers.get('drop')
            window.evaluate_js('document.getElementById("startLocal").click()')
            for _ in range(100):
                if window.evaluate_js('document.querySelector("#localRows .done")!==null'): break
                time.sleep(.1)
            else: raise AssertionError('Conversion did not finish')
            files = list((fixture.root / 'results').iterdir())
            assert len(files) == 1 and files[0].read_bytes() == fixture.payload
        assert window.evaluate_js('document.getElementById("startLocal").disabled')
        print('PASS: login gating, local page, native drop routing, deduplication, account preflight, UI conversion, output-only directory', flush=True)
        passed.append(True)
        if '--hold' in sys.argv: return
    except Exception:
        import traceback
        traceback.print_exc()
    window.destroy()

try:
    main(check)
finally:
    fixture.doCleanups()
sys.exit(0 if passed else 1)
