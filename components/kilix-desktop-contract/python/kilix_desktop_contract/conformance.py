"""Process-isolated non-interactive provider conformance checks.

The adapter-stage mode exists for the ordered release window in which protocol
adapters are present but shared persistence is not.  It still requires all
read-only documents, screenshot truthfulness and explicit unavailable exits;
only migration execution is relaxed.  A final run omits that mode and requires
a valid dry-run migration record.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Any, Sequence

from .constants import DEADLINES_SECONDS, EXIT_STATUSES
from .validation import errors_for, validators


MAX_OUTPUT_BYTES = 4 * 1024 * 1024


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
) -> ConformanceReport:
    """Run the common non-interactive suite against one provider command."""
    checked: list[str] = []
    version = run_endpoint(command, ["--version"], timeout=DEADLINES_SECONDS["describe"])
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
        run_endpoint(
            command,
            ["provider", "describe", "--json"],
            timeout=DEADLINES_SECONDS["describe"],
        ),
        "provider-description",
    )
    provider_id = description["provider_id"]
    checked.append("describe")

    check = _json_document(
        run_endpoint(
            command,
            ["provider", "check", "--json"],
            timeout=DEADLINES_SECONDS["check"],
        ),
        "provider-check",
    )
    if check["provider_id"] != provider_id:
        raise ConformanceError("check provider_id disagrees with describe")
    checked.append("check")

    config_schema = _json_document(
        run_endpoint(
            command,
            ["provider", "config", "schema", "--json"],
            timeout=DEADLINES_SECONDS["config"],
        ),
        "config-schema",
    )
    if config_schema["x-kilix-provider-id"] != provider_id:
        raise ConformanceError("config schema provider_id disagrees with describe")
    checked.append("config-schema")

    config = _json_document(
        run_endpoint(
            command,
            ["provider", "config", "get", "--json"],
            timeout=DEADLINES_SECONDS["config"],
        ),
        "provider-config",
    )
    if config["provider_id"] != provider_id:
        raise ConformanceError("config provider_id disagrees with describe")
    checked.append("config-get")

    capabilities = description["capabilities"]
    if not _capability_available(capabilities["settings"]):
        _expect_unavailable(
            run_endpoint(
                command,
                ["provider", "config", "set", "conformance-probe", "1"],
                timeout=DEADLINES_SECONDS["config"],
            ),
            "config-set",
        )
        checked.append("config-set-unavailable")

    with tempfile.TemporaryDirectory(prefix="kilix-desktop-conformance-") as directory:
        output = Path(directory) / "provider-screenshot.png"
        screenshot = run_endpoint(
            command,
            ["provider", "screenshot", str(output)],
            timeout=DEADLINES_SECONDS["screenshot"],
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

    migration = run_endpoint(
        command,
        [
            "provider",
            "migrate",
            "--from",
            description["provider_version"],
            "--dry-run",
        ],
        timeout=DEADLINES_SECONDS["migrate"],
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

    return ConformanceReport(provider_id, tuple(checked), adapter_stage)
