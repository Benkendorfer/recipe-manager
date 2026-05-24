# Contributing

This project uses a lightweight GitHub-based workflow:

- `main` is protected.
- Changes should go through pull requests.
- Pull requests are squash-merged.
- User-visible changes require a Towncrier changelog fragment.
- Releases are made through release PRs and tagged after merging to `main`.

## Development setup

Create the conda environment:

```bash
conda env create -f environment.yml
conda activate recipe_manager
```

If the environment already exists:

```bash
conda env update -f environment.yml --prune
conda activate recipe_manager
```

Dependencies are declared in `pyproject.toml`. The conda environment installs the project in editable mode.

## Branch workflow

Create a branch from `main`:

```bash
git checkout main
git pull
git checkout -b short-description-of-change
```

Make changes, commit them, and open a pull request into `main`.

Use clear PR titles because PRs are squash-merged, and the PR title becomes the main commit message.

Good examples:

```text
Add YAML recipe import
Fix missing ingredient quantity parsing
Update Streamlit recipe detail layout
```

Avoid vague titles like:

```text
Fix stuff
Updates
WIP
```

## Issues and pull requests

If a PR fixes an issue, include this in the PR body:

```markdown
Fixes #12
```

GitHub will close the issue when the PR is merged.

## Changelog fragments

This project uses [Towncrier](https://towncrier.readthedocs.io/) to build `CHANGELOG.md`.

Do not edit `CHANGELOG.md` directly for normal feature or bug-fix PRs. Instead, add a changelog fragment under:

```text
changelog.d/
```

The filename should use the pull request number:

```text
changelog.d/<PR_NUMBER>.<type>.md
```

Valid types are:

```text
added
changed
fixed
removed
deprecated
security
```

Examples:

```text
changelog.d/27.added.md
changelog.d/28.fixed.md
changelog.d/29.changed.md
```

Each fragment should contain one short user-facing sentence.

Good:

```markdown
Added support for importing recipes from YAML files.
```

Good:

```markdown
Fixed recipe parsing failure when an ingredient quantity is missing.
```

Avoid implementation-only details:

```markdown
Refactored parser helper functions and renamed internal variables.
```

If a PR has no user-visible change, apply the `skip-changelog` label.

Examples of PRs that may use `skip-changelog`:

- test-only changes
- CI-only changes
- formatting
- internal refactors
- documentation-only changes

## Pull request checklist

Before merging a PR:

- The branch is up to date with `main`.
- CI passes.
- User-visible changes have a `changelog.d/*.md` fragment.
- Non-user-visible changes have the `skip-changelog` label.
- The PR title is suitable as a squash commit message.
- Any fixed issue is linked with `Fixes #...`.

## Release process

Releases are done with a release PR.

From an up-to-date `main`:

```bash
git checkout main
git pull
git checkout -b release/v0.2.0
```

Update the version in `pyproject.toml`:

```toml
version = "0.2.0"
```

Preview the changelog:

```bash
VERSION=$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
towncrier build --draft --version "$VERSION"
```

If the draft looks good, build the real changelog:

```bash
towncrier build --version "$VERSION"
```

This updates `CHANGELOG.md` and removes the consumed files from `changelog.d/`.

Commit the release changes:

```bash
git add pyproject.toml CHANGELOG.md changelog.d
git commit -m "Release v$VERSION"
```

Push the release branch:

```bash
git push origin release/v$VERSION
```

Open a release PR into `main`.

The release PR should usually have the `skip-changelog` label because it is the changelog update itself.

After the release PR is squash-merged into `main`, tag the merged `main` commit:

```bash
git checkout main
git pull origin main
git tag -a "v$VERSION" -m "Release v$VERSION"
git push origin "v$VERSION"
```

Do not tag the release branch before merging. Since release PRs are squash-merged, tagging the branch commit would create a tag that does not point to a commit on `main`.

## Versioning

This project uses semantic versioning:

```text
MAJOR.MINOR.PATCH
```

Use:

- `PATCH` for bug fixes
- `MINOR` for new features or behavior changes
- `MAJOR` for breaking changes

Before `1.0.0`, the project is considered experimental and APIs/config formats may still change.

## Changelog links

Changelog entries link to pull requests, not issues.

The usual traceability chain is:

```text
CHANGELOG.md entry
  -> pull request
  -> linked issue, if applicable
```

For example:

```text
changelog.d/27.fixed.md
```

links the changelog entry to PR `#27`.

If PR `#27` fixes issue `#12`, put this in the PR body:

```markdown
Fixes #12
```
