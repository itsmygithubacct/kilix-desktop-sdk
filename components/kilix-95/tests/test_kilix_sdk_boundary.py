"""Kilix 95 runtime imports host helpers through kilix_sdk."""
import ast
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
KILIX_HOME = Path(os.environ.get("KILIX_HOME", ROOT.parent / "kilix"))
sys.path.insert(0, str(KILIX_HOME / "config"))


def import_sources(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


main_imports = import_sources(ROOT / "main.py")
assert "kilix_sdk" in main_imports
assert "browse" not in main_imports
assert "gfx" not in main_imports

host_text = (ROOT / "host.py").read_text()
assert "from kilix_sdk import paths" in host_text
assert "except ImportError:" in host_text

import kilix_sdk

manifest = json.loads((ROOT / "provider.json").read_text())
assert manifest["provider_api"] == 1
assert manifest["version"] == (ROOT / "VERSION").read_text().strip()
assert set(manifest["security_features"]) == {
    "default-password-nag", "masked-secret-clipboard"}
requirement = manifest["requires_kilix_sdk"]
required_api = tuple(int(part) for part in requirement.split("."))
assert len(required_api) == 2
assert kilix_sdk.SDK_API_VERSION[0] == required_api[0]
assert kilix_sdk.SDK_API_VERSION >= required_api
kilix_sdk.require_compatible(requirement)
assert f'require_kilix_sdk("{requirement}")' in (ROOT / "main.py").read_text()

print("ok")
