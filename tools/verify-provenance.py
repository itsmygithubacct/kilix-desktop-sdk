#!/usr/bin/env python3
"""Verify that every imported commit is present and faithful.

Runs offline against this repository alone. For each row of
docs/provenance/map-<component>.tsv it checks that the imported commit exists,
that its <component> subtree is byte-identical to the tree the original commit
had, and that its parents are themselves imported commits from the same map.

Exit 0 only when every row passes. Prints denominators, never a bare "ok".
"""
import subprocess, sys, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENTS = [
    "kilix-desktop-contract",
    "kilix-95",
    "kilix-cap",
    "kilix-land-desktop",
    "kilix-tui-utils",
]


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT)] + list(args),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def main():
    total = passed = 0
    failures = []
    for comp in COMPONENTS:
        path = ROOT / "docs" / "provenance" / f"map-{comp}.tsv"
        rows = [line.rstrip("\n").split("\t") for line in path.open()][1:]
        by_old = {r[0]: r[2] for r in rows}
        new_set = set(by_old.values())
        comp_ok = 0
        for old_commit, old_tree, new_commit, _date, _subject in rows:
            total += 1
            checks = []
            try:
                git("cat-file", "-e", new_commit + "^{commit}")
                checks.append(("commit present", True))
            except subprocess.CalledProcessError:
                failures.append(f"{comp} {new_commit}: not present")
                continue
            subtree = git("rev-parse", f"{new_commit}:components/{comp}")
            checks.append(("subtree == original tree", subtree == old_tree))
            top = git("ls-tree", "--name-only", new_commit).split()
            checks.append(("nothing outside components/", top == ["components"]))
            parents = git("rev-list", "--parents", "-n", "1", new_commit).split()[1:]
            checks.append(("parents are imported commits",
                           all(p in new_set for p in parents)))
            if all(ok for _name, ok in checks):
                passed += 1
                comp_ok += 1
            else:
                bad = [n for n, ok in checks if not ok]
                failures.append(f"{comp} {old_commit}->{new_commit}: {', '.join(bad)}")
        print(f"{comp}: {comp_ok}/{len(rows)} imported commits verified faithful")

    dupes = [c for c, n in collections.Counter(
        r.split("\t")[2]
        for comp in COMPONENTS
        for r in (ROOT / "docs" / "provenance" / f"map-{comp}.tsv").read_text().splitlines()[1:]
    ).items() if n > 1]
    print(f"duplicate imported commits across maps: {len(dupes)}/0 expected")

    print(f"TOTAL: {passed}/{total} imported commits verified faithful; "
          f"{len(failures)}/{total} failures")
    for f in failures:
        print("  FAIL", f)
    return 0 if (passed == total and not dupes) else 1


if __name__ == "__main__":
    sys.exit(main())
