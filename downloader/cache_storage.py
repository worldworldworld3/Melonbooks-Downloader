"""Remove only explicitly previewed source-cache files, never follow links."""
import os
from pathlib import Path
import stat


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def checked_root(data_dir):
    root = Path(data_dir).resolve() / 'source-cache'
    if root.exists() and is_link(root):
        raise ValueError('缓存目录是链接或重解析点，无法安全清除。')
    return root


def signature(path):
    info = path.stat()
    return (info.st_size, info.st_mtime_ns, info.st_ino)


def inventory(data_dir):
    root = checked_root(data_dir)
    files = []
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not is_link(Path(folder) / name)]
        for name in names:
            path = Path(folder) / name
            lower = name.lower()
            if not (lower.endswith(('.ebg', '.ebg.json')) or ('.ebg.' in lower and lower.endswith('.part'))):
                continue
            if not is_link(path) and path.is_file():
                files.append((path.relative_to(root), signature(path)))
    return files


def clear_previewed(data_dir, files, output_dir):
    root = checked_root(data_dir)
    output = Path(output_dir).resolve()
    if output == root or output.is_relative_to(root):
        raise ValueError('输出目录位于缓存内，请先将输出目录改到缓存以外再清除。')
    removed = skipped = freed = 0
    for relative, expected in files:
        path = root / relative
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('缓存路径无效。')
        try:
            for part in (path, *path.parents):
                if is_link(part): raise OSError('Linked cache path')
                if part == root: break
            if not path.resolve().is_relative_to(root) or signature(path) != expected:
                skipped += 1
                continue
            path.unlink()
            removed += 1
            freed += expected[0]
        except FileNotFoundError:
            continue
        except OSError:
            skipped += 1
    return removed, skipped, freed
