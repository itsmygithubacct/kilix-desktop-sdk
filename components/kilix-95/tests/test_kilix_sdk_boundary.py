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

# The version gate above compares a declared number. It cannot notice a
# provider reaching for a shared-settings symbol that the host SDK does not
# actually export — which is how a provider ends up importable against the
# version it claims and broken against the version it gets. Check the symbols
# themselves, not just the number.
from kilix_sdk import settings as shared_settings

referenced = set()
for source in sorted(ROOT.glob("*.py")) + sorted(ROOT.glob("apps/*.py")):
    tree = ast.parse(source.read_text(), filename=str(source))
    # Resolve whatever this file binds `kilix_sdk.settings` to, so a local
    # variable that happens to be called `settings` is not mistaken for it.
    aliases = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "kilix_sdk"
        for alias in node.names if alias.name == "settings"
    }
    if not aliases:
        continue
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases):
            referenced.add(node.attr)

missing = sorted(name for name in referenced if not hasattr(shared_settings, name))
assert not missing, (
    "provider uses shared-settings symbols this Kilix SDK does not export: "
    f"{missing}. Either the host is older than requires_kilix_sdk claims, or "
    "adding them should have bumped SDK_API_VERSION.")

print("ok")
