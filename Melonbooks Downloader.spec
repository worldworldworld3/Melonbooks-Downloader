# Build with build.ps1. Only independent decoding is included.
from pathlib import Path
root = Path(SPECPATH)
from PyInstaller.utils.hooks import get_package_paths
webview_path = Path(get_package_paths('webview')[1])
pythonnet_path = Path(get_package_paths('pythonnet')[1])
a = Analysis(
    [str(root / 'downloader' / 'app.pyw')],
    pathex=[str(root / 'downloader'), str(root / 'decoder')],
    binaries=[],
    datas=[(str(root / 'downloader' / 'frontend'), 'frontend'),
           (str(root / 'LICENSE'), '.'),
           (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
           (str(root / 'licenses'), 'licenses'),
           (str(root / 'decoder' / 'android_client_material.json'), '.'),
           (str(root / 'decoder' / 'client_material.json'), '.')],
    hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms'],
    hookspath=[str(webview_path / '__pyinstaller'), str(pythonnet_path / '_pyinstaller')],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3', 'gi',
              'converter', 'desktop_automation', 'quiet_viewer'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='Melonbooks Downloader', debug=False, strip=False, upx=False,
          icon=str(root / 'app.ico'), version=str(root / 'version_info.txt'),
          console=False, disable_windowed_traceback=False)
