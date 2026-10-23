#!/usr/bin/env python3
"""Small vendor-free builds; all lifecycle process operations are mocked."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='.laptop-tests-', dir=root) as directory:
    build = Path(directory)
    flags = ['-D_DEFAULT_SOURCE', '-D_POSIX_C_SOURCE=200809L', '-Isrc',
             '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
             '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections']
    if "--sanitize" in sys.argv:
        flags += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
    for test, extra in [('laptop_run_unit', []), ('laptop_menu_unit', ['src/ui.c'])]:
        binary = build / test
        subprocess.run([os.environ.get('CC', 'cc'), *flags, f'tests/{test}.c',
                        *extra, '-o', str(binary)], cwd=root, check=True)
        fixture = build / test.replace('_unit', '_fixtures')
        fixture.mkdir()
        subprocess.run([str(binary), str(fixture)], cwd=root, check=True, timeout=10)
