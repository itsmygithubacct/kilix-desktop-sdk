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

# A test subprocess must not inherit anything that could decide its outcome.
# BASH_FUNC_* is the one that hides: it carries *exported shell functions*, so
# `command -v` inside a test would resolve the operator's shell function and
# report a tool as installed when the sandbox has no such thing.
dirty = {
    "PATH": "/usr/bin:/bin",
    "KILIX_STORAGE_HOME": "/live/storage",
    "GPU_TERMINAL_HOME": "/live/data",
    "KITTY_WINDOW_ID": "3",
    "BASH_FUNC_chromium%%": "() { echo ambient; }",
}
kept = runner.parent_env_without_stack_vars(dirty)
assert kept == {"PATH": "/usr/bin:/bin"}, kept

# The control: the same filter must keep an ordinary variable whose name merely
# resembles one of the stripped families, or "stripped" would be indiscernible
# from "dropped everything".
assert runner.parent_env_without_stack_vars({"KITTYCAT": "1"}) == {"KITTYCAT": "1"}

print("ok")
