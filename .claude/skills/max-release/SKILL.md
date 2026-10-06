---
name: max-release
description: Decide and ship a Max CLI version bump - recommend major, minor or patch from the commits since the last tag (scripts/release_plan.py plus a read of the diff), wait for the maintainer's choice, then update pyproject.toml and CHANGELOG.md, run the full CI, merge, tag and check PyPI. Use when the user says "bump the version", "release", "new version", "publish", or asks which version comes next.
---

# Releasing Max

The rules live in `docs/contributing.md` ("Commit Messages" and "Versions and Releases"). This skill is the order to apply them in. **Never bump or tag before the maintainer picks the level.**

## 1. Recommend

```bash
git fetch --tags origin
python scripts/release_plan.py
```

The script reads the commits since the last tag, sorts them by Conventional Commits type, flags a changed `requires-python` and settings added to `config.REMOVED_SETTINGS`, and prints a suggested level. It only sees what commit messages and those two files say, so read the diff for what they miss:

```bash
git diff $(git describe --tags --abbrev=0)..HEAD --stat
git diff $(git describe --tags --abbrev=0)..HEAD -- src/max_cli/interface src/max_cli/core/catalog src/max_cli/config.py
```

Look for, in this order:

| Found | Level |
|-------|-------|
| A command, option or setting removed or renamed; a default that changes what a command makes (output names, folders, formats); a Python version dropped; exit codes changed; the plugin API changed | major |
| A new command, option, page, setting, format or provider; a Python version added | minor |
| Only fixes, speedups, wording | patch |
| Only docs, tests, refactors, CI | no release |

When the script and the diff disagree, the bigger level wins; say why.

Then answer the maintainer with:

- the current version and the last tag;
- the level you recommend and the version it gives (`1.0.0` -> `1.1.0`);
- the reasons: the commits or diff findings that decide it, three to six of them;
- anything breaking, with what users must do;
- the other choices in one line each, if a reasonable person could pick them.

Then stop and wait for their answer.

## 2. Prepare

On the level they chose:

1. Branch `release/X.Y.Z` from an up-to-date `main`.
2. `pyproject.toml`: `version = "X.Y.Z"` (asks first: the guard watches that file).
3. `CHANGELOG.md`: a `## X.Y.Z (YYYY-MM-DD)` section at the top with **New**, **Fixed** and **Changed** lists. Write each line for a user (what they can do now, what no longer goes wrong), not the commit subject. A breaking change says what to do instead. The Release workflow publishes this section as the GitHub release notes, so it has to stand alone.
4. Commit `release: X.Y.Z`. No Claude attribution in commits or PR text.

## 3. Ship

1. `python scripts/ci_local.py --full` on the clean tree, then `gh pr create`.
2. Merge once GitHub's checks pass (`gh pr checks <n>`; a job GitHub cancelled for lack of runners is rerun with `gh run rerun <id> --failed`, not a failure).
3. On the merged `main`: `git tag -a vX.Y.Z -m "Max X.Y.Z"` and `git push origin vX.Y.Z`. The pre-push hook runs the quick CI on that commit first.
4. Follow the Release run (`gh run list --workflow release.yml --limit 1`, then `gh run watch <id>`). It tests, builds, creates the GitHub release and publishes to PyPI with the `PYPI_API_TOKEN` secret.
5. Check `https://pypi.org/pypi/max-cli/json` shows the version and `gh release view vX.Y.Z` has the wheel and the sdist.
6. Tell the maintainer to run `pip install -e . --no-deps` with the dashboard closed, so their editable install shows the new version.

## When it goes wrong

- **Release run fails before "Publish to PyPI"**: nothing is published. Fix on a branch, merge, delete the tag (`git push origin :refs/tags/vX.Y.Z`, `git tag -d vX.Y.Z`) and tag the new merge commit.
- **"Publish to PyPI" fails with an auth error**: the `PYPI_API_TOKEN` secret expired. The maintainer makes a new token on pypi.org and saves it as that secret; then rerun the workflow (`gh run rerun <id>`). `skip-existing` keeps it safe to rerun.
- **A published version is wrong**: PyPI never takes the same version twice. Release the fix as the next patch.
