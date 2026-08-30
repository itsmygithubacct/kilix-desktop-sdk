#!/usr/bin/env python3
"""Verify that every imported commit is present, faithful, and correctly attributed.

Runs offline against this repository alone.

WHAT THIS PROVES, AND HOW
=========================
An earlier version of this tool checked only that each imported commit's
`components/<name>` subtree equalled the `old_tree` recorded in
docs/provenance/map-*.tsv. A review seat showed by mutation that this cannot
fail in the way that matters: replacing every `old_commit` in one map with
fabricated SHAs still returned 398/398, exit 0. The claimed original was loaded
into a dictionary and used only for its values, so the attribution itself was
never resolved against anything. A tool that passes a deliberately
mis-attributed import is not evidence of a faithful import.

The attribution is now PROVEN rather than trusted, and still offline.

A Git commit's object name is the SHA-1 of its serialised object: tree,
parents, author, committer and message. This import preserves author,
committer, timestamps and message byte-for-byte, and re-roots the tree under
components/<name>. So the ORIGINAL commit object is fully reconstructible from
the imported one:

    tree    <- the recorded old_tree (independently checked against the
               imported commit's own components/<name> subtree)
    parents <- each imported parent mapped back through the map
    the rest <- copied verbatim from the imported commit's header and message

Hashing that reconstruction must reproduce `old_commit` exactly. It can only do
so if the recorded original is the real commit whose tree and metadata these
are. A fabricated `old_commit`, a swapped upstream, a doctored `old_tree`, an
altered author, committer, timestamp or message, or a broken parent mapping all
change the hash and are caught.

WHAT THIS STILL DOES NOT PROVE
==============================
That the original commits are reachable in some published repository. This tool
proves the map is internally true; it does not prove provenance against an
external ledger. Resolving the originals in the component repositories remains a
separate check, and docs/provenance/import-evidence.md records which rows cannot
be resolved from published bytes.

Exit 0 only when every row passes every check. Prints denominators.
"""
import subprocess, sys, pathlib, collections, hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENTS = [
    "kilix-desktop-contract",
    "kilix-95",
    "kilix-cap",
    "kilix-land-desktop",
    "kilix-tui-utils",
]


def git(*args, binary=False):
    out = subprocess.run(
        ["git", "-C", str(ROOT)] + list(args), capture_output=True, check=True
    ).stdout
    return out if binary else out.decode().strip()


def reconstruct_original(new_commit, old_tree, new_to_old):
    """Rebuild the original commit object byte-for-byte and hash it.

    Every header other than tree/parent is carried over verbatim, so an
    unexpected header (encoding, gpgsig, mergetag) is preserved rather than
    silently dropped -- dropping one would change the hash and be reported as a
    mismatch, which is the safe direction.
    """
    raw = git("cat-file", "commit", new_commit, binary=True)
    header, _, message = raw.partition(b"\n\n")
    rebuilt = []
    for line in header.split(b"\n"):
        key, _, value = line.partition(b" ")
        if key == b"tree":
            rebuilt.append(b"tree " + old_tree.encode())
        elif key == b"parent":
            mapped = new_to_old.get(value.decode())
            if mapped is None:
                return None
            rebuilt.append(b"parent " + mapped.encode())
        else:
            rebuilt.append(line)
    body = b"\n".join(rebuilt) + b"\n\n" + message
    return hashlib.sha1(
        b"commit " + str(len(body)).encode() + b"\x00" + body
    ).hexdigest()


def main():
    total = passed = 0
    attribution_ok = 0
    failures = []
    for comp in COMPONENTS:
        path = ROOT / "docs" / "provenance" / f"map-{comp}.tsv"
        rows = [line.rstrip("\n").split("\t") for line in path.open()][1:]
        new_to_old = {r[2]: r[0] for r in rows}
        new_set = set(new_to_old)
        comp_ok = comp_attr = 0
        for old_commit, old_tree, new_commit, _date, _subject in rows:
            total += 1
            checks = []
            try:
                git("cat-file", "-e", new_commit + "^{commit}")
            except subprocess.CalledProcessError:
                failures.append(f"{comp} {new_commit}: not present")
                continue
            subtree = git("rev-parse", f"{new_commit}:components/{comp}")
            checks.append(("subtree == recorded old_tree", subtree == old_tree))
            top = git("ls-tree", "--name-only", new_commit).split()
            checks.append(("nothing outside components/", top == ["components"]))
            parents = git("rev-list", "--parents", "-n", "1", new_commit).split()[1:]
            checks.append(("parents are imported commits",
                           all(p in new_set for p in parents)))

            # The attribution check: prove old_commit, do not trust it.
            rebuilt = reconstruct_original(new_commit, old_tree, new_to_old)
            attributed = rebuilt == old_commit
            checks.append(("old_commit is the true SHA-1 of the reconstructed "
                           "original", attributed))
            if attributed:
                attribution_ok += 1
                comp_attr += 1

            if all(ok for _n, ok in checks):
                passed += 1
                comp_ok += 1
            else:
                bad = [n for n, ok in checks if not ok]
                failures.append(
                    f"{comp} {old_commit}->{new_commit}: {', '.join(bad)}"
                    + (f" (reconstructed {rebuilt})" if not attributed else "")
                )
        print(f"{comp}: {comp_ok}/{len(rows)} imported commits verified faithful; "
              f"{comp_attr}/{len(rows)} attributions cryptographically proven")

    dupes = [c for c, n in collections.Counter(
        r.split("\t")[2]
        for comp in COMPONENTS
        for r in (ROOT / "docs" / "provenance" / f"map-{comp}.tsv")
        .read_text().splitlines()[1:]
    ).items() if n > 1]
    print(f"duplicate imported commits across maps: {len(dupes)}/0 expected")

    print(f"TOTAL: {passed}/{total} imported commits verified faithful; "
          f"{attribution_ok}/{total} attributions cryptographically proven; "
          f"{len(failures)}/{total} failures")
    for f in failures[:20]:
        print("  FAIL", f)
    if len(failures) > 20:
        print(f"  ... and {len(failures) - 20} more")
    return 0 if (passed == total and attribution_ok == total and not dupes) else 1


if __name__ == "__main__":
    sys.exit(main())
