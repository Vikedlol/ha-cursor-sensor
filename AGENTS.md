# Agent instructions

Home Assistant custom integration (**Cursor Usage**) distributed via HACS.

## Release management

HACS displays commit hashes when there is no **GitHub Release**. This repo publishes releases from version tags via `.github/workflows/release.yml`.

### Version source of truth

- Edit only `custom_components/cursor_usage/manifest.json` → `"version"` (semver).
- Git tag must match that value (`0.4.2` or `v0.4.2`).
- `hacs.json` sets `hide_default_branch: true`, so a published release is required for installs/updates.

### Semver

| Change | Bump |
|--------|------|
| Breaking sensor/config/entity changes | MAJOR |
| New features / sensors | MINOR |
| Bugfixes, icons, docs, chores | PATCH |

### Publish a release

1. Bump `manifest.json` `"version"`.
2. Commit and push to `main`.
3. Tag and push (annotated tag preferred):

```bash
git tag -a 0.4.2 -m "Release 0.4.2"
git push origin main
git push origin 0.4.2
```

4. Verify the **Release** workflow passed and the release appears at  
   https://github.com/Vikedlol/ha-cursor-sensor/releases

### Agents must not

- Leave HACS users on commit-SHA versioning (forget to tag/push after a user-facing change).
- Tag a version that does not match `manifest.json` (CI fails).
- Force-push or delete release tags unless the user explicitly requests it.

Cursor also loads `.cursor/rules/release-management.mdc` for the same policy.
