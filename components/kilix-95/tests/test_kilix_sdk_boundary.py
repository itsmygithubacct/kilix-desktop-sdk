"""Kilix 95 runtime imports host helpers through kilix_sdk."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

print("ok")
