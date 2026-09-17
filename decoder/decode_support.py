"""Shared validation helpers for independent and legacy conversion."""
import re
import zipfile
from pathlib import Path

class Cancelled(Exception):
    pass


def source_stem(source):
    name = Path(source).name
    for suffix in ('.zipjpeg.ebg', '.pdf.ebg'):
        if name.lower().endswith(suffix):
            return name[:-len(suffix)]
    return Path(source).stem


def safe_title(title, source):
    name = (title or '').strip() or source_stem(source)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().rstrip('. ')
    if not name:
        name = '未命名作品'
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', name, re.I):
        name = '_' + name
    # Leave room for extension and duplicate numbering; count UTF-16 units.
    return name.encode('utf-16-le')[:300].decode('utf-16-le', errors='ignore').rstrip('. ')


def valid_payload(path, kind):
    try:
        if kind == 'zip':
            with zipfile.ZipFile(path) as archive:
                return archive.testzip() is None
        with path.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                return False
            stream.seek(max(0, path.stat().st_size - 4096))
            return b'%%EOF' in stream.read()
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError):
        return False


