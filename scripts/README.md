# Obsidian release gate

Nothing anywhere used to compare a version number to the bytes it names. This
does. It exists because that gap shipped three times: a manifest at 0.6.1 whose
newest release was 0.4.2, a tag `1.2.4` and a `main` that differed by 2,037
bytes of CSS under one name, and a vault folder labelled 0.1.0 holding bytes
that were not the 0.1.0 release.

## The shape

`manifest.json` is the source of truth for the version. It is hand-authored and
has been correct every time. Nothing here derives a version from commit
messages, so there is no Conventional Commits requirement and no node toolchain
in repos that have no build step. What failed was the **tag, the release and
the bytes following the version**, so that is what is automated.

Two reusable workflows, called by each product repo:

| workflow | when | what it does |
| --- | --- | --- |
| `obsidian-release.yml` | push to `main` | if no tag equals the manifest version, create the annotated bare tag and publish the release with exactly the right assets. Idempotent. |
| `obsidian-version-gate.yml` | push to `main`, nightly, manual | compare the number against the bytes in three places, fail loudly, open a tracking issue |

The logic lives once, in `obsidian_release_gate.py` in this repo. It is not
copied into product repos: this whole system exists because two copies of one
thing drifted apart.

## Repo kinds

| kind | release assets | tracked in git | used by |
| --- | --- | --- | --- |
| `plugin` | `main.js`, `manifest.json`, `styles.css` | all three | icor-planner, icor-focus, icor-diagrams, myicor-connect |
| `theme` | `manifest.json`, `theme.css` | both | inkline-obsidian |
| `plugin-source` | `main.js`, `manifest.json`, `styles.css` | manifest + styles only | icor-chat |

Tags are bare, no `v` prefix, exactly equal to the manifest version, because
the Obsidian directory requires that. Themes must not ship `versions.json`; it
is a plugin mechanism and the theme catalog does not read it.

## What the gate checks

1. `manifest.json` parses and the version is `X.Y.Z`
2. a bare tag equal to that version exists
3. that tag is an ancestor of the shipping branch
4. every shipped tracked file is byte-identical at the tag and on the branch
5. a published, non-draft release exists for that tag
6. the release asset set is exactly the required list
7. every release asset digest equals the same path's blob at the tag
8. plugins: `versions.json[version] == manifest.minAppVersion`; themes: no
   `versions.json` at all

Check 4 is the clause the whole thing exists for. In the inkline incident every
number agreed, so a version-equality check passed. Only a byte comparison
catches it.

## A check that cannot run goes red

For `plugin-source` repos `main.js` is build output, so there is nothing in git
to compare a release asset against. The gate reports that as a **failure**, not
a pass. `--allow-build-output` waives it, knowingly and visibly, and the waiver
is written into the caller workflow where it can be read. A guard whose passing
state is reachable without the thing being true is worse than no guard, because
its green prevents the check a missing guard would have prompted.

## Running it by hand

```
python3 scripts/obsidian_release_gate.py check \
  --git-dir ~/.icor-git/inkline.git \
  --gh-repo myICOR/inkline-obsidian \
  --kind theme
```

Works against a bare clone or a worktree's `.git`. Needs `git`, `python3` and
an authenticated `gh`. Exit 0 green, 1 red.

## Deferred on purpose

Tag signing (Tom decision `s3g`). The seam is one flag on tag creation in the
script plus a key import step in `obsidian-release.yml`. Nothing else changes.
