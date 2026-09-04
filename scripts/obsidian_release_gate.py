#!/usr/bin/env python3
"""
obsidian_release_gate.py - compare a version NUMBER against the BYTES it names.

Canonical copy: myICOR/.github  scripts/obsidian_release_gate.py
Do not fork this file into product repos. The per-repo workflows call the
reusable workflows in myICOR/.github, which run this one copy.

Two subcommands:

  check    Read-only drift audit. Exits 1 on any finding. This is the guard.
  release  If manifest.json's version has no matching tag, create the tag and
           publish the release with exactly the right asset set. Idempotent:
           re-running on an already-released version is a no-op.

The manifest is the source of truth. Nothing here derives a version from
commit messages; the version is hand-authored in manifest.json and the
automation's whole job is to make the tag, the release and the bytes follow it.

Repo kinds
  plugin         main.js/manifest.json/styles.css, all tracked in git
  theme          manifest.json/theme.css, both tracked in git
  plugin-source  main.js is BUILD OUTPUT and not tracked; manifest.json and
                 styles.css are tracked

Design rule (GL-075): a check that cannot run reports UNVERIFIED and fails.
It never reports green. A guard whose passing state is reachable without the
thing being true is worse than no guard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

KINDS = {
    # kind: (required release assets, files tracked in git that must match)
    "plugin": (
        ["main.js", "manifest.json", "styles.css"],
        ["main.js", "manifest.json", "styles.css"],
    ),
    "theme": (
        ["manifest.json", "theme.css"],
        ["manifest.json", "theme.css"],
    ),  # versions.json is optional for a theme; C8 checks it when present
    "plugin-source": (
        ["main.js", "manifest.json", "styles.css"],
        ["manifest.json", "styles.css"],
    ),
}


class Findings:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def ok(self, check: str, detail: str) -> None:
        self.rows.append(("PASS", check, detail))

    def fail(self, check: str, detail: str) -> None:
        self.rows.append(("FAIL", check, detail))

    def skip(self, check: str, detail: str) -> None:
        self.rows.append(("SKIP", check, detail))

    @property
    def failed(self) -> list[tuple[str, str, str]]:
        return [r for r in self.rows if r[0] == "FAIL"]

    def render(self) -> str:
        out = []
        for status, check, detail in self.rows:
            mark = {"PASS": "  ok  ", "FAIL": " FAIL ", "SKIP": " skip "}[status]
            out.append(f"[{mark}] {check}: {detail}")
        return "\n".join(out)


def run(args: list[str], cwd: str | None = None, check: bool = True) -> str:
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {p.returncode}: {p.stderr.strip()}")
    return p.stdout


def git(gitdir: str, *args: str, check: bool = True) -> str:
    return run(["git", "--git-dir", gitdir, *args], check=check).strip()


def git_bytes(gitdir: str, *args: str) -> bytes:
    p = subprocess.run(["git", "--git-dir", gitdir, *args], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.decode()[:200]}")
    return p.stdout


def gh_json(path: str, check: bool = True) -> object | None:
    p = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True
    )
    if p.returncode != 0:
        if check:
            raise RuntimeError(f"gh api {path} failed: {p.stderr.strip()[:300]}")
        return None
    return json.loads(p.stdout)


def blob_sha256(gitdir: str, rev: str, path: str) -> str | None:
    try:
        data = git_bytes(gitdir, "show", f"{rev}:{path}")
    except RuntimeError:
        return None
    return hashlib.sha256(data).hexdigest()


def tracked_files(gitdir: str, rev: str) -> set[str]:
    out = git(gitdir, "ls-tree", "-r", "--name-only", rev, check=False)
    return {line for line in out.splitlines() if line}


def read_manifest(gitdir: str, rev: str) -> dict:
    return json.loads(git_bytes(gitdir, "show", f"{rev}:manifest.json"))


def do_check(a: argparse.Namespace) -> int:
    f = Findings()
    gitdir = a.git_dir
    branch = a.branch
    assets_required, tracked_required = KINDS[a.kind]

    # --- C1 manifest parses and carries a sane version -----------------
    try:
        manifest = read_manifest(gitdir, branch)
    except Exception as e:  # noqa: BLE001
        f.fail("manifest", f"cannot read {branch}:manifest.json ({e})")
        print(f.render())
        return 1
    version = str(manifest.get("version", ""))
    if not SEMVER.match(version):
        f.fail("manifest.version", f"{version!r} is not X.Y.Z")
        print(f.render())
        return 1
    f.ok("manifest.version", f"{branch} declares {version}")

    # --- C2 a bare tag equal to the manifest version exists ------------
    tags = set(git(gitdir, "tag", "--list").splitlines())
    if version not in tags:
        f.fail(
            "tag-exists",
            f"manifest says {version} but no tag {version} exists "
            f"(this is the icor-planner shape: a version that was never cut)",
        )
    else:
        f.ok("tag-exists", f"tag {version} present (bare, no v prefix)")

    # --- C3 the tag is actually on the shipping branch -----------------
    if version in tags:
        on_branch = subprocess.run(
            ["git", "--git-dir", gitdir, "merge-base", "--is-ancestor", version, branch]
        ).returncode == 0
        if on_branch:
            f.ok("tag-on-branch", f"tag {version} is an ancestor of {branch}")
        else:
            f.fail(
                "tag-on-branch",
                f"tag {version} is NOT an ancestor of {branch}; the released "
                f"line and {branch} have diverged",
            )

    # --- C4 tag tree == branch tree for every shipped tracked file -----
    #     This is the inkline clause: numbers all agree, bytes do not.
    if version in tags:
        drifted = []
        for path in tracked_required:
            a_sha = blob_sha256(gitdir, version, path)
            b_sha = blob_sha256(gitdir, branch, path)
            if a_sha is None:
                f.fail("shipped-file-present", f"{path} missing from tag {version}")
                continue
            if b_sha is None:
                f.fail("shipped-file-present", f"{path} missing from {branch}")
                continue
            if a_sha != b_sha:
                drifted.append(f"{path} (tag {a_sha[:12]} vs {branch} {b_sha[:12]})")
        if drifted:
            f.fail(
                "bytes-tag-vs-branch",
                f"{branch} changed shipped files after tag {version} with no "
                f"version bump: " + "; ".join(drifted),
            )
        else:
            f.ok(
                "bytes-tag-vs-branch",
                f"all {len(tracked_required)} shipped tracked files identical "
                f"at tag {version} and {branch}",
            )

    # --- C5..C7 the published release ----------------------------------
    rel = None
    if a.gh_repo:
        rel = gh_json(f"repos/{a.gh_repo}/releases/tags/{version}", check=False)
    if a.gh_repo and rel is None:
        f.fail(
            "release-exists",
            f"no GitHub release tagged {version} in {a.gh_repo}",
        )
    elif rel is not None:
        if rel.get("draft"):
            f.fail("release-published", f"release {version} is still a DRAFT")
        else:
            f.ok("release-published", f"release {version} is published")

        names = sorted(x["name"] for x in rel.get("assets", []))
        if names != sorted(assets_required):
            f.fail(
                "release-asset-set",
                f"assets are {names}, required exactly {sorted(assets_required)}",
            )
        else:
            f.ok("release-asset-set", f"exactly {names}")

        by_name = {x["name"]: x for x in rel.get("assets", [])}
        for path in assets_required:
            asset = by_name.get(path)
            if asset is None:
                continue  # already reported by asset-set
            digest = (asset.get("digest") or "").removeprefix("sha256:")
            if not digest:
                f.fail("asset-digest", f"{path}: GitHub reports no digest")
                continue
            if path in tracked_required:
                want = blob_sha256(gitdir, version, path)
                if want is None:
                    f.fail("asset-digest", f"{path}: not in tag {version}")
                elif want != digest:
                    f.fail(
                        "asset-digest",
                        f"{path}: release asset {digest[:12]} != tag blob "
                        f"{want[:12]} - the release serves different bytes "
                        f"than the tag",
                    )
                else:
                    f.ok("asset-digest", f"{path}: {digest[:12]} matches tag blob")
            else:
                # Build output. There is nothing in git to compare it to.
                if a.allow_build_output:
                    f.skip(
                        "asset-digest",
                        f"{path}: build output, unverifiable against git "
                        f"(waived by --allow-build-output)",
                    )
                else:
                    f.fail(
                        "asset-digest",
                        f"{path}: build output; nothing in git to compare "
                        f"against, so this cannot be verified. Pass "
                        f"--allow-build-output to waive knowingly.",
                    )
    else:
        f.skip("release-exists", "no --gh-repo given, release checks skipped")

    # --- C8 versions.json[version] == manifest.minAppVersion -----------
    #     Plugins must ship it. Themes may: Obsidian's theme installer,
    #     theme update check and community theme modal all read it through
    #     the same versions.json resolver the plugin paths use (verified in
    #     app.js 1.12.7 and 1.13.7), and obsidian-sample-theme ships one.
    #     When a theme raises minAppVersion without it, members on an older
    #     app get "no compatible version" instead of the last release that
    #     still fits them. So: present means the same key/value check as a
    #     plugin; absent is a failure for a plugin and a pass for a theme.
    min_app = str(manifest.get("minAppVersion", ""))
    try:
        versions = json.loads(git_bytes(gitdir, "show", f"{branch}:versions.json"))
    except RuntimeError:
        if a.kind == "theme":
            f.ok(
                "versions.json",
                f"absent from {branch}; optional for a theme (ship one when "
                f"minAppVersion rises, so older apps can still install the "
                f"last release that fits them)",
            )
        else:
            f.fail("versions.json", f"missing from {branch} (required for plugins)")
    else:
        if not isinstance(versions, dict):
            f.fail("versions.json", "is not a JSON object of version -> minAppVersion")
        elif version not in versions:
            f.fail("versions.json", f"has no key {version}")
        elif str(versions[version]) != min_app:
            f.fail(
                "versions.json",
                f"{version} -> {versions[version]!r} but manifest "
                f"minAppVersion is {min_app!r}",
            )
        else:
            f.ok("versions.json", f"{version} -> {min_app}")

    print(f.render())
    if a.json_out:
        with open(a.json_out, "w") as fh:
            json.dump(
                {
                    "repo": a.gh_repo,
                    "kind": a.kind,
                    "version": version,
                    "rows": [
                        {"status": s, "check": c, "detail": d} for s, c, d in f.rows
                    ],
                    "failed": len(f.failed),
                },
                fh,
                indent=2,
            )
    n = len(f.failed)
    print()
    if n:
        print(f"RESULT: RED - {n} finding(s). The version number and the bytes "
              f"it names disagree.")
        return 1
    print("RESULT: GREEN - version, tag, release and bytes all agree.")
    return 0


def do_release(a: argparse.Namespace) -> int:
    gitdir = a.git_dir
    branch = a.branch
    assets_required, tracked_required = KINDS[a.kind]
    manifest = read_manifest(gitdir, branch)
    version = str(manifest["version"])
    if not SEMVER.match(version):
        print(f"refusing: manifest version {version!r} is not X.Y.Z", file=sys.stderr)
        return 1

    tags = set(git(gitdir, "tag", "--list").splitlines())

    # The previous tag must be resolved BEFORE we create the new one, or
    # `describe` would just find the tag we are about to add and the notes
    # would cover every commit in history.
    prev = git(gitdir, "describe", "--tags", "--abbrev=0",
               f"{version}^" if version in tags else branch,
               check=False)
    if prev == version:
        prev = git(gitdir, "describe", "--tags", "--abbrev=0", f"{version}^",
                   check=False)

    if version in tags:
        print(f"no-op: tag {version} already exists")
        rel = gh_json(f"repos/{a.gh_repo}/releases/tags/{version}", check=False)
        if rel is not None:
            print(f"no-op: release {version} already published")
            return 0
        print(f"tag {version} exists but no release does; publishing release only")
    else:
        print(f"tagging {branch} as {version} (previous tag: {prev or 'none'})")
        if not a.dry_run:
            run(["git", "--git-dir", gitdir, "tag", "-a", version,
                 "-m", f"{manifest.get('name', a.gh_repo)} {version}", branch])
            run(["git", "--git-dir", gitdir, "push", "origin", version])

    # Release notes from commit subjects since the previous tag. The endpoint
    # is the branch when we just created the tag from it, so this resolves
    # identically in a dry run (where the tag does not exist) and for real.
    endpoint = version if version in tags else branch
    rng = f"{prev}..{endpoint}" if prev else endpoint
    log = git(gitdir, "log", rng, "--no-merges", "--pretty=format:- %s", check=False)
    notes = log or "- initial release"

    if a.dry_run:
        print(f"[dry-run] would publish release {version} with assets "
              f"{assets_required}")
        print(f"[dry-run] notes:\n{notes}")
        return 0

    workdir = a.asset_dir or "."
    missing = [p for p in assets_required
               if not os.path.isfile(os.path.join(workdir, p))]
    if missing:
        print(f"refusing: asset(s) not present in {workdir}: {missing}",
              file=sys.stderr)
        return 1

    cmd = ["gh", "release", "create", version, "--repo", a.gh_repo,
           "--title", f"{manifest.get('name', a.gh_repo)} {version}",
           "--notes", notes]
    cmd += [os.path.join(workdir, p) for p in assets_required]
    run(cmd)
    print(f"published release {version} with {assets_required}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("check", "release"):
        s = sub.add_parser(name)
        s.add_argument("--git-dir", required=True,
                       help="path to a bare clone, or <worktree>/.git")
        s.add_argument("--gh-repo", default="", help="owner/name")
        s.add_argument("--kind", required=True, choices=sorted(KINDS))
        s.add_argument("--branch", default="main")
        if name == "check":
            s.add_argument("--allow-build-output", action="store_true")
            s.add_argument("--json-out", default="")
        else:
            s.add_argument("--asset-dir", default="")
            s.add_argument("--dry-run", action="store_true")

    a = ap.parse_args()
    return do_check(a) if a.cmd == "check" else do_release(a)


if __name__ == "__main__":
    sys.exit(main())
