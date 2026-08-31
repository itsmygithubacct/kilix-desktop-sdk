#!/usr/bin/env python3
"""P3 gate: assert that no component reaches into a peer component.

The F110 plan's P3 acceptance evidence is "a repository-wide grep gate asserts
zero peer imports, mirrors or sibling-path lookups". This is that gate, and it
is shipped BEFORE the couplings are removed, deliberately: a gate that reports
4/4 present is worth more than no gate, because it makes the remaining work
measurable and it cannot silently start passing for the wrong reason later.

It does NOT grep for a literal path. Cap's sibling lookup contains no
"../kilix-95" string at all -- it computes parent_directory(project_directory)
and joins "kilix-95" -- so a naive string gate would report it clean while the
coupling was live. Each check below targets the mechanism, and each names the
file and line so the finding is actionable.

Exit 0 only when all four are gone. Prints a denominator.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
C = ROOT / "components"


def _lines(path, pattern):
    if not path.is_file():
        return []
    out = []
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if re.search(pattern, line):
            out.append((n, line.strip()))
    return out


def tui_scanner_mirror():
    """TUI carries a byte copy of the host's XDG scanner, plus the tool that
    syncs it and the test that polices the copy."""
    base = C / "kilix-tui-utils"
    present = [p for p in (base / "src/kilix_tui/xdgapps.py",
                           base / "tools/sync_xdgapps.py",
                           base / "tests/test_xdgapps_parity.py") if p.is_file()]
    return ("TUI mirrors the host XDG scanner",
            [f"{p.relative_to(ROOT)} exists" for p in present])


def cap_sibling_lookup():
    """Cap resolves a SIBLING kilix-95 checkout by computing a parent directory
    and joining the component name. No literal '../kilix-95' exists."""
    src = C / "kilix-cap" / "src" / "game_catalog.c"
    hits = [f"{src.relative_to(ROOT)}:{n}  {t}"
            for n, t in _lines(src, r'"kilix-95"|KILIX95_PROJECT_HOME')]
    helper = C / "kilix-cap" / "tools" / "kilix95_games.py"
    if helper.is_file():
        hits.append(f"{helper.relative_to(ROOT)} exists (peer helper)")
    return ("Cap resolves a sibling kilix-95 checkout", hits)


def land_launcher_probe():
    """Land probes for a launcher that a DIFFERENT component installs."""
    src = C / "kilix-land-desktop" / "src" / "launcher.c"
    return ("Land probes for the TUI-installed kilix-launcher",
            [f"{src.relative_to(ROOT)}:{n}  {t}"
             for n, t in _lines(src, r'kilix-launcher')])


def tui_ships_shared_launcher():
    """A provider ships a host-shared tool that other providers consume."""
    src = C / "kilix-tui-utils" / "install.sh"
    return ("TUI installs the shared kilix-launcher",
            [f"{src.relative_to(ROOT)}:{n}  {t}"
             for n, t in _lines(src, r'kilix-launcher')])


CHECKS = [tui_scanner_mirror, cap_sibling_lookup,
          land_launcher_probe, tui_ships_shared_launcher]


def main():
    removed = 0
    for check in CHECKS:
        name, evidence = check()
        if evidence:
            print(f"PRESENT  {name}")
            for e in evidence:
                print(f"           {e}")
        else:
            removed += 1
            print(f"REMOVED  {name}")
    print(f"TOTAL: {removed}/{len(CHECKS)} peer couplings removed; "
          f"{len(CHECKS) - removed}/{len(CHECKS)} still present")
    if removed != len(CHECKS):
        print("P3 is not discharged. This gate is expected to fail until it is.")
    return 0 if removed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
