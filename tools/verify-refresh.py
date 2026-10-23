#!/usr/bin/env python3
"""Compare refreshed component bytes with exact, explicitly supplied sources.

Historical import maps remain independent. This check resolves each refresh
revision in its source repository and compares modes, blob IDs and gitlinks;
only the exact adaptation paths declared in the manifest may differ. Source
checkouts need not be at that revision and their working files are never read.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def tree(repo, revision):
    result = subprocess.run(
        ['git', '-C', str(repo), 'ls-tree', '-rz', revision],
        capture_output=True, check=True)
    entries = {}
    for record in result.stdout.split(b'\0'):
        if record:
            meta, path = record.split(b'\t', 1)
            entries[path.decode()] = meta.decode()
    return entries


def differences(left, right):
    return sorted(path for path in left.keys() | right.keys()
                  if left.get(path) != right.get(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', default=[], metavar='NAME=REPO')
    args = parser.parse_args()
    sources = dict(value.split('=', 1) for value in args.source)
    manifest = tomllib.loads((ROOT / 'manifest.toml').read_text())
    passed = 0
    for component in manifest['component']:
        name = component['name']
        if name not in sources:
            print(f'UNRESOLVED {name}: supply --source {name}=REPO')
            continue
        try:
            original = tree(sources[name], component['refresh_revision'])
            mirrored = tree(ROOT, 'HEAD:' + component['path'])
            changed = differences(original, mirrored)
            declared = sorted(component.get('refresh_local_changes', []))
            if changed != declared:
                print(f'FAIL {name}: undeclared={sorted(set(changed)-set(declared))}; '
                      f'stale={sorted(set(declared)-set(changed))}')
                continue
            print(f'PASS {name}: {len(original)} source entries; '
                  f'{len(changed)} declared adaptation paths')
            passed += 1
        except (subprocess.CalledProcessError, KeyError, OSError) as error:
            print(f'FAIL {name}: {error}')
    print(f'{passed}/{len(manifest["component"])} refresh sources verified')
    return 0 if passed == len(manifest['component']) else 1


if __name__ == '__main__':
    sys.exit(main())
