#!/usr/bin/env python3
"""Verify the assembled layout against manifest.toml.

Checks that every component subtree at HEAD equals the tree of its recorded
imported revision, that the declared submodule gitlinks are the ones actually
present, that no owned component is a nested Git repository, and that the
top-level layout is the one the design specifies.

Exit 0 only when every check passes. Prints denominators.
"""
import subprocess, sys, pathlib, tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPECTED_TOP = {
    ".gitmodules", ".reuse", "LICENSES", "README.md", "components", "docs",
    "integration", "manifest.toml", "tools",
}


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT)] + list(args),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def main():
    manifest = tomllib.load((ROOT / "manifest.toml").open("rb"))
    checks = []

    # This tool returned 6/6 PASS on a repository with an entire 79-commit
    # component erased, because it iterated the components the manifest still
    # listed. History is the authority: erasing a component's tree, map and
    # manifest entry does not remove the commits it already contributed.
    history_components: set[str] = set()
    for commit in git("rev-list", "HEAD").split():
        if git("ls-tree", "--name-only", commit).split() != ["components"]:
            continue
        inner = git("ls-tree", "--name-only", f"{commit}:components").split()
        if len(inner) == 1:
            history_components.add(inner[0])
    manifest_names = {c["name"] for c in manifest["component"]}
    erased = sorted(history_components - manifest_names)
    for name in erased:
        print(f"  FAIL component '{name}' has imported commits in history but "
              f"is not a component of this manifest -- erased")
    checks.append(("every component in history is still a component here",
                   not erased,
                   f"{len(history_components & manifest_names)}/"
                   f"{len(history_components)} history components present"
                   + (f"; erased: {', '.join(erased)}" if erased else "")))

    top = set(git("ls-tree", "--name-only", "HEAD").split())
    checks.append(("top-level layout", top == EXPECTED_TOP,
                   f"{len(top & EXPECTED_TOP)}/{len(EXPECTED_TOP)} expected entries present"))

    comps = manifest["component"]
    tree_ok = 0
    for c in comps:
        head_tree = git("rev-parse", f"HEAD:{c['path']}")
        imported_tree = git("rev-parse", f"{c['imported_revision']}:{c['path']}")
        if head_tree == imported_tree:
            tree_ok += 1
        else:
            print(f"  FAIL {c['name']}: HEAD tree {head_tree} != "
                  f"imported {c['imported_revision']} tree {imported_tree}")
    checks.append(("component trees match imported revisions",
                   tree_ok == len(comps), f"{tree_ok}/{len(comps)}"))

    gitlinks = {}
    for line in git("ls-tree", "-r", "HEAD").splitlines():
        meta, path = line.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind == "commit":
            gitlinks[path] = sha
    declared = {}
    for c in comps:
        for sm in c.get("submodules", []):
            declared[f"{c['path']}/{sm['path']}"] = sm["gitlink"]
    checks.append(("declared gitlinks == present gitlinks",
                   declared == gitlinks,
                   f"{len(declared.keys() & gitlinks.keys())}/{len(gitlinks)} "
                   f"present gitlinks declared, {len(declared)} declared in manifest"))

    nested = [p for p in git("ls-files").splitlines()
              if "/.git/" in p or p.endswith("/.git")]
    checks.append(("no nested Git repositories for owned components",
                   not nested, f"{len(nested)}/0 found"))

    # This once summed the manifest's own numbers and compared them to the
    # manifest's own total -- true by arithmetic whatever the repository held,
    # and it printed "398/398" while a map was a row short. Compare against the
    # map files instead; verify-provenance.py binds those to the repository.
    counted = sum(c["imported_commits"] for c in comps)
    declared_total = manifest["sdk"]["imported_commits"]
    rows_per_component = {}
    for c in comps:
        path = ROOT / "docs" / "provenance" / f"map-{c['name']}.tsv"
        rows_per_component[c["name"]] = len(path.read_text().splitlines()) - 1
    mismatched = [c["name"] for c in comps
                  if rows_per_component[c["name"]] != c["imported_commits"]]
    rows_total = sum(rows_per_component.values())
    checks.append(("manifest per-component counts equal their map row counts",
                   not mismatched,
                   f"{len(comps) - len(mismatched)}/{len(comps)}"
                   + (f"; mismatched: {', '.join(mismatched)}" if mismatched else "")))
    checks.append(("manifest total equals the summed map rows",
                   rows_total == declared_total == counted,
                   f"rows {rows_total}, manifest total {declared_total}, "
                   f"component sum {counted}"))

    ok = 0
    for name, result, detail in checks:
        print(f"{'PASS' if result else 'FAIL'}  {name}: {detail}")
        ok += bool(result)
    print(f"TOTAL: {ok}/{len(checks)} layout checks passed")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
