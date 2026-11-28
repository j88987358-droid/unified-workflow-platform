# Google Apps Script persistence backend

This directory contains the server-side Web App endpoint consumed by `platform_core/storage/apps_script_storage.py`.

## Configure

1. Create/open the Google Spreadsheet used for platform persistence.
2. Open **Extensions → Apps Script** and paste `Code.gs` into the project.
3. In **Project Settings → Script Properties**, add:
   - `UWP_SPREADSHEET_ID`: the spreadsheet ID from its URL.
   - `UWP_API_TOKEN`: a long random secret (at least 32 random bytes recommended).
4. Deploy → New deployment → Web app:
   - Execute as: **Me**.
   - Who has access: **Anyone** (the endpoint authenticates POST bodies using the secret token).
5. Copy the `/exec` URL into GitHub Actions secret `GOOGLE_APPS_SCRIPT_URL` and the same token into `GOOGLE_APPS_SCRIPT_TOKEN`.
6. Run the repository's Apps Script live-storage workflow only after both secrets are configured.

The API creates `Persistence` and `ExecutionLeases` tabs on first use. ScriptLock serializes reads/writes and lease transitions within this Apps Script project. Do not deploy a second independent Apps Script project against the same spreadsheet: ScriptLock is scoped to a script project, not globally across projects.

## Actions

`ping`, `get`, `set`, `delete`, `lease_start`, `lease_heartbeat`, `lease_check`, `lease_inspect`, `lease_release`.

All requests are JSON POST bodies with `token` and `action`. Lease start rejects a different owner while a lease is unexpired; heartbeat/check/release require the matching owner. `lease_inspect` returns authoritative active/expiry metadata for recovery without exposing the lease token.
