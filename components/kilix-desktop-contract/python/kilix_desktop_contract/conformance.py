"""Process-isolated non-interactive provider conformance checks.

The adapter-stage mode exists for the ordered release window in which protocol
adapters are present but shared persistence is not.  It still requires all
read-only documents, screenshot truthfulness and explicit unavailable exits;
only migration execution is relaxed.  A final run omits that mode and requires
a valid dry-run migration record.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence

from .constants import DEADLINES_SECONDS, EXIT_STATUSES
from .validation import errors_for, validators


MAX_OUTPUT_BYTES = 4 * 1024 * 1024

PROVIDER_ENVIRONMENT_NAMES = frozenset(
    {
        "LC_ALL",
        "TZ",
        "PATH",
        "HOME",
        "TMP",
        "TEMP",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
        "GPU_TERMINAL_HOME",
        "GPU_TERMINAL_SETTINGS_FILE",
        "KILIX_HOME",
        "KILIX_STORAGE_HOME",
        "KILIX_CONFIG_HOME",
        "KILIX_STATE_DIRECTORY",
        "KILIX_CACHE_HOME",
        "KILIX_DATA_HOME",
        "KILIX_SESSION_HOME",
        "KILIX_BUILD_DIRECTORY",
        "KILIX_STATE_LIBRARY",
        "KILIX95_STORAGE_HOME",
        "KILIX95_CONFIG_HOME",
        "KILIX95_STATE_HOME",
        "KILIX95_CACHE_HOME",
        "KILIX95_DATA_HOME",
        "KILIX95_SESSION_HOME",
        "KILIX_CAP_CONFIG_HOME",
        "KILIX_LAND_DESKTOP_CONFIG_HOME",
        "KILIX_LAND_DESKTOP_ASSETS",
        "KILIX_ICEWM_STORAGE_HOME",
        "KILIX_ICEWM_PREFIX",
        "KILIX_TUI_UTILS_PREFIX",
        "KILIX_DESKTOP_DIR",
        "KILIX_RECYCLE_DIR",
        "KILIX_DESKTOP_CONTRACT_COMMAND",
        "PYTHONDONTWRITEBYTECODE",
    }
)


class ConformanceError(RuntimeError):
    """A provider does not satisfy the exercised protocol surface."""


@dataclass(frozen=True)
class EndpointResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class ConformanceReport:
    provider_id: str
    checks: tuple[str, ...]
    adapter_stage: bool


@dataclass(frozen=True)
class MatrixProvider:
    provider_id: str
    command: tuple[str, ...]
    expected_checks: tuple[str, ...]
    entry_path: Path | None = None
    entry_sha256: str | None = None


@dataclass(frozen=True)
class MatrixReport:
    passes: int
    providers: tuple[MatrixProvider, ...]
    reports: tuple[ConformanceReport, ...]

    @property
    def invocation_count(self) -> int:
        return len(self.reports)

    @property
    def check_count(self) -> int:
        return sum(len(report.checks) for report in self.reports)


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass


def _group_exists(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _bounded_read(handle, label: str) -> bytes:
    size = os.fstat(handle.fileno()).st_size
    if size > MAX_OUTPUT_BYTES:
        raise ConformanceError(f"provider {label} exceeds {MAX_OUTPUT_BYTES} bytes")
    handle.seek(0)
    return handle.read()


def run_endpoint(
    command: Sequence[str],
    arguments: Sequence[str],
    *,
    timeout: float,
    environment: Mapping[str, str] | None = None,
) -> EndpointResult:
    if not command:
        raise ConformanceError("provider command is empty")
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                [*command, *arguments],
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                env=None if environment is None else dict(environment),
                start_new_session=True,
            )
        except OSError as error:
            raise ConformanceError(f"cannot start provider: {error}") from error
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            _terminate_group(process)
            raise ConformanceError(
                f"provider endpoint timed out after {timeout:g}s"
            ) from error

        # A successful endpoint is not allowed to abandon descendants. Files,
        # rather than pipes, ensure a child cannot hide by holding an output FD.
        time.sleep(0.02)
        if _group_exists(process.pid):
            _terminate_group(process)
            raise ConformanceError("provider endpoint left a live process-group member")
        stdout = _bounded_read(stdout_file, "stdout")
        stderr = _bounded_read(stderr_file, "stderr")
    return EndpointResult(returncode, stdout, stderr)


def _absolute_profile_path(value: os.PathLike[str] | str, label: str) -> str:
    path = os.fspath(value)
    if not path or "\0" in path or not os.path.isabs(path):
        raise ConformanceError(f"{label} must be an absolute path")
    return os.path.normpath(path)


def _sandbox_environment(
    root: Path,
    *,
    kilix_home: os.PathLike[str] | str,
    contract_command: os.PathLike[str] | str,
    state_library: os.PathLike[str] | str,
    land_assets: os.PathLike[str] | str,
) -> dict[str, str]:
    home = root / "home"
    runtime = root / "runtime"
    temporary = root / "tmp"
    home.mkdir(mode=0o700)
    runtime.mkdir(mode=0o700)
    temporary.mkdir(mode=0o700)
    data = root / "gpu-terminal"
    kilix = data / "kilix"
    kilix95 = data / "kilix-95"
    environment = {
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "TMP": str(temporary),
        "TEMP": str(temporary),
        "TMPDIR": str(temporary),
        "XDG_CACHE_HOME": str(root / "xdg" / "cache"),
        "XDG_CONFIG_HOME": str(root / "xdg" / "config"),
        "XDG_DATA_HOME": str(root / "xdg" / "data"),
        "XDG_RUNTIME_DIR": str(runtime),
        "XDG_STATE_HOME": str(root / "xdg" / "state"),
        "GPU_TERMINAL_HOME": str(data),
        "GPU_TERMINAL_SETTINGS_FILE": str(data / "settings.conf"),
        "KILIX_HOME": _absolute_profile_path(kilix_home, "Kilix host root"),
        "KILIX_STORAGE_HOME": str(kilix),
        "KILIX_CONFIG_HOME": str(kilix / "config"),
        "KILIX_STATE_DIRECTORY": str(kilix / "state"),
        "KILIX_CACHE_HOME": str(kilix / "cache"),
        "KILIX_DATA_HOME": str(kilix / "data"),
        "KILIX_SESSION_HOME": str(kilix / "session"),
        "KILIX_BUILD_DIRECTORY": str(kilix / "build"),
        "KILIX_STATE_LIBRARY": _absolute_profile_path(
            state_library, "Kilix state library"
        ),
        "KILIX95_STORAGE_HOME": str(kilix95),
        "KILIX95_CONFIG_HOME": str(kilix95 / "config"),
        "KILIX95_STATE_HOME": str(kilix95 / "state"),
        "KILIX95_CACHE_HOME": str(kilix95 / "cache"),
        "KILIX95_DATA_HOME": str(kilix95 / "data"),
        "KILIX95_SESSION_HOME": str(kilix95 / "session"),
        "KILIX_CAP_CONFIG_HOME": str(data / "kilix-cap" / "config"),
        "KILIX_LAND_DESKTOP_CONFIG_HOME": str(
            data / "kilix-land-desktop" / "config"
        ),
        "KILIX_LAND_DESKTOP_ASSETS": _absolute_profile_path(
            land_assets, "Kilix Land asset root"
        ),
        "KILIX_ICEWM_STORAGE_HOME": str(data / "kilix-icewm"),
        "KILIX_ICEWM_PREFIX": str(data / "kilix-icewm" / "prefix"),
        "KILIX_TUI_UTILS_PREFIX": str(root / "prefix"),
        "KILIX_DESKTOP_DIR": str(root / "desktop"),
        "KILIX_RECYCLE_DIR": str(root / "recycle"),
        "KILIX_DESKTOP_CONTRACT_COMMAND": _absolute_profile_path(
            contract_command, "desktop contract command"
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if set(environment) != PROVIDER_ENVIRONMENT_NAMES:
        raise RuntimeError("provider environment does not match its frozen name set")
    return environment


def _tree_snapshot(root: Path) -> dict[str, tuple[object, ...]]:
    snapshot: dict[str, tuple[object, ...]] = {}
    paths = [root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())]
    for path in paths:
        status = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        mode = stat.S_IMODE(status.st_mode)
        if stat.S_ISREG(status.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot[relative] = (
                "file",
                mode,
                status.st_size,
                status.st_mtime_ns,
                digest,
            )
        elif stat.S_ISDIR(status.st_mode):
            snapshot[relative] = ("directory", mode, status.st_mtime_ns)
        elif stat.S_ISLNK(status.st_mode):
            snapshot[relative] = (
                "symlink",
                mode,
                status.st_mtime_ns,
                os.readlink(path),
            )
        else:
            snapshot[relative] = (
                "special",
                stat.S_IFMT(status.st_mode),
                mode,
                status.st_mtime_ns,
            )
    return snapshot


def _read_only_endpoint(
    command: Sequence[str],
    arguments: Sequence[str],
    *,
    timeout: float,
    environment: Mapping[str, str],
    sandbox: Path,
    endpoint: str,
) -> EndpointResult:
    before = _tree_snapshot(sandbox)
    result = run_endpoint(
        command,
        arguments,
        timeout=timeout,
        environment=environment,
    )
    after = _tree_snapshot(sandbox)
    if after != before:
        changed = sorted(
            path
            for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        )
        preview = ", ".join(changed[:8])
        if len(changed) > 8:
            preview += f", ... ({len(changed)} paths)"
        raise ConformanceError(
            f"read-only {endpoint} mutated the sandbox: {preview}"
        )
    return result


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConformanceError(f"provider JSON repeats key {key!r}")
        result[key] = value
    return result


def _json_document(result: EndpointResult, kind: str) -> dict[str, Any]:
    if result.returncode != 0:
        raise ConformanceError(f"{kind} endpoint exited {result.returncode}")
    if result.stderr:
        raise ConformanceError(f"{kind} endpoint wrote unexpected stderr")
    if not result.stdout.endswith(b"\n") or result.stdout.endswith(b"\n\n"):
        raise ConformanceError(f"{kind} stdout must end in exactly one newline")
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConformanceError(f"{kind} stdout is not UTF-8") from error
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicates)
    except json.JSONDecodeError as error:
        raise ConformanceError(f"{kind} stdout is not one JSON document: {error}") from error
    if not isinstance(document, dict):
        raise ConformanceError(f"{kind} stdout is not a JSON object")
    validation_errors = errors_for(kind, document, validators())
    if validation_errors:
        raise ConformanceError(f"{kind}: {'; '.join(validation_errors)}")
    return document


def _capability_available(value: object) -> bool:
    return value is True or (
        isinstance(value, dict) and value.get("available") is True
    )


def _expect_unavailable(result: EndpointResult, endpoint: str) -> None:
    if result.returncode != EXIT_STATUSES["unavailable"]:
        raise ConformanceError(
            f"{endpoint} must exit {EXIT_STATUSES['unavailable']}, "
            f"got {result.returncode}"
        )
    if result.stdout:
        raise ConformanceError(f"unavailable {endpoint} wrote stdout")
    if not result.stderr:
        raise ConformanceError(f"unavailable {endpoint} omitted its diagnostic")
    try:
        result.stderr.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConformanceError(f"{endpoint} diagnostic is not UTF-8") from error


def run_conformance(
    command: Sequence[str],
    *,
    adapter_stage: bool = False,
    kilix_home: os.PathLike[str] | str,
    contract_command: os.PathLike[str] | str,
    state_library: os.PathLike[str] | str,
    land_assets: os.PathLike[str] | str,
) -> ConformanceReport:
    """Run the common non-interactive suite against one provider command."""
    with tempfile.TemporaryDirectory(
        prefix="kilix-desktop-conformance-"
    ) as directory:
        sandbox = Path(directory)
        environment = _sandbox_environment(
            sandbox,
            kilix_home=kilix_home,
            contract_command=contract_command,
            state_library=state_library,
            land_assets=land_assets,
        )
        return _run_conformance(
            command,
            adapter_stage=adapter_stage,
            environment=environment,
            sandbox=sandbox,
        )


def run_conformance_matrix(
    providers: Sequence[MatrixProvider],
    *,
    passes: int,
    kilix_home: os.PathLike[str] | str,
    contract_command: os.PathLike[str] | str,
    state_library: os.PathLike[str] | str,
    land_assets: os.PathLike[str] | str,
) -> MatrixReport:
    """Run an exact ordered provider population for independent fresh passes."""
    population = tuple(providers)
    if not population:
        raise ConformanceError("conformance matrix provider population is empty")
    if passes < 1:
        raise ConformanceError("conformance matrix pass population must be positive")
    identities = [provider.provider_id for provider in population]
    if any(not identity for identity in identities):
        raise ConformanceError("conformance matrix contains an empty provider identity")
    if len(identities) != len(set(identities)):
        raise ConformanceError("conformance matrix repeats a provider identity")
    for provider in population:
        if not provider.command or any(not item for item in provider.command):
            raise ConformanceError(
                f"conformance matrix command for {provider.provider_id} is empty"
            )
        if not provider.expected_checks:
            raise ConformanceError(
                f"conformance matrix checks for {provider.provider_id} are empty"
            )
        _verify_matrix_entry(provider, "before matrix")

    reports: list[ConformanceReport] = []
    for _pass in range(passes):
        for provider in population:
            _verify_matrix_entry(provider, "before invocation")
            report = run_conformance(
                provider.command,
                kilix_home=kilix_home,
                contract_command=contract_command,
                state_library=state_library,
                land_assets=land_assets,
            )
            if report.provider_id != provider.provider_id:
                raise ConformanceError(
                    "conformance matrix provider identity mismatch: "
                    f"expected {provider.provider_id}, observed {report.provider_id}"
                )
            if report.checks != provider.expected_checks:
                raise ConformanceError(
                    f"conformance matrix check tuple changed for {provider.provider_id}"
                )
            if report.adapter_stage:
                raise ConformanceError("conformance matrix did not run in final mode")
            _verify_matrix_entry(provider, "after invocation")
            reports.append(report)
    return MatrixReport(passes, population, tuple(reports))


def _verify_matrix_entry(provider: MatrixProvider, phase: str) -> None:
    if provider.entry_path is None and provider.entry_sha256 is None:
        return
    if provider.entry_path is None or provider.entry_sha256 is None:
        raise ConformanceError(
            f"conformance matrix entry binding is incomplete for {provider.provider_id}"
        )
    try:
        status = provider.entry_path.lstat()
        digest = hashlib.sha256(provider.entry_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ConformanceError(
            f"conformance matrix entry for {provider.provider_id} is unreadable {phase}: {error}"
        ) from error
    if not stat.S_ISREG(status.st_mode) or provider.entry_path.is_symlink():
        raise ConformanceError(
            f"conformance matrix entry for {provider.provider_id} is not a regular non-symlink {phase}"
        )
    if digest != provider.entry_sha256:
        raise ConformanceError(
            f"conformance matrix entry digest changed for {provider.provider_id} {phase}"
        )


def _run_conformance(
    command: Sequence[str],
    *,
    adapter_stage: bool,
    environment: Mapping[str, str],
    sandbox: Path,
) -> ConformanceReport:
    checked: list[str] = []
    version = run_endpoint(
        command,
        ["--version"],
        timeout=DEADLINES_SECONDS["describe"],
        environment=environment,
    )
    if version.returncode != 0 or version.stderr:
        raise ConformanceError("--version must succeed without stderr")
    if (
        not version.stdout.endswith(b"\n")
        or version.stdout.endswith(b"\n\n")
        or not version.stdout[:-1]
        or b"\n" in version.stdout[:-1]
    ):
        raise ConformanceError("--version must emit exactly one non-empty line")
    try:
        version.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConformanceError("--version stdout is not UTF-8") from error
    checked.append("version")

    description = _json_document(
        _read_only_endpoint(
            command,
            ["provider", "describe", "--json"],
            timeout=DEADLINES_SECONDS["describe"],
            environment=environment,
            sandbox=sandbox,
            endpoint="provider describe",
        ),
        "provider-description",
    )
    provider_id = description["provider_id"]
    checked.append("describe")

    check = _json_document(
        _read_only_endpoint(
            command,
            ["provider", "check", "--json"],
            timeout=DEADLINES_SECONDS["check"],
            environment=environment,
            sandbox=sandbox,
            endpoint="provider check",
        ),
        "provider-check",
    )
    if check["provider_id"] != provider_id:
        raise ConformanceError("check provider_id disagrees with describe")
    checked.append("check")

    config_schema = _json_document(
        _read_only_endpoint(
            command,
            ["provider", "config", "schema", "--json"],
            timeout=DEADLINES_SECONDS["config"],
            environment=environment,
            sandbox=sandbox,
            endpoint="provider config schema",
        ),
        "config-schema",
    )
    if config_schema["x-kilix-provider-id"] != provider_id:
        raise ConformanceError("config schema provider_id disagrees with describe")
    checked.append("config-schema")

    config = _json_document(
        _read_only_endpoint(
            command,
            ["provider", "config", "get", "--json"],
            timeout=DEADLINES_SECONDS["config"],
            environment=environment,
            sandbox=sandbox,
            endpoint="provider config get",
        ),
        "provider-config",
    )
    if config["provider_id"] != provider_id:
        raise ConformanceError("config provider_id disagrees with describe")
    checked.append("config-get")

    capabilities = description["capabilities"]
    if _capability_available(capabilities["settings"]):
        mutation = run_endpoint(
            command,
            ["provider", "config", "set", "conformance-probe", "1"],
            timeout=DEADLINES_SECONDS["config"],
            environment=environment,
        )
        if mutation.returncode != 0:
            raise ConformanceError(
                f"advertised config-set endpoint exited {mutation.returncode}"
            )
        if mutation.stdout or mutation.stderr:
            raise ConformanceError(
                "successful config-set wrote stdout or stderr"
            )
        changed_config = _json_document(
            _read_only_endpoint(
                command,
                ["provider", "config", "get", "conformance-probe", "--json"],
                timeout=DEADLINES_SECONDS["config"],
                environment=environment,
                sandbox=sandbox,
                endpoint="provider config get after set",
            ),
            "provider-config",
        )
        if changed_config["provider_id"] != provider_id:
            raise ConformanceError(
                "config after set provider_id disagrees with describe"
            )
        if changed_config["revision"] <= config["revision"]:
            raise ConformanceError("config-set did not advance the revision")
        if changed_config["values"].get("conformance-probe") != 1:
            raise ConformanceError("config-set value was not observable")
        checked.append("config-set")
    else:
        _expect_unavailable(
            _read_only_endpoint(
                command,
                ["provider", "config", "set", "conformance-probe", "1"],
                timeout=DEADLINES_SECONDS["config"],
                environment=environment,
                sandbox=sandbox,
                endpoint="unavailable provider config set",
            ),
            "config-set",
        )
        checked.append("config-set-unavailable")

    output = sandbox / "provider-screenshot.png"
    screenshot = run_endpoint(
        command,
        ["provider", "screenshot", str(output)],
        timeout=DEADLINES_SECONDS["screenshot"],
        environment=environment,
    )
    if _capability_available(capabilities["headless_screenshot"]):
        if screenshot.returncode != 0:
            raise ConformanceError(
                f"advertised screenshot endpoint exited {screenshot.returncode}"
            )
        if screenshot.stdout or screenshot.stderr:
            raise ConformanceError("successful screenshot wrote stdout or stderr")
        try:
            status = output.lstat()
        except OSError as error:
            raise ConformanceError("screenshot did not create its output") from error
        if not output.is_file() or output.is_symlink() or status.st_size == 0:
            raise ConformanceError("screenshot output is not a non-empty regular file")
        checked.append("screenshot")
    else:
        _expect_unavailable(screenshot, "screenshot")
        if output.exists() or output.is_symlink():
            raise ConformanceError("unavailable screenshot created an output path")
        checked.append("screenshot-unavailable")

    migration = _read_only_endpoint(
        command,
        [
            "provider",
            "migrate",
            "--from",
            description["provider_version"],
            "--dry-run",
        ],
        timeout=DEADLINES_SECONDS["migrate"],
        environment=environment,
        sandbox=sandbox,
        endpoint="provider migrate --dry-run",
    )
    if adapter_stage:
        _expect_unavailable(migration, "migrate")
        checked.append("migration-gate")
    else:
        migration_document = _json_document(migration, "migration")
        if migration_document["provider_id"] != provider_id:
            raise ConformanceError("migration provider_id disagrees with describe")
        if not migration_document["dry_run"]:
            raise ConformanceError("migration conformance requires a dry-run record")
        checked.append("migration-dry-run")

    checked.append("read-only-endpoints")
    return ConformanceReport(provider_id, tuple(checked), adapter_stage)
