"""Use an ASCII drive alias for PostgreSQL's Windows non-ASCII path limitation.

SUBST changes the visible path only; every file remains under the D-drive project.
The mapping is per-user and recreated by the start scripts after a reboot.
"""
import ctypes
import json
from pathlib import Path
import string
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def postgres_root():
    kernel = ctypes.windll.kernel32
    expected = '\\??\\' + str(ROOT)
    for letter in reversed(string.ascii_uppercase):
        buffer = ctypes.create_unicode_buffer(32768)
        if kernel.QueryDosDeviceW(letter + ':', buffer, len(buffer)):
            if buffer.value.casefold().rstrip('\\') == expected.casefold().rstrip('\\'):
                return Path(letter + ':/')
    mask = kernel.GetLogicalDrives()
    for letter in reversed(string.ascii_uppercase[4:]):
        if not mask & (1 << (ord(letter) - ord('A'))):
            subprocess.run(['subst.exe', letter + ':', str(ROOT)], check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            record = {'drive': letter + ':', 'physical_root': str(ROOT),
                      'purpose': 'ASCII path alias only; no files stored outside project'}
            (ROOT / 'database/runtime_drive.json').write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return Path(letter + ':/')
    raise RuntimeError('No free drive letter for the PostgreSQL path alias.')


if __name__ == '__main__':
    print(postgres_root())
