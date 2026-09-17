"""Offline tests. No real account, network, or GUI required."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'downloader'), str(ROOT / 'decoder'), str(ROOT / 'tests')]
import desktop

if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as folder:
        def isolated_data(here):
            return Path(folder) if here == ROOT / 'downloader' else here
        with patch('desktop.data_dir', side_effect=isolated_data):
            suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py')
            result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
