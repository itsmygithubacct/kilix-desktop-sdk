"""Resource locations for source checkouts and ordinary wheel installations."""

from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent
_INSTALLED = _PACKAGE / "_resources"
# BuildPy copies the canonical source documents here when building a wheel.
# Editable/source use retains the public schemas/ and contracts/ paths.
RESOURCE_ROOT = _INSTALLED if _INSTALLED.is_dir() else _PACKAGE.parents[1]
