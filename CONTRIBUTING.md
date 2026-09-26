# Contributing to an ICOR for Life repository

This file is the org-wide default. A repository with its own
`CONTRIBUTING.md` wins; read that one first.

Pull requests are welcome. Every ICOR for Life plugin repository is under
the MIT licence (see its `LICENSE`), and every contribution is accepted
under the same terms: what comes in is licensed exactly as what goes out.
There is no contributor licence agreement to sign.

## Sign your commits

Every commit needs a Developer Certificate of Origin sign-off
(https://developercertificate.org, version 1.1): `git commit -s` adds the
`Signed-off-by: Your Name <you@example.com>` line. The sign-off says you
wrote the change, or have the right to submit it, under MIT. Pull requests
with unsigned commits are not merged.

The name in the sign-off is the name you go by on GitHub: a real name or a
consistent pseudonym, as long as it is yours and not misleading. Anonymous
sign-offs are not accepted. If you do not want your own email address in
the history, use GitHub's private no-reply address (Settings, Emails, "Keep
my email addresses private"). The sign-off, the name and the address become
part of this repository's public git history, are copied into every fork
and clone, and cannot be removed afterwards (Developer Certificate of
Origin 1.1, clause (d)). Decide what you put in before you sign.

### Keep your email address private

Before you open a pull request, turn on two settings on GitHub
(Settings, Emails): "Keep my email addresses private" and "Block command
line pushes that expose my email". Then commit and sign off with the
no-reply address GitHub shows there. Here is why. When a pull request is
squash-merged, GitHub writes the merge commit under the email address your
account uses for changes made on the website: your primary address, unless
"Keep my email addresses private" is on. The address you committed with
does not carry over. Git history is public, copied into every fork and
clone, and cannot be changed afterwards, so choose the address before you
open the pull request.

## Before you open a pull request

- Open an issue first for anything bigger than a small fix, so the shape is
  agreed before the work.
- One issue per pull request, and keep it small. A pull request that is
  readable in one pass gets merged; one that mixes concerns gets bounced
  with a `too-big` label.
- Add or update tests for the behaviour you change.
- Run the repository's gate locally and paste its output into the pull
  request: `npm run gate` where the repository has one, `npm test`
  otherwise.
- Do not bump the version. Leave `manifest.json`, `package.json` and
  `versions.json` alone, and do not edit `CHANGELOG.md`: we bump the version
  and write the changelog at release, on our own cadence. A pull request
  that bumps the version is bounced.
- No new runtime dependency without an issue that agrees to it first.
- Say so in the description if the change touches credentials, a network
  host, a spawned process, a workflow file or a dependency. Those get a
  security read before the review.

## How a change ships

Contributors do not push to `main`; every outside change arrives as a pull
request. Merging a pull request ships nothing: releases are cut from a
version tag by the maintainer, never from a push to `main`, so your change
reaches members with the next tagged release.

## Forks and new projects

The Obsidian directory encourages developers to collaborate on fewer
high-quality projects, so a change that fits a plugin belongs in that
plugin's repository as a pull request.

The Obsidian Community directory does not list forks: its Developer policies
state that "Forks are not allowed in the Community directory unless" the fork
"has received explicit written approval from the original author in a
publicly verifiable way" or the original author has been unreachable with no
update for at least 6 months, and that "If your project diverges from
existing options, it should not be a fork. Start fresh with a new repository
and your own code." So a project that diverges from one of these plugins
ships under its own plugin id and its own name, never the `icor-for-life-*`
id or the "ICOR for Life - ..." name: the id is unique to the directory entry
and its Owner, the name is covered by each repository's `TRADEMARK.md`, and
the MIT licence grants you the code, not the listing and not the name.

## Security

For a security problem, use the process in the repository's `SECURITY.md`
instead of a public issue or pull request.
