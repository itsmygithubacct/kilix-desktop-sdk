"""Host discovery follows the canonical gpu_terminal source allocation."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host


old_home = os.environ.pop("KILIX_HOME", None)
old_source = os.environ.get("GPU_TERMINAL_SOURCE_HOME")
try:
    source = tempfile.mkdtemp(prefix="gpu-terminal-source-")
    checkout = os.path.join(source, "kilix")
    os.makedirs(checkout)
    with open(os.path.join(checkout, "kilix"), "w") as handle:
        handle.write("#!/bin/sh\n")
    os.environ["GPU_TERMINAL_SOURCE_HOME"] = source
    assert host._discover_kilix_home() == checkout

    explicit = tempfile.mkdtemp(prefix="kilix-explicit-")
    os.environ["KILIX_HOME"] = explicit
    assert host._discover_kilix_home() == explicit
finally:
    if old_home is None:
        os.environ.pop("KILIX_HOME", None)
    else:
        os.environ["KILIX_HOME"] = old_home
    if old_source is None:
        os.environ.pop("GPU_TERMINAL_SOURCE_HOME", None)
    else:
        os.environ["GPU_TERMINAL_SOURCE_HOME"] = old_source

print("ok")
