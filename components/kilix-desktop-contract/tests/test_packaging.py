"""Validate resources after a source distribution becomes a normal wheel."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_sdist_wheel_can_validate_without_source_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            source = scratch / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(
                ".venv", "build", "dist", "*.egg-info", "__pycache__"))
            dist = scratch / "dist"
            dist.mkdir()
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            def run(args, cwd):
                result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result
            run([sys.executable, "-c",
                 "from setuptools.build_meta import build_sdist; build_sdist(" + repr(str(dist)) + ")"], source)
            unpacked = scratch / "unpacked"
            unpacked.mkdir()
            with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
                archive.extractall(unpacked, filter="data")
            project = next(unpacked.iterdir())
            run([sys.executable, "-c",
                 "from setuptools.build_meta import build_wheel; build_wheel(" + repr(str(dist)) + ")"], project)
            installed = scratch / "site-packages"
            with zipfile.ZipFile(next(dist.glob("*.whl"))) as wheel:
                wheel.extractall(installed)
            # Only the wheel contents remain visible to the runtime check.
            shutil.rmtree(source)
            shutil.rmtree(unpacked)
            env["PYTHONPATH"] = str(installed)
            action = scratch / "action.json"
            action.write_text(json.dumps({"schema_version": 1, "verb": "url.open",
                "payload": "https://example.invalid/", "trace_id": "extension"}))
            code = """
from pathlib import Path
from kilix_desktop_contract.validation import validators, SCHEMA_PATHS
from kilix_desktop_contract.readiness import load_requirements, validate_requirements
from kilix_desktop_contract.cli import main
assert len(validators()) == 7
assert all('_resources' in str(path) for path in SCHEMA_PATHS.values())
validate_requirements(load_requirements())
raise SystemExit(main(['validate', 'action', 'action.json']))
"""
            run([sys.executable, "-c", code], scratch)


if __name__ == "__main__":
    unittest.main()
