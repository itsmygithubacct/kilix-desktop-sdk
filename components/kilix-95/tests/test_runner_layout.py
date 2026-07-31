"""The test runner honors explicit host paths in grouped and CI layouts."""
import importlib.util
from pathlib import Path


RUNNER_PATH = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("kilix95_test_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


ci_kilix = "/workspace/kilix-95/kilix"
source_home, kilix_home = runner.resolve_source_layout(
    {"KILIX_HOME": ci_kilix},
    "/workspace/kilix-95/kilix-95/tests",
)
assert source_home == "/workspace/kilix-95"
assert kilix_home == ci_kilix

source_home, kilix_home = runner.resolve_source_layout(
    {"GPU_TERMINAL_SOURCE_HOME": "/workspace/gpu-terminal"},
    "/unrelated/provider/tests",
)
assert source_home == "/workspace/gpu-terminal"
assert kilix_home == "/workspace/gpu-terminal/kilix"

source_home, kilix_home = runner.resolve_source_layout(
    {},
    "/workspace/gpu-terminal/kilix-desktops/kilix-95/tests",
)
assert source_home == "/workspace/gpu-terminal"
assert kilix_home == "/workspace/gpu-terminal/kilix"

print("ok")
