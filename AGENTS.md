# Agent instructions

Home Assistant custom integration (**Cursor Usage**) distributed via HACS.

## Release management

HACS displays commit hashes when there is no **GitHub Release**. This repo publishes releases automatically from `manifest.json` via `.github/workflows/auto-release.yml` (and still accepts manual tags via `.github/workflows/release.yml`).

### Version source of truth

- Edit only `custom_components/cursor_usage/manifest.json` → `"version"` (semver).
- Git tag / release name must match that value (`0.4.2` or `v0.4.2`).
- `hacs.json` sets `hide_default_branch: true`, so a published release is required for installs/updates.

### Semver

| Change | Bump |
|--------|------|
| Breaking sensor/config/entity changes | MAJOR |
| New features / sensors | MINOR |
| Bugfixes, icons, docs, chores | PATCH |

### Publish a release

1. Bump `manifest.json` `"version"` in the same PR as the user-facing change.
2. Merge to `main` (working tree clean, branch pushed).
3. **Auto Release** runs on `main`: if no GitHub Release (or tag) exists for that version, it creates the tag and release with generated notes.
4. Confirm https://github.com/Vikedlol/ha-cursor-sensor/releases shows the new release.

Manual fallback (only if automation failed or you need an out-of-band tag):

```bash
git tag -a 0.4.2 -m "Release 0.4.2"
git push origin 0.4.2
```

That still triggers `.github/workflows/release.yml`.

### Agents must not

- Leave HACS users on commit-SHA versioning (merge a user-facing change without bumping `manifest.json`).
- Tag a version that does not match `manifest.json` (CI fails).
- Force-push or delete release tags unless the user explicitly requests it.
- Manually tag after every merge when Auto Release is healthy — bump + merge is enough.

Cursor also loads `.cursor/rules/release-management.mdc` for the same policy.
