# Cursor Usage for Home Assistant

Custom integration that exposes your Cursor plan usage and on-demand spend as Home Assistant sensors.

## API note

**Official** Cursor usage APIs (Admin / Analytics) are **Enterprise-only** and use an Admin API key against `api.cursor.com`.

This integration targets **personal / Pro** accounts and polls the same undocumented dashboard endpoint the web UI uses:

```http
GET https://cursor.com/api/usage-summary
Cookie: WorkosCursorSessionToken=<token>
```

That cookie is not a public API key. It can expire, and Cursor may change the endpoint without notice.

Cloud Agents API / SDK keys (`crsr_…`) do **not** return billing usage.

## Install

### HACS (custom repository)

1. In HACS → **⋯** → **Custom repositories**, add:
   - Repository: `https://github.com/Vikedlol/ha-cursor-sensor`
   - Category: **Integration**
2. Search for **Cursor Usage** and download/install it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Cursor Usage**.

Not listed in the default HACS store yet — custom repository only.

### Manual

1. Copy `custom_components/cursor_usage` into your Home Assistant `config/custom_components/` directory so you have:

   ```text
   config/custom_components/cursor_usage/manifest.json
   ```

2. Restart Home Assistant.

3. Go to **Settings → Devices & services → Add integration → Cursor Usage**.

## Session token

1. Open [cursor.com/dashboard/usage](https://cursor.com/dashboard/usage) while signed in.
2. Open DevTools → **Application** → **Cookies** → `https://cursor.com`.
3. Copy the value of **`WorkosCursorSessionToken`**.
4. Paste it into the integration setup form (optional display name defaults to `Cursor`).

Store the token only in Home Assistant (config entry storage). Do not commit it to git.

When the token expires, sensors become unavailable — remove/re-add the integration or use the re-auth flow after pasting a fresh cookie.

## Entities

| Entity | State | Notes |
|--------|-------|--------|
| Plan usage | `%` | `individualUsage.plan.totalPercentUsed` |
| Plan used | number | Plan allowance consumed (`used` / `limit` / `remaining` in attributes) |
| On-demand spend | USD | Cents from the API converted to dollars |

Shared attributes include billing cycle start/end and membership type. Poll interval is **1 hour**.

## Enterprise

If you have an Enterprise Admin API key, prefer the official [Admin API](https://cursor.com/docs/account/teams/admin-api) (`/teams/spend`, `/teams/filtered-usage-events`) instead of this cookie-based path. That mode is not implemented here yet.
