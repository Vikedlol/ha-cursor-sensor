# Claude instructions

Follow **AGENTS.md** for this repository, especially the **Release management** section.

When the user asks to release, ship, tag, or bump the version: bump `custom_components/cursor_usage/manifest.json`, commit, push `main`, then push a matching annotated tag so `.github/workflows/release.yml` creates the GitHub Release HACS needs.
