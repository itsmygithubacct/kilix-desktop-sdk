#!/usr/bin/env python3
"""Bind each component to the upstream repository manifest.toml NAMES.

Two review seats found the same residual: `source_repo` was read by no tool.
Repointing it to an unrelated repository left every offline verifier at exit 0,
because an honest map of the wrong repository reconciles perfectly. The offline
tools prove the map is internally true; they cannot prove WHICH upstream a
component came from.

This closes that, and it became closable only once every component's
source_revision was published: all five are now advertised by their named
remote, so the claim is checkable rather than merely stated.

This check is ONLINE by nature -- it is the one question that cannot be answered
from inside the repository. It is therefore a separate tool, and it reports
UNRESOLVED rather than PASS when the network is unavailable, so an offline run
can never be mistaken for a successful binding.

Usage: tools/check-upstream.py            # all components
Exit 0 only when every component's recorded revision is advertised by the
repository the manifest names.
"""
import pathlib, subprocess, sys, tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def advertised(repo_url, revision, timeout=90):
    """Return True/False/None -- None means the remote could not be reached."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", repo_url],
            capture_output=True, text=True, timeout=timeout,
            env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin",
                 "HOME": str(pathlib.Path.home())},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return any(line.split("\t")[0] == revision
               for line in result.stdout.splitlines() if line.strip())


def main():
    manifest = tomllib.load((ROOT / "manifest.toml").open("rb"))
    components = manifest["component"]
    bound = unresolved = 0
    failures = []
    for c in components:
        repo, rev = c["source_repo"], c["source_revision"]
        if not repo.startswith(("https://", "git@", "ssh://")):
            failures.append(f"{c['name']}: source_repo is not a fetchable URL: {repo!r}")
            print(f"FAIL       {c['name']}: source_repo is not a URL -- {repo!r}")
            continue
        state = advertised(repo, rev)
        if state is True:
            bound += 1
            print(f"BOUND      {c['name']}: {rev[:12]} advertised by {repo}")
        elif state is None:
            unresolved += 1
            print(f"UNRESOLVED {c['name']}: could not reach {repo} -- NOT a pass")
        else:
            failures.append(
                f"{c['name']}: {rev} is NOT advertised by {repo} -- the manifest "
                f"names an upstream that does not carry this component's revision")
            print(f"FAIL       {c['name']}: {rev[:12]} not advertised by {repo}")

    print(f"TOTAL: {bound}/{len(components)} components bound to the upstream the "
          f"manifest names; {unresolved} unresolved; {len(failures)} failures")
    for f in failures:
        print("  ", f)
    if unresolved:
        print("UNRESOLVED is not PASS: an offline run proves nothing about upstream.")
    return 0 if bound == len(components) else 1


if __name__ == "__main__":
    sys.exit(main())
