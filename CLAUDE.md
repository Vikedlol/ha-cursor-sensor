# Claude instructions

Follow **AGENTS.md** for this repository, especially the **Release management** section.

When the user asks to release, ship, tag, or bump the version: bump `custom_components/cursor_usage/manifest.json`, commit, and merge/push `main`. `.github/workflows/auto-release.yml` creates the matching GitHub Release (manual annotated tag + `release.yml` is fallback only).
